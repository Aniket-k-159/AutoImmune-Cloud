# Correction Report

Branch: `mengbi/model-refinement`. Each issue records the problem, planned change and validation outcome.

## Issue #1 — Stochastic trials stopping too early

[Issue #1](https://github.com/Aniket-k-159/AutoImmune-Cloud/issues/1) · [Fix: 0231a25](https://github.com/Aniket-k-159/AutoImmune-Cloud/commit/0231a25d163735946865910737e2d47b04683172)

**Problem:** One unchanged timestep could stop a trial even though later noise or faults could cause further failures.

**Plan:** Separate deterministic convergence from fixed-horizon runs in both models. Require an explicit duration for stochastic trials and record the stopping reason.

**Validation (23 September 2026):** All three notebooks were run from top to bottom in fresh Jupyter/IPython kernels (`ipykernel 7.3.0`), using the published model code. Their saved outputs include the results, figures and cell execution times.

| Notebook | Code cells completed | Figures saved |
|---|---:|---:|
| [01 — Cellular automaton](../notebooks/01_cellular_automaton.ipynb) | 10/10 | 4 |
| [02 — Topology comparison](../notebooks/02_topology_comparison.ipynb) | 12/12 | 3 |
| [03 — Robustness](../notebooks/03_robustness.ipynb) | 8/8 | 3 |

Environment: Python 3.12.14, NumPy 2.5.3, NetworkX 3.6.1 and Matplotlib 3.11.2.

**Result:** In Notebook 01, the 60×60 example with alpha=0.6, theta=0.80, noise=0.02 and seed=3 reaches 3,600 removals at step 150; the old rule stopped at step 2 with one removal. All three notebooks completed without execution errors, and their printed numerical results match the previous local validation.

**Outcome:** The stochastic trial now continues beyond an unchanged timestep to its specified horizon. These are finite-window results, not guarantees of permanent safety. Notebook 02 retains the previously observed degree-tie demonstration difference from the original saved output; that separate issue is not part of this fix.
