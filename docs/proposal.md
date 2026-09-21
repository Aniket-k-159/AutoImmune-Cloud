# Project proposal

CITS4403 Computational Modelling. Solo project.

*Revised after Checkpoint 1: the attack layer has been removed on the
facilitator's advice. A background fault process replaces it. Section 9 records
what changed and why.*

---

## 1. System and motivation

A microservice platform is a directed graph. Nodes are services, an edge
`i -> j` means "service `i` calls service `j`". Requests enter at gateway
services and propagate downstream.

Two properties matter:

- **Services have finite capacity.** When one is removed, its traffic
  redistributes to the survivors, which can push them past their own limits.
  This is the load-redistribution cascade mechanism, the same family as
  power-grid blackouts.
- **Load is unevenly distributed.** In graphs with hubs, a small number of
  shared services carry most of the traffic, so where a failure happens matters
  more than how large it was.

Nobody manually monitors hundreds of services, so platforms deploy machine
learning anomaly detection with **automated** response: a flagged workload is
quarantined, its container killed, its traffic drained. No human in the loop.

Every statistical detector faces an unavoidable trade-off. The telemetry score
distributions for "genuinely degraded" and "merely busy" overlap, so any
threshold trades false positives against false negatives. This is not a defect
of a particular model; it is geometry.

The motivating observation is what a false positive *costs* once response is
automated. In a monitored system it costs an engineer's attention, and ten false
positives cost ten times one. In an automated system it **deletes a healthy
service** — and deleting a loaded node in a dependency graph redistributes its
traffic onto its neighbours, which makes those neighbours look anomalous, which
triggers further quarantines.

**The remediation system is itself a cascade process on the same graph.** It
spreads, it removes services, and it feeds itself. That is positive feedback,
and positive feedback is what turns a local incident into a system-wide outage.

The biological parallel is autoimmunity: a more aggressive immune response
clears pathogens faster, but past a point destroys healthy tissue, and a
cytokine storm can kill the patient faster than the infection would have. The
optimal response is not the most aggressive one.

## 2. Research question

> How do detector sensitivity, response aggressiveness, and infrastructure
> topology determine total system damage in an automated remediation system?

## 3. Hypotheses

**H1 (core).** Total damage as a function of detector sensitivity is U-shaped.
Too insensitive and faults go unremediated; too sensitive and false-positive
quarantine cascades. The minimum is interior, and its location depends on spare
capacity and topology, not on detector accuracy alone.

**H2 (core).** There exists a critical sensitivity above which the remediation
system alone is supercritical: a background fault rate that would otherwise be
harmless produces a system-wide outage. Tested by sweeping sensitivity while
holding the fault rate at a level that causes negligible damage when
unremediated.

**H3 (stretch).** The detector-driven cascade is a mechanism distinct from the
capacity cascade: it persists even when spare capacity is set high enough that
overload failure is impossible. If so, over-provisioning — the standard defence
against cascading failure — does not protect against this one.

### Falsification conditions

- H1 fails if damage is monotone in sensitivity with no interior minimum.
- H2 fails if damage rises smoothly with no sharp transition and no
  susceptibility peak.
- H3 fails if the cascade disappears once capacity failure is made impossible,
  which would mean the two mechanisms are the same thing.

## 4. Modelling approach

**Paradigm: cellular automaton.** Cells are service instances on a 2D lattice,
each following one local transition rule, updated synchronously.

| CA component | In this model |
|---|---|
| Cells | a W x H lattice; each cell is one service instance |
| States | HEALTHY, DEGRADED, SHEDDING, DOWN, QUARANTINING, QUARANTINED |
| Neighbourhood | von Neumann (4) or Moore (8), identical for every cell |
| Rule | one transition function, applied uniformly to every cell |
| Update | synchronous: the lattice advances from t to t+1 using only the configuration at t |
| Boundary | fixed, non-periodic -- edge cells have fewer neighbours |

Each cell carries a real-valued load, as the sandpile CA carries a grain count.
Load moves only between lattice neighbours, so the rule is strictly local.
SHEDDING and QUARANTINING are one-step transient states, exactly as BURNING is
in the forest-fire CA; they let a failed cell hand its load to its neighbours
using only local information.

DOWN and QUARANTINED are separate absorbing states on purpose: one means the
cell genuinely exceeded capacity, the other means the detector removed a cell
that was still within capacity. That distinction is what lets damage be
attributed to overload versus to the remediation system itself.

**Transition rule.** For cell i with neighbourhood N(i):

1. Gather: incoming_i = sum over j in N(i) with s_j transient of  l_j / |N(j)|
   and  l_i(t+1) = l_i(t) + incoming_i
2. Transition:
   - SHEDDING -> DOWN, QUARANTINING -> QUARANTINED (load set to 0)
   - DOWN, QUARANTINED: absorbing
   - HEALTHY -> DEGRADED with probability p (a fault appears)
   - HEALTHY/DEGRADED -> SHEDDING if l_i(t+1) > c_i
   - HEALTHY/DEGRADED -> QUARANTINING else if telemetry_i > theta

**Telemetry.** telemetry_i = l_i/c_i + delta*[s_i = DEGRADED] + noise.
Utilisation, plus an offset if genuinely faulty, plus noise. The noise makes the
faulty and busy populations overlap, so no threshold separates them cleanly.
That overlap is the reason the problem exists, not a modelling convenience.

**Capacity.** c_i = (1 + alpha) l_i(0), so alpha is spare capacity.

**Fault process.** Each healthy cell degrades with probability p per step -- a
bad deploy, a memory leak, a noisy neighbour. A degraded cell keeps serving but
is faulty and costs something every step it goes unremediated, so catching
faults has real value and the trade-off is genuine.

### Two analytic results

Both are derived before simulation and then validated against it.

Overload threshold. A failing cell spills l/|N| to each neighbour, so a
neighbour rises to l(1 + 1/|N|). The cascade stops iff that fits inside
capacity:

    alpha_c = 1/|N|

Detector threshold. A cell that has absorbed one dead neighbour reads
(1 + 1/|N|)/(1 + alpha). If theta is below that, every such cell is flagged, and
quarantining it floods its own neighbours in turn:

    theta_c = (1 + 1/|N|)/(1 + alpha)

The second is the analytic core of the project. The safe operating point is
fixed by spare capacity and by how load redistributes. Detector accuracy does
not appear in the expression -- a platform can improve its detector and still be
destroyed by it.

### Extension: changing only the neighbourhood

The state set and transition rule are held fixed and the neighbourhood is
replaced: from a uniform lattice to a service dependency graph, where a few
shared services are called by very many others. This isolates the contribution
of topology, since nothing else changes.

Preliminary result: the lattice gives an all-or-nothing transition (measured
47.7% negligible, 0.0% intermediate, 52.3% near-total), while the graph gives
avalanches of every size. The rule is the same; the topology decides the
character of the transition.

### Three damage sources, tracked separately

1. **Unremediated degradation** — the detector missed a genuine fault.
2. **Overload** — the service genuinely exceeded capacity after a neighbour was
   removed.
3. **False-positive quarantine** — the service was healthy and had headroom, and
   was removed because its telemetry looked anomalous.

Collapsed into one number, the U-shape is visible but not explicable. Split
three ways, the story tells itself.

## 5. Experimental design

| Variable | Range | Purpose |
|---|---|---|
| Detector threshold `theta` | full ROC sweep | H1, H2 — the control parameter |
| Detector quality `d'` | 1, 2, 3 | separates "better detector" from "more aggressive detector" |
| Spare capacity `alpha` | 0.1 – 1.0 | locates the cascade transition; H3 |
| Blast radius | node / node + neighbours | response aggressiveness |
| Topology | layered / BA / ER | structural factor |
| Fault rate `p` | 1e-4, 1e-3 | drives the trade-off |
| Telemetry coupling strength | sensitivity analysis | robustness of the whole result |

**Controls.** Matched node count and mean degree across topologies. Fixed and
logged seeds. The key control is running at a fault rate low enough that damage
is negligible *without* remediation — so any large damage at high sensitivity is
unambiguously self-inflicted.

**Replicates.** 30 per cell for means and confidence intervals; 1000+ episodes
per cell for avalanche-size distributions, which are tail-hungry.

## 6. Validation before extension

The model must reproduce the standard load-redistribution cascade before the
detector is added:

| Baseline | Gate |
|---|---|
| Load-redistribution cascade | sharp transition in failed fraction as `alpha` falls; scale-free graph robust to random removal, fragile to targeted removal |

If this does not reproduce, the extension means nothing.

## 7. Analysis

**Quantitative.** Damage-decomposition U-curve, stacked by the three sources.
Phase diagram over (`theta`, `alpha`). Susceptibility — variance across
replicates — to locate transitions numerically rather than by eye.
Avalanche-size distributions fitted by maximum-likelihood with likelihood-ratio
tests against lognormal and exponential alternatives, not straight-line fits on
log-log axes.

**Qualitative.** Cascade timelines showing bounded spread versus runaway
collapse. Network snapshots at successive timesteps for one representative
cascade of each kind.

## 8. Scope

Solo project, roughly five weeks of build time.

- **Core:** H1 and H2.
- **Stretch:** H3.
- **Optional comparison arm:** run the same agent rules on a 2D lattice, where
  every agent has four neighbours and no hubs exist. Isolates how much of the
  result comes from the rules and how much from the topology. Cheap to add,
  because only the environment changes and the agent rules are untouched.
- **Mandatory regardless:** sensitivity analysis on the telemetry coupling
  constant. The U-curve could otherwise be an artefact of one parameter, and
  this is the check that protects the headline result.

**Stop rule.** If the U-curve is not clean by the start of week 11, drop H3 and
spend the time on sensitivity analysis and distribution fitting instead. Depth
on two hypotheses beats thin coverage of three.

## 9. What changed after Checkpoint 1

The original design had two contagion processes on one graph: a worm spreading
along trust edges, and the remediation cascade. The facilitator judged this too
complex for a solo project. Agreed, and the attack layer has been removed
entirely — lateral movement, trust edges, stealth levels, image diversity, and
the adaptive attacker are all gone.

A background fault process replaces it. This keeps the detection trade-off real
(the detector still has a genuine job) without simulating any spreading
mechanics.

**What was lost:** one contagion process, roughly 40% of the code and 60% of the
parameter space. Epidemic spreading on a network is thoroughly published, so
this was the part contributing least novelty.

**What was kept:** the entire autoimmune mechanism, which is the contribution.
The project now has one control parameter, one order parameter, and a cleaner
phase diagram — a tighter piece of work, not merely a smaller one.

## 10. Progress

Earlier graph formulation, complete and validated, now in `archive/`
(`archive/notebooks/01_graphs_and_load.ipynb`):

- three graph generators, all producing DAGs
- steady-state load propagation, validated against an exact topological-order
  solution to machine precision (max relative error 4e-16)
- topology comparison showing the robust-yet-fragile property

Matched on node count and mean degree, removing a single service costs **47%**
of served work on the scale-free graph versus **5%** on the random graph. No
detector is in the model yet — this is structure alone.
