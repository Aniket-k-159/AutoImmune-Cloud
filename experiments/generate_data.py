
import sys, os, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
from lattice import sweep_theta, run_trial

HERE = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(HERE, exist_ok=True)


def write(name, header, rows):
    path = os.path.join(HERE, name)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  wrote {name}  ({len(rows)} rows)")


print("generating data/ ...")

# 1. damage decomposition vs detector threshold
thetas = np.arange(0.70, 1.22, 0.02)
res = sweep_theta(thetas, alpha=0.6, replicates=8, steps=150,
                  width=50, height=50, noise=0.03, fault_rate=2e-4, seed=1)
write("theta_sweep_alpha0.6.csv",
      ["theta", "unremediated", "overload", "false_positive",
       "total_damage", "susceptibility"],
      [[f"{thetas[i]:.4f}", f"{res['unremediated'][i]:.6f}",
        f"{res['overload'][i]:.6f}", f"{res['false_positive'][i]:.6f}",
        f"{res['total_damage'][i]:.6f}", f"{res['susceptibility'][i]:.8f}"]
       for i in range(len(thetas))])

# 2. analytic vs measured thresholds
rows = []
for nb, deg in (("von_neumann", 4), ("moore", 8)):
    pred = 1.0 / deg
    meas = np.nan
    for a in np.linspace(0.01, 0.40, 391):
        if run_trial(a, 41, 41, neighbourhood=nb,
                     load_sigma=0.0, seed=1)["removed"] <= 1:
            meas = a
            break
    rows.append(["alpha_c", nb, deg, "", f"{pred:.6f}", f"{meas:.6f}"])
    for alpha in (0.4, 0.6, 0.8, 1.0):
        p = (1 + 1 / deg) / (1 + alpha)
        m = np.nan
        for th in np.arange(p + 0.06, 0.0, -0.002):
            if run_trial(alpha, 50, 50, neighbourhood=nb, theta=th, noise=0.0,
                         load_sigma=0.0, seed=5)["removed_fraction"] > 0.5:
                m = th
                break
        rows.append(["theta_c", nb, deg, f"{alpha:.2f}", f"{p:.6f}", f"{m:.6f}"])
write("analytic_gates.csv",
      ["quantity", "neighbourhood", "degree", "alpha", "predicted", "measured"],
      rows)

# 3. avalanche sizes near the lattice transition
sizes = [run_trial(0.30, 50, 50, load_sigma=0.5, seed=s)["removed"]
         for s in range(300)]
write("lattice_avalanches_alpha0.30.csv", ["trial", "cells_removed"],
      [[i, s] for i, s in enumerate(sizes)])

print("done.")
