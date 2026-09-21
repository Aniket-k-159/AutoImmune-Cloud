"""
Dependency graph generation, replica roles, and steady-state load propagation.

A microservice platform is modelled at two levels:

  ROLE   a logical service ("auth", "orders") that callers address
  NODE   one replica instance of that role, which is what actually fails

An edge role_a -> role_b means "a calls b". Requests enter at entry roles and
propagate downstream, amplified by per-edge call multiplicity.

The two-level structure is what makes cascades possible. Load addressed to a
role is split evenly across its LIVE replicas, so removing one replica raises
the load on its surviving peers. In a single-level DAG nothing redistributes at
all -- removing a node simply removes its traffic -- and no cascade can occur.

Two redistribution mechanisms follow from this:

  LATERAL   a replica dies, its share moves to surviving peers in the same role
  UPSTREAM  a role loses ALL replicas, so calls to it fail; callers retry,
            holding threads and connections through each timeout, which raises
            the callers' own effective load
"""

import numpy as np
import networkx as nx


# --------------------------------------------------------------------------
# role-level topology generators
# --------------------------------------------------------------------------

def _assign_edge_weights(G, rng, lo=0.6, hi=1.6):
    """Call multiplicity: expected calls to role j per request served by i."""
    for u, v in G.edges():
        G[u][v]["w"] = rng.uniform(lo, hi)
    return G


def build_ba_roles(n_roles=80, m=2, seed=None):
    """Scale-free role graph. Oriented new -> old, giving heavy-tailed in-degree."""
    rng = np.random.default_rng(seed)
    und = nx.barabasi_albert_graph(n_roles, m, seed=int(rng.integers(1 << 30)))
    G = nx.DiGraph()
    G.add_nodes_from(range(n_roles))
    for u, v in und.edges():
        caller, callee = (u, v) if u > v else (v, u)
        G.add_edge(caller, callee)
    return _assign_edge_weights(G, rng)


def build_er_roles(n_roles=80, mean_degree=4.0, seed=None):
    """Random role graph, matched on role count and mean degree."""
    rng = np.random.default_rng(seed)
    p = mean_degree / (n_roles - 1)
    G = nx.DiGraph()
    G.add_nodes_from(range(n_roles))
    for i in range(n_roles):
        for j in range(i):
            if rng.random() < p:
                G.add_edge(i, j)
    return _assign_edge_weights(G, rng)


def build_layered_roles(layer_sizes=(6, 16, 30, 18, 10), fanout=3, seed=None):
    """
    Layered role graph: gateway -> business logic -> platform -> data.

    Each role calls `fanout` roles in the next layer, chosen by preferential
    attachment so shared services emerge, plus occasional skip-layer calls.
    Bounded depth keeps load amplification realistic.
    """
    rng = np.random.default_rng(seed)
    G = nx.DiGraph()
    layers, rid = [], 0
    for size in layer_sizes:
        layers.append(list(range(rid, rid + size)))
        rid += size
    G.add_nodes_from(range(rid))
    for li in range(len(layers) - 1):
        targets = layers[li + 1]
        skip = layers[li + 2] if li + 2 < len(layers) else None
        counts = np.ones(len(targets))
        for caller in layers[li]:
            k = min(fanout, len(targets))
            chosen = rng.choice(len(targets), size=k, replace=False,
                                p=counts / counts.sum())
            for idx in chosen:
                G.add_edge(caller, targets[idx])
                counts[idx] += 1.0
            if skip is not None and rng.random() < 0.25:
                G.add_edge(caller, int(skip[rng.integers(len(skip))]))
    for r in G.nodes():
        G.nodes[r]["layer"] = next(i for i, L in enumerate(layers) if r in L)
    return _assign_edge_weights(G, rng)


# --------------------------------------------------------------------------
# replicas
# --------------------------------------------------------------------------

class Platform:
    """
    A role graph plus its replica instances.

    Attributes
    ----------
    roles       nx.DiGraph over role ids, edge attribute 'w'
    members     {role: [node ids]} -- the replicas of each role
    role_of     {node: role}
    nodes       list of all replica node ids
    """

    def __init__(self, role_graph, replicas=3, jitter=1, seed=None):
        rng = np.random.default_rng(seed)
        self.roles = role_graph
        self.members, self.role_of = {}, {}
        nid = 0
        for r in role_graph.nodes():
            k = max(1, replicas + int(rng.integers(-jitter, jitter + 1)))
            ids = list(range(nid, nid + k))
            nid += k
            self.members[r] = ids
            for i in ids:
                self.role_of[i] = r
        self.nodes = list(range(nid))
        self.entry_roles = [r for r in role_graph.nodes()
                            if role_graph.in_degree(r) == 0]

    @property
    def n_nodes(self):
        return len(self.nodes)

    @property
    def n_roles(self):
        return self.roles.number_of_nodes()

    def live_members(self, role, down):
        return [i for i in self.members[role] if i not in down]


def propagate_load(P, external_rate=100.0, down=None, retry_cost=0.0,
                   max_iter=500, tol=1e-9):
    """
    Steady-state per-replica load.

    Role-level demand:
        D_r = e_r + sum over live caller roles c of D_c * w_cr

    Per-replica load is that demand split across the role's LIVE replicas, so
    losing a replica raises the load on its peers. A role with no live replicas
    is dead: calls to it fail, and each caller pays `retry_cost` per failed call
    in held resources, which raises the caller's own effective load.

    Parameters
    ----------
    P : Platform
    down : set of replica node ids that are removed (failed or quarantined)
    retry_cost : float
        Resource cost to a caller of one failed call, as a multiple of the call
        rate. 0 disables upstream amplification.

    Returns
    -------
    (load, dead_roles) : per-replica load dict, and the set of roles with no
    live replicas.
    """
    down = set() if down is None else set(down)
    G = P.roles

    dead_roles = {r for r in G.nodes() if not P.live_members(r, down)}
    entries = set(P.entry_roles)

    D = {r: (external_rate if r in entries else 0.0) for r in G.nodes()}
    for _ in range(max_iter):
        new = {r: (external_rate if r in entries else 0.0) for r in G.nodes()}
        for c in G.nodes():
            if c in dead_roles or D[c] == 0.0:
                continue
            for t in G.successors(c):
                if t not in dead_roles:
                    new[t] += D[c] * G[c][t]["w"]
        delta = max(abs(new[r] - D[r]) for r in G.nodes())
        D = new
        if delta < tol:
            break
    else:
        raise RuntimeError("load propagation did not converge")

    # retry penalty: a caller of a dead role holds resources on every failed call
    penalty = {r: 0.0 for r in G.nodes()}
    if retry_cost > 0.0:
        for c in G.nodes():
            if c in dead_roles:
                continue
            for t in G.successors(c):
                if t in dead_roles:
                    penalty[c] += D[c] * G[c][t]["w"] * retry_cost

    load = {}
    for r in G.nodes():
        live = P.live_members(r, down)
        if not live:
            for i in P.members[r]:
                load[i] = 0.0
            continue
        share = (D[r] + penalty[r]) / len(live)
        for i in P.members[r]:
            load[i] = share if i not in down else 0.0
    return load, dead_roles


def assign_capacity(load, alpha):
    """C_i = (1 + alpha) L_i, fixed at t=0 from the intact load.
    alpha is spare capacity -- the control parameter for the cascade."""
    return {n: (1.0 + alpha) * l for n, l in load.items()}


def build_platform(kind="layered", replicas=3, seed=None, **kw):
    """Convenience constructor. kind in {'layered', 'ba', 'er'}."""
    builders = {"layered": build_layered_roles,
                "ba": build_ba_roles,
                "er": build_er_roles}
    if kind not in builders:
        raise ValueError(f"unknown kind: {kind}")
    return Platform(builders[kind](seed=seed, **kw), replicas=replicas,
                    seed=seed)
