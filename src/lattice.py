"""
The autoimmune-remediation model as a cellular automaton on a 2D lattice.

This is the baseline arm of the project. It is a cellular automaton in the
strict sense:

    CELLS           a W x H lattice; each cell is one service instance
    STATES          a finite set {HEALTHY, SHEDDING, DOWN, QUARANTINING,
                    QUARANTINED}
    NEIGHBOURHOOD   von Neumann (4) or Moore (8), identical for every cell
    RULE            one transition function, applied uniformly to every cell
    UPDATE          synchronous -- the whole lattice advances from t to t+1
                    using only the configuration at t

Every cell also carries a real-valued load, which is standard for CA used to
model physical transport (sandpile and forest-fire models carry grain counts
and tree states the same way). The load moves only between lattice neighbours,
so the rule stays local.

THE TRANSITION RULE
-------------------
Written for cell i with neighbourhood N(i), at time t:

  1. incoming(i) = sum over j in N(i) with state_j == SHEDDING
                   of  load_j / |N(j)|
     A cell that has just failed spills its traffic evenly onto its own
     neighbourhood. This is the load-redistribution mechanism.

  2. load_i(t+1) = load_i(t) + incoming(i)

  3. state transitions:
       SHEDDING       -> DOWN            (load set to 0; it has spilled)
       QUARANTINING   -> QUARANTINED     (load set to 0; it has spilled)
       DOWN           -> DOWN            (absorbing)
       QUARANTINED    -> QUARANTINED     (absorbing)
       HEALTHY        -> SHEDDING        if load_i(t+1) > capacity_i
                      -> QUARANTINING    else if telemetry_i > theta
                      -> HEALTHY         otherwise

`SHEDDING` and `QUARANTINING` are one-step transient states, exactly as
`BURNING` is in the forest-fire CA. They exist so that a cell's load can be
handed to its neighbours in the following step using only local information.

The two failure routes are kept distinct in the state set on purpose: DOWN
means the cell genuinely exceeded capacity, QUARANTINED means an automated
detector removed a cell that was still within capacity. Separating them is what
lets the analysis attribute damage to overload versus to the remediation system
itself.

TELEMETRY AND THE DETECTOR
--------------------------
telemetry_i = load_i / capacity_i + noise

A cell absorbing a dead neighbour's traffic runs hotter, and a detector built to
notice unusual utilisation will notice it. Setting `theta` low enough turns the
detector into a second, faster failure route, which is the phenomenon the whole
project is about.

RELATION TO EXISTING CA MODELS
------------------------------
The load-redistribution part is in the same family as the Bak-Tang-Wiesenfeld
sandpile and the Drossel-Schwabl forest-fire CA, both of which spread a local
excess to lattice neighbours. It differs in two ways that matter:

  * Sandpile toppling conserves grains and the cell recovers; here a failed cell
    is removed permanently within an episode, so load concentrates rather than
    diffusing.
  * Neither model has a detector. The quarantine route adds a second removal
    mechanism that is *driven by the state the first mechanism creates*, which
    is the positive feedback loop under study.
"""

import numpy as np
import run_protocol
from random_protocol import RandomProtocol

# --- states ---------------------------------------------------------------
HEALTHY = 0
SHEDDING = 1        # transient: failed by overload, spills load this step
DOWN = 2            # absorbing: removed by overload
QUARANTINING = 3    # transient: removed by the detector, spills load this step
QUARANTINED = 4     # absorbing: removed by the detector
DEGRADED = 5        # a genuine fault: still serving, but faulty and costly

STATE_NAMES = {HEALTHY: "healthy", SHEDDING: "shedding", DOWN: "down",
               QUARANTINING: "quarantining", QUARANTINED: "quarantined",
               DEGRADED: "degraded"}

TRANSIENT = (SHEDDING, QUARANTINING)
REMOVED = (SHEDDING, DOWN, QUARANTINING, QUARANTINED)
SERVING = (HEALTHY, DEGRADED)       # cells still carrying load

VON_NEUMANN = ((-1, 0), (1, 0), (0, -1), (0, 1))
MOORE = VON_NEUMANN + ((-1, -1), (-1, 1), (1, -1), (1, 1))


class LatticeCA:
    """
    Cellular automaton on a W x H lattice with fixed (non-periodic) boundaries.

    Parameters
    ----------
    width, height : int
    alpha : float
        Spare capacity. capacity = (1 + alpha) * initial load.
    neighbourhood : "von_neumann" | "moore"
    theta : float
        Detector threshold on telemetry. np.inf disables the detector, which
        reduces the model to a pure load-redistribution CA.
    noise : float
        Standard deviation of telemetry noise, which is what makes the detector
        imperfect and produces false positives.
    load_sigma : float
        Lognormal spread of initial per-cell load. 0 gives a uniform lattice.
    seed : int | None
    randomness : "legacy" | "split"
        "legacy" preserves the shared self.rng draw order. "split" separates
        initialization, perturbation, faults and telemetry; potential faults
        and noise are indexed by absolute timestep and flat row-major cell ID.
    stream_seeds : mapping | None
        Optional nonnegative integer seeds for named split streams. Record
        random_info() to replay a run, including one started with seed=None.
    redistribution : "legacy" | "serving_neighbours"
        "legacy" shares across all static neighbours and records cleared
        shares as dropped load. "serving_neighbours" shares only across
        HEALTHY or DEGRADED neighbours at the start of the step. With no
        eligible recipient, the donor's load is dropped in full.
    """

    def __init__(self, width=60, height=60, alpha=0.3,
                 neighbourhood="von_neumann", theta=np.inf, noise=0.0,
                 load_sigma=0.0, fault_rate=0.0, fault_signal=0.35,
                 seed=None, *, redistribution="legacy",
                 randomness="legacy", stream_seeds=None):
        if redistribution not in ("legacy", "serving_neighbours"):
            raise ValueError(f"unknown redistribution: {redistribution}")
        self.redistribution = redistribution
        self.w, self.h = width, height
        self.alpha = alpha
        self.theta = theta
        self.noise = noise
        self.fault_rate = fault_rate
        self.fault_signal = fault_signal
        self._random = RandomProtocol(seed, randomness, stream_seeds)
        self.randomness = randomness
        self.rng = np.random.default_rng(self._random.seed)

        # cumulative damage, attributed to its source
        self.degraded_cell_steps = 0    # faults left unremediated
        self.n_true_positive = 0        # degraded cells the detector removed
        self.n_false_positive = 0       # healthy cells the detector removed

        offsets = {"von_neumann": VON_NEUMANN, "moore": MOORE}
        if neighbourhood not in offsets:
            raise ValueError(f"unknown neighbourhood: {neighbourhood}")
        self.neighbourhood = neighbourhood
        self.offsets = offsets[neighbourhood]

        self.state = np.full((height, width), HEALTHY, dtype=np.int8)
        if load_sigma > 0:
            rng = self.rng if randomness == "legacy" else self._random.initialization
            self.load = rng.lognormal(0.0, load_sigma, (height, width))
        else:
            self.load = np.ones((height, width), dtype=float)
        self.load0 = self.load.copy()
        self.initial_load = float(self.load.sum())
        self.dropped_load = 0.0
        self.capacity = (1.0 + alpha) * self.load0

        # |N(j)| for every cell -- smaller on edges and corners, since the
        # lattice does not wrap. Precomputed because the rule divides by it.
        self.degree = self._neighbour_counts()
        self.t = 0

    # -- lattice helpers ---------------------------------------------------

    def _shifted(self, arr, dy, dx, fill):
        """`arr` translated by (dy, dx), with `fill` shifted in at the edges.

        A cell reading `_shifted(arr, dy, dx)[y, x]` gets the value held by its
        neighbour at (y+dy, x+dx), so every quantity the rule needs is obtained
        by shifting whole arrays rather than looping over cells.
        """
        out = np.full_like(arr, fill)
        ys_src = slice(max(dy, 0), self.h + min(dy, 0))
        ys_dst = slice(max(-dy, 0), self.h + min(-dy, 0))
        xs_src = slice(max(dx, 0), self.w + min(dx, 0))
        xs_dst = slice(max(-dx, 0), self.w + min(-dx, 0))
        out[ys_dst, xs_dst] = arr[ys_src, xs_src]
        return out

    def _neighbour_counts(self):
        """How many lattice neighbours each cell actually has."""
        ones = np.ones((self.h, self.w))
        total = np.zeros((self.h, self.w))
        for dy, dx in self.offsets:
            total += self._shifted(ones, dy, dx, 0.0)
        return total

    # -- the transition rule ----------------------------------------------

    def telemetry(self):
        """
        Observed utilisation. The signal the detector acts on.

        Three contributions, and the overlap between them is the whole problem:
          * utilisation -- rises when a cell absorbs a dead neighbour's traffic
          * a fault offset -- a genuinely degraded cell looks worse
          * noise -- which makes the two populations overlap, so no threshold
            can separate them cleanly
        """
        # Apply the same zero-capacity convention as the graph model.
        util = np.divide(self.load, self.capacity, out=np.zeros_like(self.load),
                         where=self.capacity != 0)
        util[(self.capacity == 0) & (self.load > 0)] = np.inf
        if self.fault_signal:
            util = util + self.fault_signal * (self.state == DEGRADED)
        if self.noise > 0:
            if self.randomness == "split":
                util = util + self.noise * self._random.field(
                    "telemetry", self.t, self.state.shape)
            else:
                util = util + self.rng.normal(0.0, self.noise, util.shape)
        return util

    def step(self):
        """
        Advance the whole lattice one timestep.

        Returns the number of cells that changed state, so a caller can detect
        a fixed point.
        """
        # 1. gather load spilled by neighbours that failed on the previous step
        transient = np.isin(self.state, TRANSIENT)
        absorbing = np.isin(self.state, (DOWN, QUARANTINED))
        serving = np.isin(self.state, SERVING)
        recipients = self.degree
        if self.redistribution == "serving_neighbours":
            recipients = np.zeros_like(self.load)
            for dy, dx in self.offsets:
                recipients += self._shifted(serving, dy, dx, False)
        incoming = np.zeros_like(self.load)
        spill = np.where(transient,
                         self.load / np.maximum(recipients, 1), 0.0)
        for dy, dx in self.offsets:
            incoming += self._shifted(spill, dy, dx, 0.0)
        if self.redistribution == "serving_neighbours":
            incoming[~serving] = 0.0

        # Cleared incoming shares and unroutable donor load leave the system.
        self.dropped_load += float(
            incoming[transient | absorbing].sum()
            + self.load[transient & (recipients == 0)].sum()
            + self.load[absorbing].sum())
        new_load = self.load + incoming
        new_state = self.state.copy()

        # 2. transient states finish: they are now removed and carry nothing
        new_state[self.state == SHEDDING] = DOWN
        new_state[self.state == QUARANTINING] = QUARANTINED
        new_load[np.isin(self.state, TRANSIENT)] = 0.0
        new_load[np.isin(self.state, (DOWN, QUARANTINED))] = 0.0

        # 3. new faults appear independently among serving cells
        if self.fault_rate > 0:
            healthy_now = self.state == HEALTHY
            potential = (self._random.field("faults", self.t, self.state.shape)
                         if self.randomness == "split"
                         else self.rng.random(self.state.shape))
            struck = healthy_now & (potential < self.fault_rate)
            new_state[struck] = DEGRADED

        # 4. every serving cell applies the local rule. Overload is checked
        #    first: a cell over capacity fails whatever the detector thinks.
        over = serving & (new_load > self.capacity)
        new_state[over] = SHEDDING

        if np.isfinite(self.theta):
            self.load = new_load          # telemetry reads the updated load
            flagged = serving & ~over & (self.telemetry() > self.theta)
            new_state[flagged] = QUARANTINING
            # attribute each removal: was the cell actually faulty?
            self.n_true_positive += int(np.count_nonzero(
                flagged & (self.state == DEGRADED)))
            self.n_false_positive += int(np.count_nonzero(
                flagged & (self.state == HEALTHY)))

        # 5. faults left in place cost something every step they persist
        self.degraded_cell_steps += int(np.count_nonzero(new_state == DEGRADED))

        changed = int(np.count_nonzero(new_state != self.state))
        self.state, self.load = new_state, new_load
        self.t += 1
        return changed

    def run_for(self, steps):
        """Observe exactly `steps` additional timesteps."""
        return run_protocol.run_for(self, steps)

    def run_until_stable(self, max_steps=2000):
        """Run a deterministic cascade; inspect summary() for the stop reason."""
        return run_protocol.run_until_stable(self, max_steps, TRANSIENT)

    def run(self, max_steps=2000, *, steps=None):
        """Use an explicit window, or deterministic convergence when omitted."""
        return self.run_until_stable(max_steps) if steps is None else self.run_for(steps)

    # -- seeding and measurement ------------------------------------------

    def seed_failure(self, y=None, x=None):
        """Remove one cell to start a cascade. Defaults to the lattice centre,
        which keeps the neighbourhood full and avoids a boundary artefact."""
        y = self.h // 2 if y is None else y
        x = self.w // 2 if x is None else x
        self.state[y, x] = SHEDDING
        return y, x

    @property
    def n_cells(self):
        return self.w * self.h

    @property
    def n_removed(self):
        return int(np.count_nonzero(np.isin(self.state, REMOVED)))

    @property
    def n_down(self):
        """Cells lost to genuine overload."""
        return int(np.count_nonzero(np.isin(self.state, (SHEDDING, DOWN))))

    @property
    def n_quarantined(self):
        """Cells removed by the detector."""
        return int(np.count_nonzero(
            np.isin(self.state, (QUARANTINING, QUARANTINED))))

    @property
    def n_degraded(self):
        """Faults currently present and unremediated."""
        return int(np.count_nonzero(self.state == DEGRADED))

    @property
    def removed_fraction(self):
        return self.n_removed / self.n_cells

    def random_inputs(self, step=None):
        """Potential inputs for an absolute step (default: current t), split only.

        Returns fresh full-population arrays without advancing any generator.
        Repeated telemetry at a fixed t uses this same standardized noise.
        """
        return self._random.inputs(self.t if step is None else step, self.state.shape)

    def random_info(self):
        """Serializable protocol version, actual root seed and stream seeds."""
        return self._random.info()

    def summary(self):
        return {
            "steps": self.t,
            "random_info": self.random_info(),
            "removed": self.n_removed,
            "overload": self.n_down,
            "quarantined": self.n_quarantined,
            "degraded": self.n_degraded,
            "removed_fraction": self.removed_fraction,
            "degraded_cell_steps": self.degraded_cell_steps,
            "true_positive": self.n_true_positive,
            "false_positive": self.n_false_positive,
            **self.load_accounting(),
            **getattr(self, "_run_info", {}),
        }

    def load_accounting(self):
        """Current load includes transient cells awaiting their next transfer."""
        current = float(self.load.sum())
        return {"redistribution": self.redistribution,
                "initial_load": self.initial_load, "current_load": current,
                "dropped_load": self.dropped_load,
                "load_balance_error": self.initial_load - current - self.dropped_load}


def run_episode(alpha, theta, steps=150, width=50, height=50,
                neighbourhood="von_neumann", noise=0.03, load_sigma=0.0,
                fault_rate=2e-4, fault_signal=0.35, seed=None, *,
                redistribution="legacy", randomness="legacy", stream_seeds=None):
    """
    Run a platform for a fixed number of steps under a background fault rate,
    with the detector operating at threshold `theta`.

    Unlike `run_trial`, nothing is seeded: every failure originates either from
    a fault the process generated or from the remediation system's own actions.

    Damage is decomposed into the three sources the project distinguishes:

      unremediated   cell-steps spent degraded and undetected, normalised by
                     the lattice size -- the cost of missing a genuine fault
      overload       cells lost because they genuinely exceeded capacity
      false_positive cells removed by the detector while healthy and within
                     capacity -- the self-inflicted damage

    Total damage weights unremediated fault-time and lost cells equally, so the
    three components are directly comparable on one axis.
    """
    ca = LatticeCA(width=width, height=height, alpha=alpha,
                   neighbourhood=neighbourhood, theta=theta, noise=noise,
                   load_sigma=load_sigma, fault_rate=fault_rate,
                   fault_signal=fault_signal, seed=seed,
                   redistribution=redistribution, randomness=randomness,
                   stream_seeds=stream_seeds)
    ca.run_for(steps)

    n = ca.n_cells
    unremediated = ca.degraded_cell_steps / n
    overload = ca.n_down / n
    false_positive = ca.n_false_positive / n
    return {
        "theta": theta,
        "alpha": alpha,
        "unremediated": unremediated,
        "overload": overload,
        "false_positive": false_positive,
        "true_positive": ca.n_true_positive / n,
        "total_damage": unremediated + overload + false_positive,
        "removed_fraction": ca.removed_fraction,
        "ca": ca,
        "random_info": ca.random_info(),
        **ca.load_accounting(),
        **ca._run_info,
    }


def sweep_theta(thetas, alpha=0.6, replicates=8, steps=150, width=50,
                height=50, neighbourhood="von_neumann", noise=0.03,
                fault_rate=2e-4, fault_signal=0.35, seed=0, *,
                redistribution="legacy", randomness="legacy"):
    """
    Sweep detector sensitivity and return the damage decomposition.

    Returns a dict of arrays, each aligned with `thetas`: the three damage
    components, the total, and the variance of the total across replicates
    (the susceptibility, which peaks at a transition).

    Split mode pairs replicate r across thresholds using seed*10000 + r.
    Legacy retains independent threshold schedules seed*10000 + i*100 + r.
    Stream overrides are intentionally unavailable for aggregate helpers:
    fixed overrides would repeat identical streams across replicates.
    """
    keys = ("unremediated", "overload", "false_positive", "total_damage")
    out = {k: [] for k in keys}
    out["susceptibility"] = []

    for i, th in enumerate(thetas):
        base_seed = seed * 10000 + (i * 100 if randomness == "legacy" else 0)
        runs = [run_episode(alpha, th, steps=steps, width=width, height=height,
                            neighbourhood=neighbourhood, noise=noise,
                            fault_rate=fault_rate, fault_signal=fault_signal,
                            seed=base_seed + r,
                            redistribution=redistribution, randomness=randomness)
                for r in range(replicates)]
        for k in keys:
            out[k].append(float(np.mean([r[k] for r in runs])))
        out["susceptibility"].append(
            float(np.var([r["total_damage"] for r in runs])))

    return {k: np.asarray(v) for k, v in out.items()}


def run_trial(alpha, width=60, height=60, neighbourhood="von_neumann",
              theta=np.inf, noise=0.0, load_sigma=0.0, seed=None, *, steps=None,
              redistribution="legacy", randomness="legacy", stream_seeds=None):
    """Seed the centre cell. Stochastic trials require an explicit window."""
    ca = LatticeCA(width=width, height=height, alpha=alpha,
                   neighbourhood=neighbourhood, theta=theta, noise=noise,
                   load_sigma=load_sigma, seed=seed,
                   redistribution=redistribution, randomness=randomness,
                   stream_seeds=stream_seeds)
    ca.seed_failure()
    history = ca.run(steps=steps)
    out = ca.summary()
    out["history"] = history
    out["avalanche_size"] = out["removed"] - 1
    out["ca"] = ca
    return out


def sweep_alpha(alphas, replicates=10, width=60, height=60,
                neighbourhood="von_neumann", theta=np.inf, noise=0.0,
                load_sigma=0.3, seed=0, *, steps=None, redistribution="legacy",
                randomness="legacy"):
    """Sweep spare capacity. Returns mean removed fraction, its standard
    deviation, and susceptibility (variance across replicates).

    Both modes reuse seed*1000 + r across alpha values. Split mode keeps each
    replicate's potential inputs aligned even when its trajectories differ.
    Fixed stream overrides are excluded to preserve distinct replicates.
    """
    mean, std, susceptibility = [], [], []
    for a in alphas:
        vals = [run_trial(a, width, height, neighbourhood, theta, noise,
                          load_sigma, seed=seed * 1000 + r, steps=steps,
                          redistribution=redistribution,
                          randomness=randomness)["removed_fraction"]
                for r in range(replicates)]
        vals = np.asarray(vals)
        mean.append(vals.mean())
        std.append(vals.std())
        susceptibility.append(vals.var())
    return (np.asarray(mean), np.asarray(std), np.asarray(susceptibility))
