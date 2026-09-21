"""
Headless validation for steps 1 and 2.

Run from the project root:   python experiments/validate_network.py

Checks:
  1. role graphs are acyclic
  2. removing a replica raises the load on its surviving peers
     (the redistribution a single-level DAG does not provide)
  3. the measured critical spare capacity matches the analytic
     prediction alpha_c = 1/(k-1) for uniform replica counts
  4. targeted removal is far more damaging than random removal
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))  # archive/src

import numpy as np
import networkx as nx

from network import (Platform, build_layered_roles, build_platform,
                     propagate_load)
from agents import World, run_trial
import cascade as procedural

SEED, RETRY = 42, 1.0

print("=" * 66)
print("VALIDATION: agent model and cascade baseline")
print("=" * 66)

# ---- 1. structure -------------------------------------------------------
print("\n[1] role graph structure")
platforms = {k: build_platform(k, replicas=3, seed=SEED)
             for k in ("layered", "ba", "er")}
for kind, P in platforms.items():
    assert nx.is_directed_acyclic_graph(P.roles), f"{kind} role graph has a cycle"
    print(f"    {kind:9s} roles={P.n_roles:3d} replicas={P.n_nodes:4d} "
          f"edges={P.roles.number_of_edges():4d}  acyclic ok")

# ---- 2. redistribution exists ------------------------------------------
print("\n[2] removing a replica must raise its peers' load")
P = platforms["layered"]
L0, _ = propagate_load(P)
busiest = max(P.nodes, key=lambda n: L0[n])
L1, _ = propagate_load(P, down={busiest})
rose = [n for n in P.nodes if n != busiest and L1[n] > L0[n] + 1e-9]
assert rose, "no redistribution: removal changed nobody's load"
n = rose[0]
print(f"    removed replica {busiest}; {len(rose)} peer(s) rose")
print(f"    e.g. replica {n}: {L0[n]:,.0f} -> {L1[n]:,.0f} "
      f"({L1[n]/L0[n]:.3f}x)")

# ---- 3. analytic critical threshold ------------------------------------
print("\n[3] critical spare capacity vs analytic alpha_c = 1/(k-1)")
grid = np.linspace(0.02, 1.40, 139)
for k in (2, 3, 4, 5, 6):
    Pk = Platform(build_layered_roles(seed=7), replicas=k, jitter=0, seed=7)
    predicted = 1.0 / (k - 1)
    measured = np.nan
    for a in grid:
        dmg = np.mean([
            run_trial(Pk, a, "random", rng=np.random.default_rng(s),
                      retry_cost=RETRY)["failed_fraction"]
            for s in range(12)])
        if dmg <= 1.5 / Pk.n_nodes:
            measured = a
            break
    err = abs(measured - predicted)
    assert err < 0.03, f"k={k}: predicted {predicted:.4f}, measured {measured:.4f}"
    print(f"    k={k}  predicted {predicted:.4f}  measured {measured:.4f}  "
          f"err {err:.4f}  ok")

# ---- 4. robust yet fragile ---------------------------------------------
print("\n[4] random vs targeted removal (alpha = 0.18)")
for kind, P in platforms.items():
    rng = np.random.default_rng(1)
    rnd = np.mean([run_trial(P, 0.18, "random", rng=rng,
                             retry_cost=RETRY)["failed_fraction"]
                   for _ in range(60)])
    hub = run_trial(P, 0.18, "hub", rng=np.random.default_rng(1),
                    retry_cost=RETRY)["failed_fraction"]
    assert hub > rnd, f"{kind}: targeted removal not worse than random"
    print(f"    {kind:9s} random {rnd:.3f}   targeted {hub:.3f}   "
          f"{hub/max(rnd,1e-9):.1f}x")

# ---- 5. agent model == procedural model --------------------------------
print("\n[5] agent formulation reproduces the procedural one exactly")
same = True
for kind, P in platforms.items():
    for alpha in (0.05, 0.18, 0.40, 0.90):
        for trig in ("random", "hub"):
            a = run_trial(P, alpha, trig, rng=np.random.default_rng(7),
                          retry_cost=RETRY)
            c = procedural.run_trial(P, alpha, trig,
                                     rng=np.random.default_rng(7),
                                     retry_cost=RETRY)
            same &= (a["failed"] == c["failed"])
assert same, "agent and procedural formulations disagree"
print("    identical failed sets across 3 topologies x 4 alphas x 2 triggers")

print("\n" + "=" * 66)
print("all checks passed")
print("=" * 66)
