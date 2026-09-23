"""
The same cellular automaton, with the neighbourhood taken from a graph.

This module exists to run ONE controlled comparison. The state set, the
transition rule, the telemetry function, the fault process and the update
schedule are identical to `lattice.py`. The only thing that changes is where a
cell's neighbours come from:

    lattice.py    N(i) = the 4 or 8 lattice cells adjacent to i
    graph_ca.py   N(i) = the graph neighbours of i

Because nothing else differs, any difference in behaviour is attributable to
topology alone. As a check on that claim, `grid_graph()` builds the lattice as
a graph, and running this module on it reproduces `LatticeCA` exactly.

WHY TOPOLOGY SHOULD MATTER
--------------------------
The local rule says a failing cell j spills load_j / |N(j)| to each neighbour.
With uniform initial load, a neighbour i survives that spill iff

        1 + 1/k_j  <=  1 + alpha        i.e.     alpha >= 1 / k_j

where k_j is the degree of the cell that FAILED, not of the cell receiving. So
the danger a failure poses is set by how thinly it can spread its load.

On a lattice every cell has the same degree, so there is a single threshold and
the system is either everywhere-safe or everywhere-unsafe. On a graph with a
spread of degrees, each cell carries its own local threshold 1/k_j, so at a
given alpha only part of the network is dangerous. That is what turns an
all-or-nothing transition into avalanches of every size.
"""

import numpy as np
import run_protocol
import networkx as nx

from lattice import (HEALTHY, SHEDDING, DOWN, QUARANTINING, QUARANTINED,
                     DEGRADED, TRANSIENT, REMOVED, SERVING, STATE_NAMES)


# --------------------------------------------------------------------------
# topologies -- all undirected, matched on node count and mean degree
# --------------------------------------------------------------------------

def grid_graph(width, height, neighbourhood="von_neumann"):
    """The lattice, expressed as a graph. Used to verify that this module
    reproduces `LatticeCA` when given the lattice's own neighbourhood."""
    diagonal = neighbourhood == "moore"
    G = nx.grid_2d_graph(height, width, periodic=False)
    if diagonal:
        for y in range(height):
            for x in range(width):
                for dy, dx in ((1, 1), (1, -1)):
                    ny, nx_ = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx_ < width:
                        G.add_edge((y, x), (ny, nx_))
    return nx.convert_node_labels_to_integers(G, ordering="sorted")


def erdos_renyi_graph(n, mean_degree, seed=None):
    """Random graph: degrees are Poisson, so nearly homogeneous. The control
    for 'graph, but without hubs'."""
    p = mean_degree / (n - 1)
    return nx.gnp_random_graph(n, p, seed=seed)


def scale_free_graph(n, m, seed=None):
    """Barabasi-Albert preferential attachment: a heavy-tailed degree
    distribution, so a few cells have very many neighbours."""
    return nx.barabasi_albert_graph(n, m, seed=seed)


def small_world_graph(n, k, p=0.1, seed=None):
    """Watts-Strogatz: lattice-like locally, with a few long-range shortcuts.
    Degrees stay homogeneous, so it isolates path length from degree spread."""
    return nx.watts_strogatz_graph(n, k, p, seed=seed)


# --------------------------------------------------------------------------
# the automaton
# --------------------------------------------------------------------------

class GraphCA:
    """
    Cellular automaton on an arbitrary undirected graph.

    States, transition rule, telemetry and fault process are identical to
    `lattice.LatticeCA`; see that module for the rule in full.

    Parameters
    ----------
    graph : nx.Graph
        The interaction topology. Node labels must be 0..n-1.
    alpha : float
        Spare capacity. capacity = (1 + alpha) * initial load.
    theta : float
        Detector threshold. np.inf disables the detector.
    noise, fault_rate, fault_signal : float
        As in LatticeCA.
    load_mode : "uniform" | "degree"
        "uniform" gives every cell the same initial load, which is the right
        choice for a controlled comparison against the lattice. "degree" makes
        initial load proportional to degree, which is more realistic for a
        service dependency graph where widely-called services carry more
        traffic.
    """

    def __init__(self, graph, alpha=0.3, theta=np.inf, noise=0.0,
                 fault_rate=0.0, fault_signal=0.35, load_mode="uniform",
                 seed=None):
        self.G = graph
        self.n = graph.number_of_nodes()
        self.alpha = alpha
        self.theta = theta
        self.noise = noise
        self.fault_rate = fault_rate
        self.fault_signal = fault_signal
        self.rng = np.random.default_rng(seed)

        self.degree = np.array([max(graph.degree(i), 1) for i in range(self.n)],
                               dtype=float)

        if load_mode == "uniform":
            self.load = np.ones(self.n, dtype=float)
        elif load_mode == "degree":
            d = np.array([graph.degree(i) for i in range(self.n)], dtype=float)
            self.load = d / d.mean()
        else:
            raise ValueError(f"unknown load_mode: {load_mode}")

        self.load0 = self.load.copy()
        self.capacity = (1.0 + alpha) * self.load0
        self.state = np.full(self.n, HEALTHY, dtype=np.int8)

        # adjacency in CSR-like form: neighbours of i are
        # nbr[indptr[i]:indptr[i+1]]. Precomputed because the rule walks it
        # every step.
        nbrs, indptr = [], [0]
        for i in range(self.n):
            nbrs.extend(sorted(graph.neighbors(i)))
            indptr.append(len(nbrs))
        self.nbr = np.array(nbrs, dtype=np.int32)
        self.indptr = np.array(indptr, dtype=np.int32)

        self.t = 0
        self.degraded_cell_steps = 0
        self.n_true_positive = 0
        self.n_false_positive = 0

    # -- rule components ---------------------------------------------------

    def _gather(self):
        """incoming_i = sum over transient neighbours j of load_j / |N(j)|."""
        spill = np.where(np.isin(self.state, TRANSIENT),
                         self.load / self.degree, 0.0)
        incoming = np.zeros(self.n)
        active = np.nonzero(spill)[0]
        for j in active:
            lo, hi = self.indptr[j], self.indptr[j + 1]
            incoming[self.nbr[lo:hi]] += spill[j]
        return incoming

    def telemetry(self):
        util = self.load / self.capacity
        if self.fault_signal:
            util = util + self.fault_signal * (self.state == DEGRADED)
        if self.noise > 0:
            util = util + self.rng.normal(0.0, self.noise, self.n)
        return util

    def step(self):
        """One synchronous update of the whole population."""
        new_load = self.load + self._gather()
        new_state = self.state.copy()

        new_state[self.state == SHEDDING] = DOWN
        new_state[self.state == QUARANTINING] = QUARANTINED
        new_load[np.isin(self.state, TRANSIENT)] = 0.0
        new_load[np.isin(self.state, (DOWN, QUARANTINED))] = 0.0

        if self.fault_rate > 0:
            struck = ((self.state == HEALTHY)
                      & (self.rng.random(self.n) < self.fault_rate))
            new_state[struck] = DEGRADED

        serving = np.isin(self.state, SERVING)
        over = serving & (new_load > self.capacity)
        new_state[over] = SHEDDING

        if np.isfinite(self.theta):
            self.load = new_load
            flagged = serving & ~over & (self.telemetry() > self.theta)
            new_state[flagged] = QUARANTINING
            self.n_true_positive += int(np.count_nonzero(
                flagged & (self.state == DEGRADED)))
            self.n_false_positive += int(np.count_nonzero(
                flagged & (self.state == HEALTHY)))

        self.degraded_cell_steps += int(np.count_nonzero(new_state == DEGRADED))
        changed = int(np.count_nonzero(new_state != self.state))
        self.state, self.load = new_state, new_load
        self.t += 1
        return changed

    def run_for(self, steps):
        """Observe exactly `steps` additional timesteps."""
        return run_protocol.run_for(self, steps)

    def run_until_stable(self, max_steps=5000):
        """Run a deterministic cascade; inspect summary() for the stop reason."""
        return run_protocol.run_until_stable(self, max_steps, TRANSIENT)

    def run(self, max_steps=5000, *, steps=None):
        """Use an explicit window, or deterministic convergence when omitted."""
        return self.run_until_stable(max_steps) if steps is None else self.run_for(steps)

    # -- seeding and measurement ------------------------------------------

    def seed_failure(self, node=None, rng=None):
        """Remove one cell to start a cascade."""
        if node is None:
            rng = self.rng if rng is None else rng
            node = int(rng.integers(self.n))
        self.state[node] = SHEDDING
        return node

    @property
    def n_removed(self):
        return int(np.count_nonzero(np.isin(self.state, REMOVED)))

    @property
    def n_down(self):
        return int(np.count_nonzero(np.isin(self.state, (SHEDDING, DOWN))))

    @property
    def n_quarantined(self):
        return int(np.count_nonzero(
            np.isin(self.state, (QUARANTINING, QUARANTINED))))

    @property
    def removed_fraction(self):
        return self.n_removed / self.n

    def summary(self):
        return {
            "steps": self.t,
            "removed": self.n_removed,
            "overload": self.n_down,
            "quarantined": self.n_quarantined,
            "removed_fraction": self.removed_fraction,
            "degraded_cell_steps": self.degraded_cell_steps,
            "true_positive": self.n_true_positive,
            "false_positive": self.n_false_positive,
            **getattr(self, "_run_info", {}),
        }


# --------------------------------------------------------------------------
# experiment drivers, mirroring lattice.py
# --------------------------------------------------------------------------

def run_trial(graph, alpha, theta=np.inf, noise=0.0, load_mode="uniform",
              seed_node=None, seed=None, *, steps=None):
    """Seed one failure. Stochastic trials require an explicit window."""
    ca = GraphCA(graph, alpha=alpha, theta=theta, noise=noise,
                 load_mode=load_mode, seed=seed)
    node = ca.seed_failure(seed_node)
    history = ca.run(steps=steps)
    out = ca.summary()
    out["seed_node"] = node
    out["seed_degree"] = int(ca.degree[node])
    out["avalanche_size"] = out["removed"] - 1
    out["history"] = history
    out["ca"] = ca
    return out


def run_episode(graph, alpha, theta, steps=150, noise=0.03, fault_rate=2e-4,
                fault_signal=0.35, load_mode="uniform", seed=None):
    """Run under a background fault rate with the detector at `theta`, and
    decompose damage exactly as `lattice.run_episode` does."""
    ca = GraphCA(graph, alpha=alpha, theta=theta, noise=noise,
                 fault_rate=fault_rate, fault_signal=fault_signal,
                 load_mode=load_mode, seed=seed)
    ca.run_for(steps)
    n = ca.n
    unremediated = ca.degraded_cell_steps / n
    overload = ca.n_down / n
    false_positive = ca.n_false_positive / n
    return {
        "theta": theta,
        "unremediated": unremediated,
        "overload": overload,
        "false_positive": false_positive,
        "total_damage": unremediated + overload + false_positive,
        "removed_fraction": ca.removed_fraction,
        "ca": ca,
        **ca._run_info,
    }


def sweep_theta(graph, thetas, alpha=0.6, replicates=8, steps=150, noise=0.03,
                fault_rate=2e-4, fault_signal=0.35, load_mode="uniform",
                seed=0):
    """Sweep detector sensitivity and return the damage decomposition."""
    keys = ("unremediated", "overload", "false_positive", "total_damage")
    out = {k: [] for k in keys}
    out["susceptibility"] = []
    for i, th in enumerate(thetas):
        runs = [run_episode(graph, alpha, th, steps=steps, noise=noise,
                            fault_rate=fault_rate, fault_signal=fault_signal,
                            load_mode=load_mode,
                            seed=seed * 10000 + i * 100 + r)
                for r in range(replicates)]
        for k in keys:
            out[k].append(float(np.mean([r[k] for r in runs])))
        out["susceptibility"].append(
            float(np.var([r["total_damage"] for r in runs])))
    return {k: np.asarray(v) for k, v in out.items()}


def avalanche_sizes(graph, alpha, trials=400, theta=np.inf, noise=0.0,
                    load_mode="uniform", seed=0, *, steps=None):
    """Avalanche size from `trials` independent single-cell failures, together
    with the degree of each seeded cell."""
    rng = np.random.default_rng(seed)
    sizes, degrees = [], []
    for _ in range(trials):
        node = int(rng.integers(graph.number_of_nodes()))
        r = run_trial(graph, alpha, theta=theta, noise=noise,
                      load_mode=load_mode, seed_node=node,
                      seed=int(rng.integers(1 << 30)), steps=steps)
        sizes.append(r["avalanche_size"])
        degrees.append(r["seed_degree"])
    return np.asarray(sizes), np.asarray(degrees)
