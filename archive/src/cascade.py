"""
Load-redistribution cascade on a replicated service platform.

A replica whose load exceeds its capacity fails. Its share of its role's demand
moves to surviving peers, which may push them over in turn. If a role loses
every replica, calls to it fail and its callers pay a retry cost, which
propagates load upstream.

This is the published baseline mechanism (Motter-Lai style load redistribution,
adapted to replicated services). Nothing here knows about detectors or
quarantine -- it is reproduced first so the detector-driven cascade in later
steps can be compared against a mechanism known to be correct.
"""

import numpy as np

from network import propagate_load, assign_capacity


def cascade(P, capacity, seed_down, external_rate=100.0, retry_cost=0.0,
            max_rounds=500):
    """
    Run a load-redistribution cascade from an initial removal.

    Returns a dict with the failed set, the subset that failed by overload,
    the number of redistribution rounds, the per-round failed count, and the
    share of the intact system's served work still carried at the fixed point.
    """
    down = set(seed_down)
    overloaded = set()
    history = [len(down)]

    L0, _ = propagate_load(P, external_rate=external_rate,
                           retry_cost=retry_cost)
    total0 = sum(L0.values())

    rounds = 0
    for rounds in range(1, max_rounds + 1):
        L, _ = propagate_load(P, external_rate=external_rate, down=down,
                              retry_cost=retry_cost)
        newly = {n for n in P.nodes
                 if n not in down and L[n] > capacity[n] + 1e-12}
        if not newly:
            rounds -= 1
            break
        down |= newly
        overloaded |= newly
        history.append(len(down))
    else:
        raise RuntimeError("cascade did not reach a fixed point")

    L_end, dead_roles = propagate_load(P, external_rate=external_rate,
                                       down=down, retry_cost=retry_cost)
    served = sum(L_end.values()) / total0 if total0 > 0 else 0.0

    return {
        "failed": down,
        "overloaded": overloaded,
        "dead_roles": dead_roles,
        "rounds": rounds,
        "history": history,
        "served_fraction": served,
    }


def run_trial(P, alpha, trigger="random", rng=None, external_rate=100.0,
              retry_cost=0.0):
    """
    One cascade trial: capacity is set from the intact load, one replica is
    removed, and the consequences are allowed to play out.

    trigger : "random"  uniformly chosen replica (accidental failure)
              "hub"     a replica of the highest-demand role (targeted)
    """
    rng = np.random.default_rng() if rng is None else rng
    L0, _ = propagate_load(P, external_rate=external_rate,
                           retry_cost=retry_cost)
    C = assign_capacity(L0, alpha)

    if trigger == "hub":
        busiest_role = max(P.roles.nodes(),
                           key=lambda r: sum(L0[i] for i in P.members[r]))
        seed = P.members[busiest_role][0]
    elif trigger == "random":
        seed = int(rng.choice(P.nodes))
    else:
        raise ValueError(f"unknown trigger: {trigger}")

    res = cascade(P, C, {seed}, external_rate=external_rate,
                  retry_cost=retry_cost)
    res["seed_node"] = seed
    res["failed_fraction"] = len(res["failed"]) / P.n_nodes
    res["avalanche_size"] = len(res["failed"]) - 1   # excluding the trigger
    return res


def sweep_alpha(P, alphas, trigger="random", replicates=30, seed=0,
                external_rate=100.0, retry_cost=0.0):
    """
    Sweep spare capacity and record the order parameter.

    Returns mean failed fraction, its standard deviation, mean served fraction,
    and susceptibility (variance across replicates, which peaks at the critical
    point and gives a numerical estimate of it).
    """
    rng = np.random.default_rng(seed)
    mean_failed, std_failed, mean_served, susceptibility = [], [], [], []

    for a in alphas:
        fracs, served = [], []
        for _ in range(replicates):
            r = run_trial(P, a, trigger=trigger, rng=rng,
                          external_rate=external_rate, retry_cost=retry_cost)
            fracs.append(r["failed_fraction"])
            served.append(r["served_fraction"])
        fracs = np.asarray(fracs)
        mean_failed.append(fracs.mean())
        std_failed.append(fracs.std())
        mean_served.append(float(np.mean(served)))
        susceptibility.append(fracs.var())

    return (np.asarray(mean_failed), np.asarray(std_failed),
            np.asarray(mean_served), np.asarray(susceptibility))
