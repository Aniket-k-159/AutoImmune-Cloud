"""
Agent-based formulation of the platform.

This module makes the agent architecture explicit. The physics is identical to
`cascade.py` -- it is verified against it -- but the control flow is written the
way an agent-based model is normally presented, so the paradigm is visible in
the code rather than inferred from it.

    AGENT        one service replica
    STATE        HEALTHY | OVERLOADED | QUARANTINED
    ENVIRONMENT  the role dependency graph
    NEIGHBOURS   peers in the same role, plus callers and callees
    SCHEDULE     synchronous -- every agent observes, then every agent decides,
                 then every agent acts

Each agent acts on LOCAL information only:

  * the demand routed to its own role, and how many peers are alive to share it
  * whether the roles it depends on are answering

No agent has access to platform-wide state, and no rule mentions cascades.
Cascades, the critical threshold, and heavy-tailed avalanche sizes are all
emergent.

Timescale separation (assumption A4): load is taken to re-equilibrate faster
than services fail, so demand is propagated to a fixed point between successive
rounds of failure decisions. The propagation itself is local message passing --
each agent forwards load only to its direct dependencies -- iterated until
stable.
"""

import numpy as np

HEALTHY = "healthy"
OVERLOADED = "overloaded"
QUARANTINED = "quarantined"

DOWN_STATES = (OVERLOADED, QUARANTINED)


class ServiceAgent:
    """One replica of a role. Sees only its own local neighbourhood."""

    __slots__ = ("id", "role", "state", "load", "capacity", "_next_state")

    def __init__(self, node_id, role):
        self.id = node_id
        self.role = role
        self.state = HEALTHY
        self.load = 0.0
        self.capacity = float("inf")
        self._next_state = HEALTHY

    @property
    def is_up(self):
        return self.state == HEALTHY

    @property
    def load_ratio(self):
        """Utilisation. The quantity a telemetry signal will be built on in
        step 3 -- a big service at 40% is not anomalous, a small one at 95% is."""
        return self.load / self.capacity if self.capacity > 0 else 0.0

    # -- the three phases of a synchronous agent update --------------------

    def observe(self, world):
        """Read local state: my share of my role's demand, including any retry
        penalty my role pays for dependencies that are not answering."""
        self.load = world.local_load(self)

    def decide(self):
        """Local rule. The only rule an agent has in the baseline model:
        if my load exceeds my capacity, I fail."""
        if self.state == HEALTHY and self.load > self.capacity + 1e-12:
            self._next_state = OVERLOADED
        else:
            self._next_state = self.state

    def act(self):
        """Commit the decision. Separated from decide() so the update is
        synchronous -- no agent sees another agent's move within the same step."""
        self.state = self._next_state

    def __repr__(self):
        return (f"ServiceAgent(id={self.id}, role={self.role}, "
                f"state={self.state}, load={self.load:.1f})")


class World:
    """
    The environment the agents inhabit: the role dependency graph, the
    role -> replica membership, and the message-passing routine that turns
    external arrivals into per-agent load.
    """

    def __init__(self, platform, external_rate=100.0, retry_cost=0.0):
        self.P = platform
        self.external_rate = external_rate
        self.retry_cost = retry_cost
        self.agents = {n: ServiceAgent(n, platform.role_of[n])
                       for n in platform.nodes}
        self.t = 0
        self._demand = {}
        self._penalty = {}
        self._dead_roles = set()
        self._live_count = {}

    # -- accessors ---------------------------------------------------------

    @property
    def down(self):
        return {a.id for a in self.agents.values() if not a.is_up}

    def live_peers(self, agent):
        """Agents in the same role that are still serving. A local view."""
        return [self.agents[i] for i in self.P.members[agent.role]
                if self.agents[i].is_up]

    def reset(self):
        """Return every agent to HEALTHY, keeping capacities. Lets a single
        World be reused across trials instead of rebuilt each time."""
        for a in self.agents.values():
            a.state = HEALTHY
            a._next_state = HEALTHY
        self.t = 0

    def dead_dependencies(self, agent):
        """Roles this agent calls that have no live replica left."""
        return [r for r in self.P.roles.successors(agent.role)
                if r in self._dead_roles]

    # -- message passing ---------------------------------------------------

    def equilibrate(self, max_iter=500, tol=1e-9):
        """
        Propagate demand to a fixed point by local message passing.

        Each role forwards load only to its direct dependencies, weighted by
        call multiplicity. A role with no live replicas is dead: it forwards
        nothing, and every caller pays `retry_cost` per failed call in held
        threads and connections.
        """
        G = self.P.roles
        # one pass over the population: how many replicas of each role are up
        live = {r: 0 for r in G.nodes()}
        for a in self.agents.values():
            if a.state == HEALTHY:
                live[a.role] += 1
        self._live_count = live
        self._dead_roles = {r for r, n in live.items() if n == 0}
        entries = set(self.P.entry_roles)

        D = {r: (self.external_rate if r in entries else 0.0) for r in G.nodes()}
        for _ in range(max_iter):
            new = {r: (self.external_rate if r in entries else 0.0)
                   for r in G.nodes()}
            for c in G.nodes():                      # each role sends messages
                if c in self._dead_roles or D[c] == 0.0:
                    continue
                for t in G.successors(c):            # ...only to its own deps
                    if t not in self._dead_roles:
                        new[t] += D[c] * G[c][t]["w"]
            delta = max(abs(new[r] - D[r]) for r in G.nodes())
            D = new
            if delta < tol:
                break
        else:
            raise RuntimeError("demand propagation did not converge")

        self._penalty = {r: 0.0 for r in G.nodes()}
        if self.retry_cost > 0.0:
            for c in G.nodes():
                if c in self._dead_roles:
                    continue
                for t in G.successors(c):
                    if t in self._dead_roles:
                        self._penalty[c] += D[c] * G[c][t]["w"] * self.retry_cost
        self._demand = D

    def local_load(self, agent):
        """An agent's share: its role's demand plus retry penalty, split across
        whichever peers are still alive.

        Uses the live-peer count cached by the most recent equilibrate(), which
        is local information -- how many siblings answered the last health
        check -- not a platform-wide view."""
        if agent.state != HEALTHY:
            return 0.0
        n_live = self._live_count.get(agent.role, 0)
        if n_live == 0:
            return 0.0
        return (self._demand[agent.role] + self._penalty[agent.role]) / n_live

    # -- the agent loop ----------------------------------------------------

    def set_capacity(self, alpha):
        """Capacity is provisioned from the intact load: C = (1+alpha) L."""
        self.equilibrate()
        for a in self.agents.values():
            a.observe(self)
            a.capacity = (1.0 + alpha) * a.load

    def step(self):
        """
        One synchronous round: observe, decide, act.

        Returns the number of agents that changed state, so a caller can detect
        the fixed point.
        """
        self.equilibrate()
        for a in self.agents.values():
            a.observe(self)
        for a in self.agents.values():
            a.decide()
        changed = sum(1 for a in self.agents.values()
                      if a._next_state != a.state)
        for a in self.agents.values():
            a.act()
        self.t += 1
        return changed

    def run(self, max_steps=500):
        """Iterate the agent loop until no agent changes state."""
        history = [len(self.down)]
        for _ in range(max_steps):
            if self.step() == 0:
                break
            history.append(len(self.down))
        else:
            raise RuntimeError("agent loop did not reach a fixed point")
        return history

    # -- measurement -------------------------------------------------------

    def served_fraction(self, baseline_total):
        self.equilibrate()
        total = sum(self.local_load(a) for a in self.agents.values())
        return total / baseline_total if baseline_total > 0 else 0.0

    def snapshot(self):
        """Per-agent state and utilisation. Used for cascade timelines and for
        the telemetry signal in step 3."""
        return {a.id: (a.state, a.load, a.load_ratio)
                for a in self.agents.values()}


def run_trial(platform, alpha, trigger="random", rng=None, external_rate=100.0,
              retry_cost=0.0, world=None):
    """
    One cascade trial, expressed as an agent simulation.

    Capacity is provisioned from the intact load, one agent is removed, and the
    agent loop runs to a fixed point.

    `world` may be passed to reuse an existing population across trials, which
    avoids rebuilding every agent each time. It is reset and re-provisioned
    before the trial, so results are identical either way.
    """
    rng = np.random.default_rng() if rng is None else rng
    if world is None:
        world = World(platform, external_rate=external_rate,
                      retry_cost=retry_cost)
    else:
        world.reset()
    world.set_capacity(alpha)

    baseline_total = sum(a.load for a in world.agents.values())

    if trigger == "hub":
        busiest = max(platform.roles.nodes(),
                      key=lambda r: sum(world.agents[i].load
                                        for i in platform.members[r]))
        seed = platform.members[busiest][0]
    elif trigger == "random":
        seed = int(rng.choice(platform.nodes))
    else:
        raise ValueError(f"unknown trigger: {trigger}")

    world.agents[seed].state = QUARANTINED
    history = world.run()

    down = world.down
    return {
        "world": world,
        "failed": down,
        "overloaded": {a.id for a in world.agents.values()
                       if a.state == OVERLOADED},
        "dead_roles": world._dead_roles,
        "rounds": len(history) - 1,
        "history": history,
        "seed_node": seed,
        "failed_fraction": len(down) / platform.n_nodes,
        "avalanche_size": len(down) - 1,
        "served_fraction": world.served_fraction(baseline_total),
    }


def sweep_alpha(platform, alphas, trigger="random", replicates=30, seed=0,
                external_rate=100.0, retry_cost=0.0):
    """Sweep spare capacity. Returns mean failed fraction, its standard
    deviation, mean served fraction, and susceptibility."""
    rng = np.random.default_rng(seed)
    mean_failed, std_failed, mean_served, susceptibility = [], [], [], []
    world = World(platform, external_rate=external_rate, retry_cost=retry_cost)

    for a in alphas:
        fracs, served = [], []
        for _ in range(replicates):
            r = run_trial(platform, a, trigger=trigger, rng=rng,
                          external_rate=external_rate, retry_cost=retry_cost,
                          world=world)
            fracs.append(r["failed_fraction"])
            served.append(r["served_fraction"])
        fracs = np.asarray(fracs)
        mean_failed.append(fracs.mean())
        std_failed.append(fracs.std())
        mean_served.append(float(np.mean(served)))
        susceptibility.append(fracs.var())

    return (np.asarray(mean_failed), np.asarray(std_failed),
            np.asarray(mean_served), np.asarray(susceptibility))
