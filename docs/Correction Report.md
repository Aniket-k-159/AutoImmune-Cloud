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

## Issue #2 — Untracked load loss

[Issue #2](https://github.com/Aniket-k-159/AutoImmune-Cloud/issues/2) · [Fix: 8026976](https://github.com/Aniket-k-159/AutoImmune-Cloud/commit/80269764b7b5af8d7957b6ad6a1630eb661fb428)

**Problem:** Load sent to exited neighbours disappeared without being recorded.

**Plan:** Track dropped load in both models, retain the default `legacy` rule, and add optional `serving_neighbours` redistribution. With no eligible neighbour, record the load as dropped.

**Validation (25 September 2026):** All three notebooks were rerun in fresh Jupyter/IPython kernels using commit `8026976` and the environment recorded above. Each includes one additional Issue #2 validation cell; all original code and explanatory cells are preserved.

| Notebook | Code cells completed | Figures saved | Added evidence |
|---|---:|---:|---|
| 01 | 11/11 | 4 | Continuing cascade and isolated-cell load accounting |
| 02 | 13/13 | 3 | Graph/lattice agreement and redistribution comparison |
| 03 | 9/9 | 3 | Fixed-horizon damage and threshold comparison |

**Results:** The original cells reproduce the published legacy numerical output. In the 7×7 counterexample at step 2, legacy load is 47.75 with 1.25 recorded as dropped; the optional rule retains 49 with none dropped. Both account for the initial 49 units. In Notebook 02's 300-trial scale-free sample, near-total cascades rise from 0% to 48.7% under the optional rule. Notebook 03's baseline scan moves from theta=1.00, damage=0.145 to theta=1.02, damage=0.577.

**Outcome:** Load loss is now explicit. The optional rule can concentrate load and worsen cascades; it does not guarantee zero loss or improved safety. These comparisons retain the existing cost measure and finite observation horizon. Earlier conclusions remain conditional on the redistribution rule and sampled conditions.

## Issue #3 — Isolated nodes and zero-capacity telemetry

[Issue #3](https://github.com/Aniket-k-159/AutoImmune-Cloud/issues/3) · [Fix: 9079fe7](https://github.com/Aniket-k-159/AutoImmune-Cloud/commit/9079fe7187e2d07b932233c4bb41c24d05ca8559)

**Problem:** Degree-based load gave isolated nodes zero load and capacity, producing NaN telemetry that prevented fault detection. Their reported degree was also changed from 0 to 1.

**Plan:** Separate actual degrees from division safeguards, define zero-load/zero-capacity utilisation as zero while retaining fault signals, and reject degree-based load on edgeless graphs. Both models use the same zero-capacity telemetry rule.

**Validation (26 September 2026):** All three notebooks were run in fresh Jupyter/IPython kernels using commit `9079fe7`, completing 11, 14 and 9 code cells and saving 10 figures. Notebook 02 adds the direct boundary checks; every earlier code and explanatory cell is preserved, and its numerical output is unchanged.

**Results:** The three-node example now reports `[1, 1, 0]`. Under both redistribution rules, the isolated node's healthy signal is 0; a fault signal of 1 exceeds threshold 0.9 and produces one correct isolation. Load accounting remains balanced. Uniform load on an isolated node reports `seed_degree=0` and records its dropped load. Edgeless degree-based load raises a clear error instead of creating NaN values.

**Outcome:** Isolated-node measurement and detection are corrected without changing the existing experiment results. Positive load with zero capacity is still treated as overload; the fix does not silently make such a node healthy.

## Issue #4 — Random inputs for paired comparisons

[Issue #4](https://github.com/Aniket-k-159/AutoImmune-Cloud/issues/4) · [Fix: a763271](https://github.com/Aniket-k-159/AutoImmune-Cloud/commit/a7632710e4fa3c48ed6ac842df93c45099c082bd)

**Problem:** Skipping telemetry draws changed later fault draws, so the same seed did not give different detector settings the same fault inputs.

**Plan:** Add an optional `split` random protocol with separate sources for initialization, initial failures, faults and telemetry. Index fault and noise inputs by node and timestep, record the effective seeds and protocol version, and retain `legacy` as the default for historical comparisons.

**Validation (28 September 2026):** All three notebooks were fully executed in fresh Jupyter/IPython kernels using commit `a763271`, completing 12, 15 and 10 code cells and saving 10 figures. Each adds one Issue #4 check; all earlier cell sources and printed numerical results are preserved. The recorded environment remains unchanged.

**Results:** In the 6×6, seed-7 example, legacy fault states differ from timestep 2 when comparing a disabled detector with a very high threshold. Split inputs and states agree through all three steps, including after extra telemetry calls. Graph and lattice checks agree under both redistribution rules. Notebook 03 completes 152 trials with 24 training seeds and 40 separate evaluation seeds; its paired damage difference is -2.8125, with a 95% bootstrap interval of [-3.164844, -2.462881] for the stated fixed-grid experiment.

**Outcome:** Split mode supports controlled, repeatable comparisons. Shared potential inputs do not require identical actual faults once strategies remove different nodes. The damage comparison uses the existing cost measure and finite horizon; it does not establish improved availability or a universally optimal threshold.
