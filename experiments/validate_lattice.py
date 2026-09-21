

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np

from lattice import (LatticeCA, run_trial, run_episode,
                     HEALTHY, DOWN, QUARANTINED, REMOVED)

print("=" * 66)
print("VALIDATION: lattice cellular automaton")
print("=" * 66)

# ---- 1. neighbourhood ---------------------------------------------------
print("\n[1] neighbour counts at the boundary")
ca = LatticeCA(width=5, height=4, seed=0)
deg = ca.degree.astype(int)
assert deg[0, 0] == 2 and deg[0, 2] == 3 and deg[1, 2] == 4, deg
print(f"    von Neumann: corner={deg[0,0]} edge={deg[0,2]} interior={deg[1,2]}  ok")
cam = LatticeCA(width=5, height=4, neighbourhood="moore", seed=0)
dm = cam.degree.astype(int)
assert dm[0, 0] == 3 and dm[1, 2] == 8, dm
print(f"    Moore:       corner={dm[0,0]} edge={dm[0,2]} interior={dm[1,2]}  ok")

# ---- 2. conservation ----------------------------------------------------
print("\n[2] load is conserved by redistribution")
ca = LatticeCA(width=9, height=9, alpha=0.3, load_sigma=0.4, seed=1)
before = ca.load.sum()
ca.seed_failure()
for _ in range(5):
    ca.step()
after = ca.load.sum()
assert abs(before - after) < 1e-9, f"{before} -> {after}"
print(f"    total load {before:.6f} -> {after:.6f}  ok")

# ---- 3. no spontaneous failure -----------------------------------------
print("\n[3] an undisturbed lattice never changes state")
ca = LatticeCA(width=20, height=20, alpha=0.3, seed=2)
changed = sum(ca.step() for _ in range(10))
assert changed == 0 and ca.n_removed == 0
print("    10 steps, 0 state changes, 0 cells removed  ok")

# ---- 4. overload threshold ---------------------------------------------
print("\n[4] overload threshold vs analytic alpha_c = 1/|N|")
for nb, deg_n in (("von_neumann", 4), ("moore", 8)):
    predicted = 1.0 / deg_n
    measured = np.nan
    for a in np.linspace(0.01, 0.40, 391):
        if run_trial(a, 41, 41, neighbourhood=nb,
                     load_sigma=0.0, seed=1)["removed"] <= 1:
            measured = a
            break
    err = abs(measured - predicted)
    assert err < 0.005, f"{nb}: {predicted} vs {measured}"
    print(f"    {nb:12s} predicted {predicted:.4f}  measured {measured:.4f}  "
          f"err {err:.4f}  ok")

# ---- 5. detector threshold ---------------------------------------------
print("\n[5] detector threshold vs analytic theta_c = (1 + 1/|N|)/(1 + alpha)")
for nb, deg_n in (("von_neumann", 4), ("moore", 8)):
    for alpha in (0.4, 0.6, 0.8, 1.0):
        predicted = (1 + 1 / deg_n) / (1 + alpha)
        measured = np.nan
        for th in np.arange(predicted + 0.06, 0.0, -0.002):
            if run_trial(alpha, 50, 50, neighbourhood=nb, theta=th, noise=0.0,
                         load_sigma=0.0, seed=5)["removed_fraction"] > 0.5:
                measured = th
                break
        err = abs(measured - predicted)
        assert err < 0.01, f"{nb} a={alpha}: {predicted} vs {measured}"
        print(f"    {nb:12s} alpha={alpha:.1f}  predicted {predicted:.4f}  "
              f"measured {measured:.4f}  err {err:.4f}  ok")

# ---- 6. degenerate and boundary cases ----------------------------------
print("\n[6] degenerate and boundary cases")

ca = LatticeCA(width=1, height=1, alpha=0.3, seed=0)
ca.seed_failure()
ca.run()
assert ca.n_removed == 1
print("    1x1 lattice: the single cell is removed, no crash  ok")

ca = LatticeCA(width=1, height=12, alpha=0.3, seed=0)
assert ca.degree.max() == 2
ca.seed_failure()
ca.run()
print(f"    1x12 strip: max |N|=2, removed {ca.n_removed}/12  ok")

# theta below baseline utilisation: every cell is flagged at once
alpha = 0.5
ca = LatticeCA(width=15, height=15, alpha=alpha,
               theta=1 / (1 + alpha) - 0.05, noise=0.0, seed=0)
ca.run()
assert ca.n_quarantined == ca.n_cells, ca.summary()
print(f"    theta below baseline: all {ca.n_cells} cells quarantined  ok")

# detector off must be identical to theta = +inf
r_off = run_trial(0.2, 30, 30, theta=np.inf, load_sigma=0.0, seed=9)
r_high = run_trial(0.2, 30, 30, theta=1e9, load_sigma=0.0, seed=9)
assert r_off["removed"] == r_high["removed"]
print("    theta=inf and theta=1e9 agree  ok")

# an episode with no faults and no detector loses nothing
e = run_episode(0.6, np.inf, steps=50, width=30, height=30, fault_rate=0.0,
                noise=0.0, seed=0)
assert e["total_damage"] == 0.0, e
print("    no faults + no detector => zero damage  ok")

print("\n" + "=" * 66)
print("all checks passed")
print("=" * 66)
