"""
Regenerate the report figures into report/figures/.

Run from the project root:  python -I experiments/make_figures.py

Figures 3 and 4 are drawn from data/report_numbers.json, so the plots and the
numbers quoted in the report come from the same measurement pass and cannot
drift apart. Figures 1 and 2 re-run their own short simulations.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils"))

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from lattice import LatticeCA, run_trial
from plotting import use_house_style, show_lattice, COLOURS

use_house_style()
ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "report", "figures")
os.makedirs(OUT, exist_ok=True)
NUM = json.load(open(os.path.join(ROOT, "data", "report_numbers.json")))

TCOL = {"lattice": "#1baf7a", "small-world": "#eda100",
        "random": "#898781", "scale-free": "#2a78d6"}


def save(fig, name):
    fig.savefig(os.path.join(OUT, name), bbox_inches="tight", dpi=200)
    plt.close(fig)
    print("  " + name)


print("generating report figures...")

# --- Fig 1: the cascade, over a fixed horizon --------------------------
ALPHA, HORIZON = NUM["headline"]["alpha"], NUM["headline"]["steps"]
ca = LatticeCA(width=60, height=60, alpha=ALPHA, theta=0.80, noise=0.02,
               load_sigma=0.0, seed=3, randomness="split")
ca.seed_failure()
snaps, shots = [ca.state.copy()], [0]
for s in range(1, HORIZON + 1):
    ca.step()
    if s in (20, 60, 150):
        snaps.append(ca.state.copy())
        shots.append(s)
fig, axes = plt.subplots(1, 4, figsize=(11, 3.0))
for ax, snap, t in zip(axes, snaps, shots):
    show_lattice(snap, ax=ax, title=f"t = {t}")
save(fig, "fig1_cascade.png")

# --- Fig 2: the two analytic gates -------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(11, 3.4))
ax = axes[0]
for nb, deg, col in (("von_neumann", 4, "#2a78d6"), ("moore", 8, "#eb6834")):
    alphas = np.linspace(0.05, 0.40, 36)
    frac = [run_trial(a, 41, 41, neighbourhood=nb, load_sigma=0.0,
                      seed=1)["removed_fraction"] for a in alphas]
    ax.plot(alphas, frac, color=col, lw=1.8, label=f"{nb} (|N|={deg})")
    ax.axvline(1 / deg, color=col, ls=":", lw=1)
ax.set_xlabel(r"spare capacity $\alpha$"); ax.set_ylabel("fraction lost")
ax.set_title(r"(a) overload threshold $\alpha_c=1/|N|$")
ax.legend(fontsize=8)

ax = axes[1]
for nb, col in (("von_neumann", "#2a78d6"), ("moore", "#eb6834")):
    rows = [r for r in NUM["gate_theta_c"] if r["neighbourhood"] == nb]
    ax.scatter([r["predicted"] for r in rows], [r["measured"] for r in rows],
               s=50, color=col, zorder=3,
               label=f"{nb} (|N|={rows[0]['degree']})")
lims = [0.5, 0.95]
ax.plot(lims, lims, ls="--", color="#898781", lw=1)
ax.set_xlabel(r"predicted $\theta_c$"); ax.set_ylabel(r"measured $\theta_c$")
ax.set_title("(b) detector threshold"); ax.legend(fontsize=8)
save(fig, "fig2_gates.png")

# --- Fig 3: the U-curve, both redistribution rules ---------------------
fig, axes = plt.subplots(1, 2, figsize=(12.0, 3.9), sharey=True)
for ax, rule, title in zip(
        axes, ("legacy", "serving_neighbours"),
        ("(a) shared across all neighbours", "(b) shared across live neighbours only")):
    u = NUM["ucurve"][rule]
    th = np.array(u["thetas"])
    ax.stackplot(th, u["unremediated"], u["overload"], u["false_positive"],
                 labels=["unremediated fault-time", "overload",
                         "false-positive quarantine"],
                 colors=[COLOURS["unremediated"], COLOURS["overload"],
                         COLOURS["false_positive"]], alpha=0.85)
    ax.plot(th, u["total_damage"], color="#0b0b0b", lw=1.8, label="total")
    ax.axvline(u["theta_star"], color="#0b0b0b", ls=":", lw=1)
    ax.axvline(NUM["headline"]["theta_c"], color="#5f5e5a", ls="--", lw=1)
    ax.set_xlabel(r"detector threshold $\theta$")
    ax.set_title(title)
axes[0].set_ylabel("damage (cell-equivalents per cell)")
axes[0].legend(fontsize=8, loc="upper center")
save(fig, "fig3_ucurve.png")

# --- Fig 4: topology, both redistribution rules ------------------------
fig, axes = plt.subplots(1, 2, figsize=(11.5, 3.7), sharey=True)
for ax, rule, title in zip(
        axes, ("legacy", "serving_neighbours"),
        ("(a) shared across all neighbours", "(b) shared across live neighbours only")):
    t = NUM["topology"][rule]
    names = list(t.keys())
    x = np.arange(len(names))
    w = 0.27
    ax.bar(x - w, [t[n]["pct_zero"] for n in names], w, label="negligible",
           color="#c3c2b7")
    ax.bar(x, [t[n]["pct_intermediate"] for n in names], w,
           label="intermediate", color="#2a78d6")
    ax.bar(x + w, [t[n]["pct_total"] for n in names], w, label="near-total",
           color="#e34948")
    ax.set_xticks(x)
    ax.set_xticklabels([n.replace("-", "-\n") for n in names], fontsize=8)
    ax.set_title(title)
axes[0].set_ylabel("% of 300 single-cell failures")
axes[0].legend(fontsize=8)
save(fig, "fig4_topology.png")

print("done.")
