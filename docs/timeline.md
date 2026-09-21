# Timeline

Revised after Checkpoint 1. The attack layer has been dropped, which frees
roughly a week — spent on sensitivity analysis, which is what protects the
headline result.

| Week | Work | Gate |
|---|---|---|
| 6  | Repo, graph topologies and load propagation | solver validated |
| 7-8 | **CHECKPOINT 1** — proposal discussed | scope simplified; paradigm set to CA |
| 8  | Cascade baseline on the graph arm | critical capacity matches 1/(k-1) |
| 8  | **Lattice CA built** | load conserved; alpha_c = 1/\|N\| |
| 8  | Detector rule added to the CA | theta_c = (1 + 1/\|N\|)/(1 + alpha) |
| 9  | U-curve, damage decomposition | H1 and H2 supported |
| 9-10 | **CHECKPOINT 2** — model demo, sweep plan | |
| 10 | Graph-neighbourhood comparison (H3) | |
| 11 | Sensitivity analysis on telemetry coupling; avalanche fitting | |
| 11 | Report drafting | **STOP RULE** applies here |
| 12 | **CHECKPOINT 3** — demo and report | |

## Ahead of schedule

The riskiest step — verifying that load-induced telemetry elevation actually
crosses the detection threshold — is **done and passed**. It was the thing most
likely to sink the project, and it is settled: at alpha = 0.6 the detector alone
destroys 100% of a lattice on which the physical cascade cannot propagate.

## Stop rule

If the U-curve is not clean by the start of week 11, drop H3 entirely. Spend the
time on sensitivity analysis and avalanche-distribution fitting instead. Depth
on two hypotheses beats thin coverage of three.

## Runtime budget

Estimate before launching the full sweep. Example: 20 thresholds x 3 detector
qualities x 5 alphas x 30 replicates = 9,000 runs. At 2s per run that is 5
hours. Work this out at Checkpoint 2 and have a parallelisation plan ready.
Long sweeps run as scripts in `experiments/`, never inside a notebook cell.
