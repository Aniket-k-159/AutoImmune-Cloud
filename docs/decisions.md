# Decisions log

## D1. Edge orientation in the BA generator
Preferential attachment is undirected. Oriented new -> old so early-arriving
nodes become high IN-degree shared services (auth, config, data). Reproduces the
observed microservice pattern and keeps the graph acyclic.

## D2. Iterative load solver rather than topological
The graphs are DAGs, so a topological pass is exact and cheaper. The iterative
fixed-point solver is used anyway so the same code still works if cycles are
introduced later (retry loops, sidecar meshes). Validated against the exact
solution: max relative error 4e-16.

## D3. Fan-out amplification — use the layered graph as primary
Load is multiplicative (`L_j = sum_i L_i * w_ij`, `w ~ U(0.6, 1.6)`), so it
compounds along call chains. Measured amplification over injected load: BA 148x
(longest chain 15 hops), Layered 57x (4 hops), ER 41x (10 hops). Direction is
correct — data-layer services do serve far more QPS than gateways — but the BA
magnitude is driven by chain depth rather than by anything realistic.

Decision: the **layered** graph is the primary topology for the main
experiments; its bounded depth keeps amplification reasonable and it is the
realistic generator. BA and ER are retained for the topology-comparison arm,
where extreme concentration is precisely the finding. Damage is reported both as
a fraction of nodes and as a share of served work, so concentration stays
visible rather than hidden.

## D4. Notebook as the primary deliverable
Analysis lives in `notebooks/`, numbered by build step, each ending in a
validation gate. Reusable model code is duplicated into `src/` as importable
modules once it stops changing, so later sweeps can run headless. Long parameter
sweeps run as scripts in `experiments/`, never inside a notebook cell.

## D5. Attack layer removed (post-Checkpoint 1)
The facilitator judged the original three-layer design (worm + cascade +
detector) too complex for a solo project. The attack layer has been removed
entirely: lateral movement, trust edges, stealth levels, image diversity, and
the adaptive attacker.

A **background fault process** replaces it — each service degrades independently
with probability `p` per timestep. This preserves the detection trade-off (the
detector still has a genuine job, and missing a fault has a real cost) without
simulating any spreading mechanics.

Rationale: epidemic spreading on a network is thoroughly published and was the
part contributing least novelty. The autoimmune loop — false positive triggers
load redistribution triggers more false positives — is the contribution, and it
survives intact. The project now has one control parameter (`theta`), one order
parameter (damage), and a cleaner two-parameter phase diagram.

## D6. Telemetry coupled to load ratio, not absolute load
Telemetry score is a function of `L_i / C_i` rather than `L_i`. A large service
running at 40% is not anomalous; a small one at 95% is. Using the ratio makes
the detector's behaviour independent of node size, which matters on the
scale-free graph where loads span several orders of magnitude.

Consequence: this is the parameter the whole result hangs on, so a sensitivity
analysis on the coupling strength is mandatory rather than optional. Logged in
`assumptions.md` as A11.

## D7. Replicas are required for a cascade to exist at all
The step-1 model was a single-level DAG with load flowing downstream. Testing it
showed **zero** propagation at every spare-capacity level: removing a node
changed nobody else's load (0 rose, 0 fell). In a pure downstream DAG a removed
node's traffic simply stops; there is nowhere for it to go.

The model was therefore restructured into two levels. A **role** is a logical
service that callers address; a **replica** is one instance of it, and what
actually fails. Load addressed to a role is split across its live replicas, so
removing one raises the load on its peers.

Two redistribution mechanisms follow, and they are separable by parameter:
- LATERAL: a replica dies, peers in the same role absorb its share.
- UPSTREAM: a role loses every replica, so calls to it fail and callers pay a
  retry cost in held resources. Controlled by `retry_cost`; 0 disables it.

Measured effect: with lateral failover alone, peak damage is 1.4% -- cascades
stay inside the role where they started. With retries enabled, peak damage is
23.5%, a 17x increase, because the failure can now walk upstream through the
dependency graph.

This was found by testing rather than by reasoning, which is the argument for
keeping a validation gate on every build step.

## D8. Analytic threshold as the validation gate
alpha_c = 1/(k-1) is derived exactly for the lateral mechanism and matched by
simulation at k = 2..6. This replaces "we observe a sharp transition" with a
falsifiable numerical prediction, and it is a stronger gate.

Replica counts are drawn with jitter (2-4 per role), so roles have different
critical capacities and the platform-wide transition is smeared across a range
of alpha rather than being one clean step. This is both more realistic and more
interesting: a platform can be subcritical for most of its services and
supercritical for a few.

## D9. Explicit agent-based formulation
The model was restated as an explicit agent-based model in `src/agents.py`:
a `ServiceAgent` class with `observe()` / `decide()` / `act()`, and a `World`
that runs a synchronous schedule over the population.

The physics is unchanged. `cascade.py` (the original procedural form) is kept in
the repository and the two are checked against each other: across three
topologies, four spare-capacity levels and both trigger types, the sets of
failed agents are **identical**. The refactor is a presentation change, and it is
verified to be one.

Why bother: the paradigm should be visible in the code rather than inferred from
it. `propagate_load()` looping to a fixed point is mathematically a local rule --
each agent sums from its in-neighbours -- but it reads as a system-level equation
solve. The agent loop makes the locality explicit.

Timescale separation (assumption A4) is what allows both: load is taken to
re-equilibrate faster than services fail, so demand propagates to a fixed point
between successive rounds of failure decisions. The propagation is itself local
message passing -- each agent forwards load only to its direct dependencies --
iterated until stable.

Performance note: the first agent implementation was 5.7x slower than the
procedural one because `World.down` rebuilt a set for every agent, making each
observe phase O(N^2). Caching the live-replica count per role during
equilibration, and reusing one population across trials instead of rebuilding
250 objects each time, brought it to 2.9 ms/trial -- faster than the original,
with identical results.

## D10. Graph rather than grid
The interaction topology is a dependency graph, not a lattice, which is the one
respect in which this is not a cellular automaton. This is deliberate: the
robust-yet-fragile result (targeted removal 5-11x worse than random) exists
because the graph has hubs, and it vanishes on a lattice with uniform
neighbourhoods.

A lattice variant is listed as an optional comparison arm rather than the main
model. It is cheap to add -- only the environment changes, the agent rules are
untouched -- and it would isolate how much of the result comes from the rules
versus the topology.

## D11. Cellular automaton as the primary formulation
The unit's modelling paradigms are cellular automata and agent-based models. The
project was restated with a lattice CA (`src/lattice.py`) as the primary model,
because a lattice CA is unambiguous: finite cells, a finite state set, a fixed
neighbourhood identical for every cell, one uniform transition rule, synchronous
update.

The graph formulation is retained as the extension. It keeps the same state set
and the same transition rule and changes only the neighbourhood, which is what
makes it a controlled comparison rather than a different model.

Design choices inside the CA:
- SHEDDING and QUARANTINING are one-step TRANSIENT states, as BURNING is in the
  forest-fire CA. They exist so a failed cell can hand its load to its
  neighbours on the following step using only local information. Without them
  the rule would need to read the neighbourhood-of-the-neighbourhood.
- DOWN and QUARANTINED are separate absorbing states, so damage can be
  attributed to overload versus to the detector. Merging them would make the
  U-curve visible but not explicable.
- Boundaries are fixed, not periodic. Edge cells genuinely have fewer
  neighbours, which is physically sensible for a rack layout and avoids the
  artificial wrap-around a torus would impose. `degree` is precomputed per cell
  because the rule divides by |N(j)|.

## D12. Two analytic gates rather than qualitative validation
alpha_c = 1/|N| and theta_c = (1 + 1/|N|)/(1 + alpha) are both derived by hand
and matched by simulation to within sweep resolution, across two neighbourhoods
and four spare-capacity levels. This replaces "a sharp transition is observed"
with falsifiable numerical predictions.

theta_c is the more valuable of the two: detector accuracy does not appear in
it. The safe operating point is set by spare capacity and by how load
redistributes, so improving the detector does not move the cliff.

## D13. Susceptibility is reported honestly, not uncritically
Over the full theta sweep, susceptibility peaks in the PERMISSIVE region, not at
the autoimmune collapse. The reason is that with the detector effectively off,
damage is driven by how many faults the random process happened to generate, so
replicate variance is large. Susceptibility cannot distinguish "unpredictable
because near a critical point" from "unpredictable because the input was
random".

Restricting the sweep to the aggressive arm, where the fault process contributes
almost nothing to the variance, puts the peak at theta = 0.95, which coincides
with the steepest change in damage. Both are reported, with the reason stated,
rather than showing only the flattering one.

## D14. Lattice outcomes are bimodal
300 trials near the transition: 47.7% negligible, 0.0% intermediate, 52.3%
near-total. A uniform lattice gives every cell the same degree and the same
share of load, so a cascade that is self-sustaining anywhere is self-sustaining
everywhere -- there is no structure for it to stop against.

No power law is fitted to this, because there is no scale-free range to fit.
`utils/metrics.py` returns NaN rather than a spurious exponent when a sample has
too few distinct values, and `bimodality()` reports the two-extremes structure
instead. This matters for the comparison in notebook 02: the graph formulation
produces avalanches of every size from the same rule.

## D15. Graph CA verified against the lattice CA rather than assumed equivalent
The controlled comparison in notebook 02 rests on the claim that only the
neighbourhood differs between the two arms. That claim is verified rather than
asserted: the lattice is expressed as a graph, the graph implementation is given
that neighbourhood, and the two produce IDENTICAL cell counts across two
neighbourhood types and five spare-capacity levels.

Without this check the topology comparison would be comparing two
implementations, not two topologies.

## D16. No power law is claimed for the avalanche distributions
MLE fitting (Clauset-Shalizi-Newman) on the scale-free arm selects a very high
xmin and the likelihood-ratio test against an exponential is inconclusive
(R = -0.2, p = 0.59). The honest description is a mixture -- many small events
plus a heavy shoulder -- not a clean scale-free range.

Reporting it this way is the reason for fitting properly instead of drawing a
line through a log-log histogram. `utils/metrics.py` returns NaN rather than a
spurious exponent when a sample has too few distinct values.

## D17. The separability condition was a finding, not a planned result
The robustness sweep was run to check whether the U-curve was an artefact of the
telemetry parameters. At delta = 0.20 the minimum damage over the entire sweep
was 1.000 -- not a worse optimum but NO optimum.

Working out why produced the third analytic result: the window between "healthy
cell that absorbed a dead neighbour" and "genuinely degraded cell" has width
delta - (1/|N|)/(1+alpha), and must also be wide relative to noise. Measured
onsets sit 4.0-5.4 sigma above that floor across four spare-capacity levels.

This is the most practically useful result in the project and it came out of a
robustness check, which is an argument for running them before concluding rather
than after.

## D18. theta* is a constant multiple of theta_c
Across alpha in [0.4, 1.0] the ratio theta*/theta_c is 1.23, 1.28, 1.27, 1.31.
The optimum is not merely correlated with the analytic cliff, it sits at
theta* ~ 1.27 theta_c. The constant absorbs the cost ratio between missing a
fault and causing one, so it would move if that trade-off changed -- but for a
fixed cost structure the safe setting is computable rather than something to be
found by tuning.


## D19. Notebook sequence restructured to the cellular automaton
Notebooks 01 and 02 documented the dependency-graph replica model, which is a
different model family from the cellular automaton introduced in what was
notebook 03. A reader opening the sequence in order met one model, then a
different one, with no connection between them -- the sequence did not read as a
single project.

The three cellular-automaton notebooks were therefore renumbered 01-03 and now
stand as the whole sequence:

    01  the cellular automaton, both analytic gates, the U-curve
    02  the controlled topology comparison
    03  robustness and the separability condition

The replica-model notebooks and their modules moved to `archive/`, with a README
explaining what they were and why they were replaced. Nothing was deleted: the
earlier formulation was validated work and the decisions log refers to it, but
it is not part of the submitted argument.

`src/graph_ca.py` does not depend on any archived module -- it imports only the
state constants from `src/lattice.py` and builds its own topologies -- so the
submitted sequence is self-contained.
