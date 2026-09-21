# Build backlog

Each entry maps to a GitHub issue. Ordering is the build order; every step had a
gate that had to pass before the next began.

Steps marked `superseded` were completed and validated, then replaced when the
model was restated as a cellular automaton (decision D11). They are retained in
`archive/` and are not part of the submitted notebook sequence.

---

**#1  Dependency graph and load propagation**  `done` `superseded`
Three topology generators producing DAGs; steady-state load solver.
Gate: iterative solver matches the exact topological solution (max rel. err
4e-16); all graphs acyclic. PASSED.
-> `archive/notebooks/01_graphs_and_load.ipynb`, `archive/src/network.py`

**#2  Cascade baseline on the graph arm**  `done` `superseded`
Replica model; load redistributes laterally to peers and upstream via retries.
Gate: critical capacity matches the analytic `alpha_c = 1/(k-1)` at k = 2..6;
targeted removal 5-11x worse than random. PASSED.
-> `archive/notebooks/02_cascade_baseline.ipynb`, `archive/src/agents.py`

**#3  Lattice cellular automaton**  `done`
2D lattice, six states, uniform local rule, synchronous update. Transient
SHEDDING/QUARANTINING states so load transfers using local information only.
Gates: load conserved; `alpha_c = 1/|N|`; `theta_c = (1 + 1/|N|)/(1 + alpha)`;
edge cases (1x1, 1xN, theta below baseline, detector-off equivalence). ALL
PASSED.
-> `notebooks/01_cellular_automaton.ipynb`, `src/lattice.py`,
   `experiments/validate_lattice.py`

**#4  U-curve and critical sensitivity**  `done`
Background fault process; damage decomposed into unremediated / overload /
false-positive. Tests H1 and H2.
Result: minimum damage 0.162 at theta = 1.00 against 2.41 with the detector off
and total loss below theta ~ 0.94. The collapse is a jump (50% damage change for
a 0.01 threshold change), not a slope.
-> sections 7-8 of notebook 01, `data/theta_sweep_alpha0.6.csv`

**#5  Graph-neighbourhood controlled comparison (H3)**  `done`
State set and transition rule held fixed; only the neighbourhood replaced.
Gate: the graph implementation reproduces the lattice automaton EXACTLY when
given the lattice's own neighbourhood. PASSED.
Results: lattice / small-world / random all give 0% intermediate outcomes;
scale-free gives 33% and never total loss. Driver is degree spread, not path
length (small-world is the control). Local threshold `alpha >= 1/k_j` holds
exactly: no cascade ever propagated from a cell with k >= 1/alpha.
-> `notebooks/02_topology_comparison.ipynb`, `src/graph_ca.py`

**#6  Robustness and sensitivity analysis**  `done`
Swept fault signal, noise, fault rate, spare capacity and lattice size.
The U-curve survives in 8 of 9 conditions; the exception is explained
analytically and became result #7.
-> `notebooks/03_robustness.ipynb`

**#7  Separability condition**  `done`
A third analytic result, found by the robustness sweep rather than anticipated:
a safe threshold exists only if `delta > (1/|N|)/(1+alpha) + z*sigma`, z ~ 4-5.
Below it every setting is either blind or self-destructive.
-> section 2 of notebook 03

**#8  Report**  `done`
Five pages of body text, 11pt, 1in margins, four figures, five references.
-> `report/report.pdf`, `report/report.tex`, `experiments/make_figures.py`

---

## Open / future work

**#9  Autoscaling**
Delayed negative feedback opposing the positive feedback studied here. Likely to
convert collapse into oscillation, which would be a qualitatively different
regime. The single most valuable extension.

**#10  Correlated detector errors**
Services running the same image under the same load produce similar telemetry,
so false positives should cluster. Current independence assumption is
conservative; correlated errors should make the cascade worse.

**#11  Event-driven reimplementation**
The synchronous schedule may sharpen the transition relative to a queueing
system. A SimPy version would test whether any conclusion depends on it.

**#12  Calibration against production telemetry**
Measuring real `delta` and `sigma` would turn the separability condition from a
modelling result into an operational test a platform team could actually run.
