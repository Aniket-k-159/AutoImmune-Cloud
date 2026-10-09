"""
Regenerate every number quoted in the report, against the corrected model.

Run from the project root:   python -I experiments/report_numbers.py

Writes data/report_numbers.json and prints a readable summary. Nothing in the
report is quoted from memory: each figure here is produced by this script and
the JSON is committed alongside it.

Protocol choices, and why:

  randomness="split"       detector settings must see the same faults, or a
                           comparison between them is not a comparison.
                           (correction issue #4)
  steps=150                stochastic runs need an explicit horizon; a quiet
                           timestep is not a fixed point. (issue #1)
  redistribution           both rules are measured. "legacy" spreads across all
                           static neighbours and records what lands on dead
                           cells as dropped; "serving_neighbours" spreads only
                           across live cells. (issue #2)
"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "utils"))

import numpy as np
from lattice import LatticeCA, run_trial, run_episode, sweep_theta
from graph_ca import (run_trial as g_trial, grid_graph, erdos_renyi_graph, scale_free_graph,
                      small_world_graph, avalanche_sizes, sweep_theta as g_sweep)

OUT = {}
t0 = time.time()
HORIZON = 150
ALPHA = 0.6


def head(t):
    print(f"\n{'=' * 68}\n{t}\n{'=' * 68}")


# ---------------------------------------------------------------- gate 1
head("GATE 1  overload threshold   alpha_c = 1/|N|")
g1 = []
for nb, deg in (("von_neumann", 4), ("moore", 8)):
    pred = 1.0 / deg
    meas = float("nan")
    for a in np.linspace(0.01, 0.40, 391):
        if run_trial(a, 41, 41, neighbourhood=nb, load_sigma=0.0,
                     seed=1)["removed"] <= 1:
            meas = float(a)
            break
    g1.append({"neighbourhood": nb, "degree": deg,
               "predicted": pred, "measured": meas})
    print(f"  {nb:12s} |N|={deg}  predicted {pred:.4f}  measured {meas:.4f}"
          f"  err {abs(meas - pred):.4f}")
OUT["gate_alpha_c"] = g1

# ---------------------------------------------------------------- gate 2
head("GATE 2  detector threshold   theta_c = (1 + 1/|N|)/(1 + alpha)")
g2 = []
for nb, deg in (("von_neumann", 4), ("moore", 8)):
    for a in (0.4, 0.6, 0.8, 1.0):
        pred = (1 + 1 / deg) / (1 + a)
        meas = float("nan")
        for th in np.arange(pred + 0.06, 0.0, -0.002):
            if run_trial(a, 50, 50, neighbourhood=nb, theta=float(th),
                         noise=0.0, load_sigma=0.0,
                         seed=5)["removed_fraction"] > 0.5:
                meas = float(th)
                break
        g2.append({"neighbourhood": nb, "degree": deg, "alpha": a,
                   "predicted": pred, "measured": meas})
        print(f"  {nb:12s} alpha={a:.1f}  predicted {pred:.4f}"
              f"  measured {meas:.4f}  err {abs(meas - pred):.4f}")
OUT["gate_theta_c"] = g2

# ------------------------------------------------- headline, fixed horizon
head(f"HEADLINE  alpha={ALPHA} (alpha_c=0.25, so subcritical), {HORIZON} steps")
theta_c = (1 + 1 / 4) / (1 + ALPHA)
print(f"  theta_c = {theta_c:.3f}\n")
print(f"  {'detector':>12}{'removed':>10}{'overload':>10}{'quarant':>10}")
head_rows = []
for th in (np.inf, 0.90, 0.85, 0.82, 0.80, 0.78, 0.70):
    r = run_trial(ALPHA, 60, 60, theta=float(th), noise=0.02, load_sigma=0.0,
                  seed=3, steps=HORIZON, randomness="split")
    lbl = "off" if not np.isfinite(th) else f"theta={th:.2f}"
    head_rows.append({"theta": None if not np.isfinite(th) else float(th),
                      "removed_fraction": r["removed_fraction"],
                      "overload": r["overload"], "quarantined": r["quarantined"]})
    print(f"  {lbl:>12}{r['removed_fraction']:>10.4f}{r['overload']:>10}"
          f"{r['quarantined']:>10}")
OUT["headline"] = {"alpha": ALPHA, "theta_c": theta_c, "steps": HORIZON,
                   "rows": head_rows}

# ------------------------------------------------------------- the U-curve
head("U-CURVE  damage vs detector threshold (split randomness)")
thetas = np.arange(0.70, 1.22, 0.02)
ucurve = {}
for redis in ("legacy", "serving_neighbours"):
    r = sweep_theta(thetas, alpha=ALPHA, replicates=8, steps=HORIZON,
                    width=50, height=50, noise=0.03, fault_rate=2e-4, seed=1,
                    redistribution=redis, randomness="split")
    i = int(np.argmin(r["total_damage"]))
    d = r["total_damage"]
    collapse = None
    for j in range(i, -1, -1):
        if d[j] > 0.5:
            collapse = float(thetas[j])
            break
    ucurve[redis] = {
        "thetas": thetas.tolist(),
        "total_damage": d.tolist(),
        "unremediated": r["unremediated"].tolist(),
        "overload": r["overload"].tolist(),
        "false_positive": r["false_positive"].tolist(),
        "theta_star": float(thetas[i]), "min_damage": float(d[i]),
        "damage_detector_off": float(d[-1]), "collapse_below": collapse,
    }
    print(f"  {redis:20s} best theta {thetas[i]:.2f}  min damage {d[i]:.3f}"
          f"  detector-off {d[-1]:.3f}  collapses below {collapse}")
OUT["ucurve"] = ucurve

# steepness of the collapse, aggressive arm only
head("COLLAPSE SHARPNESS  (aggressive arm, finer grid)")
fine = np.arange(0.86, 1.02, 0.01)
rf = sweep_theta(fine, alpha=ALPHA, replicates=12, steps=HORIZON, width=50,
                 height=50, noise=0.03, fault_rate=2e-4, seed=7,
                 randomness="split")
df = rf["total_damage"]
jump = int(np.argmax(np.abs(np.diff(df))))
peak = float(fine[int(np.argmax(rf["susceptibility"]))])
OUT["collapse"] = {"thetas": fine.tolist(), "total_damage": df.tolist(),
                   "from_theta": float(fine[jump]), "to_theta": float(fine[jump + 1]),
                   "from_damage": float(df[jump]), "to_damage": float(df[jump + 1]),
                   "pct_change": float(abs(df[jump + 1] - df[jump]) / max(df[jump], 1e-9)),
                   "susceptibility_peak": peak}
print(f"  steepest step: {df[jump]:.3f} -> {df[jump+1]:.3f} as theta moves "
      f"{fine[jump]:.2f} -> {fine[jump+1]:.2f}")
print(f"  that is a {100*abs(df[jump+1]-df[jump])/max(df[jump],1e-9):.0f}% change "
      f"for a 0.01 threshold change")
print(f"  susceptibility peak at theta = {peak:.2f}")

# ------------------------------------------------- theta* tracks theta_c
head("OPTIMUM vs ANALYTIC CLIFF   theta* / theta_c across alpha")
ratio = []
for a in (0.4, 0.6, 0.8, 1.0):
    r = sweep_theta(thetas, alpha=a, replicates=8, steps=HORIZON, width=50,
                    height=50, noise=0.03, fault_rate=2e-4, seed=1,
                    randomness="split")
    ts = float(thetas[int(np.argmin(r["total_damage"]))])
    tc = (1 + 1 / 4) / (1 + a)
    ratio.append({"alpha": a, "theta_c": tc, "theta_star": ts, "ratio": ts / tc})
    print(f"  alpha={a:.1f}  theta_c={tc:.4f}  theta*={ts:.2f}  ratio={ts/tc:.2f}")
OUT["optimum_ratio"] = ratio

# ------------------------------------------------- separability condition
head("SEPARABILITY   minimum fault signal for any safe threshold to exist")


def min_damage(alpha, delta, sigma):
    th = np.arange(0.50, 1.70, 0.05)
    r = sweep_theta(th, alpha=alpha, replicates=3, steps=100, width=30,
                    height=30, noise=sigma, fault_rate=3e-4,
                    fault_signal=delta, seed=1, randomness="split")
    return float(np.min(r["total_damage"]))


sigma = 0.03
sep = []
for a in (0.4, 0.6, 0.8, 1.0):
    floor = (1 / 4) / (1 + a)
    meas = float("nan")
    for delta in np.arange(0.06, 0.60, 0.02):
        if min_damage(a, float(delta), sigma) < 0.5:
            meas = float(delta)
            break
    sep.append({"alpha": a, "floor": floor, "measured": meas,
                "margin_sigma": (meas - floor) / sigma})
    print(f"  alpha={a:.1f}  floor {floor:.4f}  onset {meas:.3f}"
          f"  margin {(meas-floor)/sigma:.1f} sigma")
OUT["separability"] = {"sigma": sigma, "rows": sep}

# ------------------------------------------------------------- topology
head("TOPOLOGY   outcome distributions, matched n and mean degree")
N = 900
TOPO = {"lattice": grid_graph(30, 30),
        "small-world": small_world_graph(N, 4, 0.1, seed=1),
        "random": erdos_renyi_graph(N, 4.0, seed=1),
        "scale-free": scale_free_graph(N, 2, seed=1)}
topo = {}
for redis in ("legacy", "serving_neighbours"):
    print(f"\n  redistribution = {redis}")
    print(f"  {'topology':>12}{'std k':>8}{'% zero':>9}{'% mid':>8}{'% total':>9}{'mean':>9}")
    topo[redis] = {}
    for name, G in TOPO.items():
        s, _ = avalanche_sizes(G, 0.25, trials=300, seed=2,
                               redistribution=redis)
        f = s / N
        d = np.array([G.degree(i) for i in G.nodes()])
        topo[redis][name] = {
            "std_degree": float(d.std()),
            "pct_zero": float(100 * np.mean(f < 0.02)),
            "pct_intermediate": float(100 * np.mean((f >= 0.02) & (f <= 0.9))),
            "pct_total": float(100 * np.mean(f > 0.9)),
            "mean_size": float(s.mean()), "max_size": int(s.max()),
        }
        t = topo[redis][name]
        print(f"  {name:>12}{t['std_degree']:>8.2f}{t['pct_zero']:>9.1f}"
              f"{t['pct_intermediate']:>8.1f}{t['pct_total']:>9.1f}{t['mean_size']:>9.1f}")
OUT["topology"] = topo

# local threshold: does alpha >= 1/k_j still hold exactly?
head("LOCAL THRESHOLD   cascades propagate only from cells with k < 1/alpha")
G = TOPO["scale-free"]
sizes, degrees = avalanche_sizes(G, 0.25, trials=800, seed=3)
below = sizes[degrees < 4]
above = sizes[degrees >= 4]
OUT["local_threshold"] = {
    "alpha": 0.25, "cutoff_degree": 4,
    "n_below": int(below.size), "pct_below_spread": float(np.mean(below > 5)),
    "n_above": int(above.size), "max_above": int(above.max()) if above.size else 0,
}
print(f"  seeded below k=4: {below.size} trials, {100*np.mean(below>5):.1f}% spread")
print(f"  seeded at k>=4 : {above.size} trials, max avalanche "
      f"{above.max() if above.size else 0}")

# hubs: firebreaks or not, under each redistribution rule
head("HUBS   avalanche from the 5 highest- and 5 lowest-degree cells")
d = np.array([G.degree(i) for i in G.nodes()])
order = np.argsort(-d)
hubs = {}
for redis in ("legacy", "serving_neighbours"):


    hi = [int(g_trial(G, 0.25, seed_node=int(n), seed=1,
                      redistribution=redis)["avalanche_size"]) for n in order[:5]]
    lo = [int(g_trial(G, 0.25, seed_node=int(n), seed=1,
                      redistribution=redis)["avalanche_size"]) for n in order[-5:]]
    hubs[redis] = {"high_degree": [int(d[n]) for n in order[:5]],
                   "high_avalanche": hi,
                   "low_degree": [int(d[n]) for n in order[-5:]],
                   "low_avalanche": lo}
    print(f"  {redis:20s} hubs {hi}   low-degree {lo}")
OUT["hubs"] = hubs

# ------------------------------------------------------------------ save
OUT["meta"] = {"horizon": HORIZON, "alpha": ALPHA,
               "randomness": "split", "generated_seconds": round(time.time() - t0, 1)}
path = os.path.join(os.path.dirname(__file__), "..", "data", "report_numbers.json")
with open(path, "w") as fh:
    json.dump(OUT, fh, indent=1)
print(f"\nwrote {os.path.relpath(path)}   ({time.time()-t0:.0f}s)")
