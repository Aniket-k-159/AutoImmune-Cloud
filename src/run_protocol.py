"""Explicit stopping protocols shared by the two simulation models."""
import operator
import numpy as np


def _count(value, name, minimum):
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f"{name} must be an integer >= {minimum}")
    try:
        value = operator.index(value)
    except TypeError as exc:
        raise ValueError(f"{name} must be an integer >= {minimum}") from exc
    if value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _record(ca, start, protocol, requested, limit, reason):
    ca._run_info = dict(protocol=protocol, requested_steps=requested,
                        max_steps=limit, executed_steps=ca.t - start,
                        start_step=start, end_step=ca.t, stop_reason=reason)


def run_for(ca, steps):
    """Execute exactly `steps` additional updates, including quiet updates."""
    steps = _count(steps, "steps", 0)
    start = ca.t
    history = [ca.n_removed]
    for _ in range(steps):
        ca.step()
        history.append(ca.n_removed)
    _record(ca, start, "fixed_horizon", steps, None, "fixed_horizon")
    return history


def run_until_stable(ca, max_steps, transient_states):
    """Check a deterministic fixed point; a capped run is not convergence."""
    max_steps = _count(max_steps, "max_steps", 1)
    if ca.fault_rate > 0 or (np.isfinite(ca.theta) and ca.noise > 0):
        raise ValueError("Ongoing stochastic inputs require explicit steps: use run_for(steps)")
    start = ca.t
    history = [ca.n_removed]
    reason = "step_limit"
    for _ in range(max_steps):
        state, load = ca.state.copy(), ca.load.copy()
        changed = ca.step()
        if (changed == 0 and np.array_equal(state, ca.state)
                and np.array_equal(load, ca.load)
                and not np.isin(ca.state, transient_states).any()):
            reason = "fixed_point"
            break
        history.append(ca.n_removed)
    _record(ca, start, "deterministic", None, max_steps, reason)
    return history
