# Archive — the earlier formulation

**Nothing here is part of the submitted project.** It is kept because the
decisions log refers to it and because it records how the model reached its
final form.

## What this is

The project began as a **service dependency graph** model rather than a
cellular automaton. Services were nodes, calls were directed edges, and each
logical service ran several interchangeable replicas behind a load balancer.
Failure spread two ways: laterally, when a replica died and its peers absorbed
its share, and upstream, when a service lost every replica and its callers paid
a retry cost in held connections.

That formulation worked and was validated — the measured critical spare capacity
matched an analytic prediction `alpha_c = 1/(k-1)` at every replica count
`k = 2..6`, and it reproduced the standard robust-yet-fragile result, with
targeted removal 5–11× more damaging than random removal.

## Why it was replaced

The unit's modelling paradigms are cellular automata and agent-based models. A
dependency-graph model with role-level load balancing is neither cleanly — it
has no fixed neighbourhood and no uniform local rule over identical cells. The
model was therefore restated as a lattice cellular automaton, which is
unambiguous: finite cells, a finite state set, a fixed neighbourhood identical
for every cell, one uniform transition rule, synchronous update.

The restatement was not a retreat. It produced two exact analytic thresholds
that the graph formulation had not yielded, and it made the topology question
answerable as a *controlled* comparison: the submitted notebook 02 holds the
state set and transition rule fixed and changes only the neighbourhood, which
the replica model could not have done.

## Contents

```
notebooks/01_graphs_and_load.ipynb    graph topologies and load propagation;
                                      solver validated against an exact
                                      topological-order solution (4e-16)
notebooks/02_cascade_baseline.ipynb   replica cascade, agent-based formulation,
                                      alpha_c = 1/(k-1) validated at k = 2..6
src/network.py                        role graph and replica topology generators
src/agents.py                         agent-based form: observe / decide / act
src/cascade.py                        procedural form, kept as a cross-check
                                      (verified to produce identical results)
experiments/validate_network.py       headless gates for the above
```

To run anything here, add `archive/src` to the path rather than `src`.

## Where the history is recorded

`docs/decisions.md` carries the reasoning, in particular:

- **D5** — the attack layer removed after Checkpoint 1
- **D7** — replicas were required for a cascade to exist at all; the first
  single-level graph model had *zero* propagation at every capacity level, which
  testing revealed and reasoning had not
- **D9** — the explicit agent-based formulation, verified against the
  procedural one
- **D11** — the move to a cellular automaton as the primary formulation
