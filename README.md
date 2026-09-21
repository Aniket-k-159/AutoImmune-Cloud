# Autoimmune cloud

**CITS4403 Computational Modelling research project**

> Does an automated remediation system have a sensitivity threshold past which
> it destroys more of the platform than the faults it is defending against?

**Claim under test:** automated remediation is itself a cascade process on the
infrastructure it protects. Past a critical detector sensitivity it causes more
outage than it prevents.

---

## The mechanism

A platform runs many service instances. Each carries a share of the traffic and
has finite capacity. When an instance is removed, **its traffic does not
vanish** it lands on its neighbours, which may push them past their own
limits. That is a load-redistribution cascade.

Nobody watches hundreds of instances by hand, so platforms deploy anomaly
detection with **automated** response: anything whose telemetry looks wrong is
quarantined and killed, with no human in the loop. Every statistical detector
has an unavoidable error rate, because the telemetry of a genuinely faulty
instance and of a merely busy one overlap.

In a monitored system a false positive costs an engineer's attention. In an
automated system it **removes a healthy instance** and that sheds traffic onto
its neighbours, which makes them look busy, which trips the detector again:

```
false positive -> instance quarantined -> load spills onto neighbours
      ^                                               |
      |                                               v
   detector flags them  <-  their utilisation rises
```

Positive feedback on the substrate the system is supposed to protect. The
biological parallel is autoimmunity: a more aggressive immune response clears
pathogens faster, but past a point destroys healthy tissue.

## Modelling paradigm — cellular automaton

| CA component | In this model |
|---|---|
| **Cells** | a `W × H` lattice; each cell is one service instance |
| **States** | `HEALTHY`, `DEGRADED`, `SHEDDING`, `DOWN`, `QUARANTINING`, `QUARANTINED` |
| **Neighbourhood** | von Neumann (4) or Moore (8), identical for every cell |
| **Rule** | one transition function, applied uniformly |
| **Update** | synchronous the lattice advances from `t` to `t+1` using only the configuration at `t` |
| **Boundary** | fixed, non-periodic |

Each cell also carries a real-valued load, as the sandpile CA carries a grain
count. Load moves only between lattice neighbours, so the rule stays local.
`SHEDDING` and `QUARANTINING` are one-step transient states, exactly as
`BURNING` is in the forest-fire CA; they let a failed cell hand its load to its
neighbours using only local information.

`DOWN` and `QUARANTINED` are kept as separate absorbing states on purpose: one
means the cell genuinely ran out of capacity, the other means the detector
removed a cell that was still within capacity. That distinction is what lets
damage be attributed to overload versus to the remediation system itself.

## Three analytic results, all validated against simulation

**Overload threshold.** A failing cell spills `ℓ/|N|` to each neighbour, so a
neighbour rises to `ℓ(1 + 1/|N|)`. The cascade stops iff that fits:

```
alpha_c = 1 / |N|
```

**Detector threshold.** A cell that has absorbed one dead neighbour reads
`(1 + 1/|N|) / (1 + alpha)`. If the threshold sits below that, every such cell
is flagged, and quarantining it floods its own neighbours in turn:

```
theta_c = (1 + 1/|N|) / (1 + alpha)
```

Both match simulation to within sweep resolution — `alpha_c` for von Neumann
and Moore neighbourhoods, `theta_c` across two neighbourhoods × four
spare-capacity levels (`data/analytic_gates.csv`).

**The second result is the project's analytic core.** The safe operating point
for an automated remediation system is fixed by how much spare capacity the
platform has and how its load redistributes. **Detector accuracy does not appear
in the expression at all** — a platform can improve its detector and still be
destroyed by it.

**Separability condition.** A usable threshold must sit above the reading of a
healthy cell that absorbed a dead neighbour and below that of a genuinely faulty
one. That window exists only if the fault signal clears the load signal by a
margin several times the telemetry noise:

```
delta > (1/|N|)/(1 + alpha) + z*sigma,    z ~ 4-5
```

Below this, **no threshold is safe** every setting is either blind or
self-destructive, and tuning cannot help because the problem is the signal, not
the threshold. Measured onsets sit 4.0–5.4σ above the analytic floor across four
spare-capacity levels.

## Research question

How do detector sensitivity, response aggressiveness, and neighbourhood
structure determine total system damage in an automated remediation system?

## Hypotheses

- **H1.** Total damage as a function of detector sensitivity is **U-shaped**
  too permissive and faults go unremediated, too aggressive and false-positive
  quarantine cascades. The minimum is interior, and its location depends on
  spare capacity and neighbourhood structure rather than on detector accuracy.
  *Supported: minimum damage 0.162 at θ = 1.00, against 2.4 with the detector
  off and 1.0 (total loss) below θ ≈ 0.94.*
- **H2.** There is a **critical sensitivity** above which remediation alone is
  supercritical. *Supported: at α = 0.6, where the overload cascade is
  impossible (α_c = 0.25), switching the detector on below θ_c destroys 100% of
  the lattice. Damage holds low and then jumps a 50% change for a 0.01 change
  in threshold.*
- **H3.** Replacing the uniform lattice neighbourhood with a service
  **dependency graph**, leaving the state set and transition rule unchanged,
  changes the character of the transition. *Supported, with a qualification:
  lattice, small-world and random graphs all give 0% intermediate-sized
  failures, while scale-free gives 33% and never loses everything. The driver is
  degree spread, not path length. But the safe threshold itself barely moves
  topology governs how you fail, not where the cliff is.*

## Originality and contribution

This is not one of the excluded models it is not Game of Life, Schelling,
Sugarscape, traffic, flocking, evolution, or the Prisoner's Dilemma and it is
not a reimplementation of an existing published model.

**What it builds on.** The load-redistribution half is in the same family as the
Bak–Tang–Wiesenfeld sandpile and the Drossel–Schwabl forest-fire CA, both of
which spread a local excess to lattice neighbours, and as the Motter–Lai
cascading-failure model on networks.

**How it differs.**

1. *Removal is permanent within an episode.* Sandpile toppling conserves grains
   and the cell recovers, so load diffuses. Here a failed cell is removed, so
   load **concentrates** on a shrinking set of survivors.
2. *There is a second removal mechanism, and it is driven by the state the first
   one creates.* No existing cascade CA has a detector. The quarantine rule
   reads the utilisation that redistribution produces and removes cells because
   of it, which closes a positive feedback loop that load redistribution alone
   does not have. This is the contribution.
3. *Damage is decomposed by cause.* Separating unremediated faults, genuine
   overload, and false-positive quarantine is what makes the U-curve
   interpretable rather than merely visible.
4. *The critical detector threshold is derived analytically*, not only measured,
   and the derivation shows it is independent of detector accuracy.

## Relation to the unit textbook, and what is reused

Two ingredients of this project appear in the unit textbook (Downey, *Think
Complexity*): the **sandpile model** of self-organised criticality, and the
**random, small-world and scale-free graph** models. This project builds on
both, so the boundary between reused and original work is stated explicitly.

**Reused, not claimed as our contribution**

| Item | Source | How it is used |
|---|---|---|
| Idea of a CA in which a local excess spreads to lattice neighbours | Bak–Tang–Wiesenfeld sandpile (textbook); Drossel–Schwabl forest fire | the load-redistribution step follows the same pattern |
| Graph generators: Erdős–Rényi, Watts–Strogatz, Barabási–Albert, 2D grid | `networkx` library functions; models covered in the textbook | used unchanged as neighbourhoods in notebook 02 |
| Maximum-likelihood power-law fitting and likelihood-ratio test | method of Clauset, Shalizi & Newman (2009) | re-implemented from the paper in `utils/metrics.py`, not copied from their code |
| Cascading-failure framing | Motter & Lai (2002) | motivation only; no code or model reused |

No code was copied from open-source projects. Library use is limited to
`numpy`, `networkx`, `matplotlib`.

**Original to this project**

1. **The detector-coupled quarantine rule.** A second removal route that reads
   the utilisation the redistribution step creates. No sandpile, forest-fire or
   cascade model has this, and it is what produces the feedback loop studied.
2. **The two-route state design.** Separate `DOWN` and `QUARANTINED` absorbing
   states, so every loss can be attributed to overload or to remediation.
3. **Three analytic results**, derived by hand and confirmed by simulation:
   `alpha_c = 1/|N|`, `theta_c = (1 + 1/|N|)/(1 + alpha)`, and the
   separability condition `delta > (1/|N|)/(1 + alpha) + z*sigma`.
4. **The damage decomposition** into unremediated faults, overload and
   false-positive quarantine, which makes the U-curve interpretable.
5. **The controlled topology comparison**: the same rule on a lattice and on
   graphs, with a check that the graph implementation reproduces the lattice
   automaton exactly, isolating topology as the only difference.
6. **The finding that degree spread, not path length, sets the character of
   failure**, and that hubs act as firebreaks under uniform load but not under
   degree-proportional load.

## Repository layout

```
src/         lattice.py    the cellular automaton -- the model
             graph_ca.py   the same automaton on a graph neighbourhood
utils/       plotting.py   shared figure style and lattice rendering
             metrics.py    susceptibility, MLE power-law fitting, bimodality
data/        saved sweep results, so figures redraw without re-running
notebooks/   the analysis, in order
experiments/ headless validation, data generation, figure export
docs/        proposal, assumptions, decisions, backlog, timeline
archive/     an earlier dependency-graph formulation, superseded when the
             model was restated as a cellular automaton (see archive/README.md)
```

`src/graph_ca.py` imports only the state constants from `src/lattice.py`, so the
submitted sequence is self-contained and nothing in `archive/` is needed to run
it.

## Setup and usage

Requires Python 3.9 or later.

```bash
pip install -r requirements.txt

# validation -- fast, no notebook needed, asserts every analytic gate
python experiments/validate_lattice.py

# regenerate saved results
python experiments/generate_data.py

# the analysis
jupyter lab      # then run notebooks/ in order
```

Every notebook runs top to bottom with no manual steps. Approximate runtimes:
01 about 35 s, 02 about 50 s, 03 about 5 min (03 is the parameter-sensitivity
sweep and is the only slow one).

## Notebooks

| Notebook | What it establishes |
|---|---|
| `01_cellular_automaton.ipynb` | **the model** — the CA stated and shown running, both analytic gates validated, the headline result, and the damage U-curve |
| `02_topology_comparison.ipynb` | **the contribution** — same states, same rule, graph neighbourhood. Degree spread, not path length, decides the character of failure |
| `03_robustness.ipynb` | the U-curve is not an artefact of the telemetry parameters, and a separability condition below which no safe threshold exists |

Read in order; each opens by stating what the previous one established.

## Headline results

| | |
|---|---|
| At `alpha = 0.6` with the detector **off** | 1 cell lost, no cascade possible |
| Same platform, detector at `theta = 0.78` | **100% destroyed**, entirely self-inflicted |
| Best achievable damage | 0.162 at `theta = 1.00`, vs 2.41 with the detector off |
| Sharpness of the collapse | 50% change in damage for a 0.01 change in threshold |
| Optimum vs analytic cliff | `theta* ~ 1.27 theta_c`, constant across `alpha` |
| Lattice / small-world / random | 0% intermediate-sized failures — all-or-nothing |
| Scale-free | 33% intermediate, 0% total — hubs arrest the spread |
| When `delta < (1/\|N\|)/(1+alpha) + 4 sigma` | **no safe threshold exists at all** |

## Status — Checkpoint 2

- [x] Lattice cellular automaton, two analytic gates validated
- [x] Headline result: remediation alone destroys a subcritical platform
- [x] U-curve with damage decomposed by cause (H1)
- [x] Critical sensitivity is a sharp transition (H2)
- [x] Graph-neighbourhood controlled comparison (H3)
- [x] Robustness sweep over every telemetry parameter
- [x] Separability condition — a third analytic result
- [ ] Report — drafting; finalised after Checkpoint 2 feedback

## References

Bak, P., Tang, C., & Wiesenfeld, K. (1987). Self-organized criticality: an
explanation of 1/f noise. *Physical Review Letters*, 59(4), 381–384.

Clauset, A., Shalizi, C. R., & Newman, M. E. J. (2009). Power-law distributions
in empirical data. *SIAM Review*, 51(4), 661–703.

Drossel, B., & Schwabl, F. (1992). Self-organized critical forest-fire model.
*Physical Review Letters*, 69(11), 1629–1632.

Motter, A. E., & Lai, Y.-C. (2002). Cascade-based attacks on complex networks.
*Physical Review E*, 66(6), 065102.
