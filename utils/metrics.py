"""
Measurement helpers used across notebooks.

Two things worth doing properly rather than by eye:

  * locating a critical point, via the susceptibility peak rather than by
    inspecting a curve
  * deciding whether an avalanche-size distribution is heavy-tailed, via
    maximum-likelihood fitting and a likelihood-ratio test rather than by
    drawing a straight line through a log-log histogram, which is known to be
    unreliable (Clauset, Shalizi & Newman, 2009)
"""

import numpy as np


def susceptibility(values):
    """Variance of an order parameter across replicates.

    Far from a critical point repeated runs agree, so the variance is small.
    Near it, identical parameters give very different outcomes and the variance
    peaks. Its maximum is a defensible numerical estimate of the critical point.
    """
    return float(np.var(np.asarray(values, dtype=float)))


def critical_point(control, susceptibilities):
    """The control-parameter value at which susceptibility peaks."""
    control = np.asarray(control, dtype=float)
    return float(control[int(np.argmax(np.asarray(susceptibilities)))])


def ccdf(samples):
    """Complementary CDF, P(X >= x), for plotting on log-log axes."""
    x = np.sort(np.asarray(samples, dtype=float))
    return x, 1.0 - np.arange(len(x)) / len(x)


def mle_power_law(samples, xmin=None):
    """
    Maximum-likelihood exponent for a discrete power law above `xmin`.

    Uses the standard continuous approximation with the +0.5 discreteness
    correction. If `xmin` is not given it is chosen by minimising the
    Kolmogorov-Smirnov distance between the empirical and fitted CCDFs, which
    is the Clauset-Shalizi-Newman procedure.

    Returns (alpha, xmin, n_tail, ks_distance).
    """
    x = np.asarray(samples, dtype=float)
    x = x[x > 0]
    if x.size < 10:
        return np.nan, np.nan, 0, np.nan

    def fit_at(xm):
        tail = x[x >= xm]
        if tail.size < 10:
            return np.nan, np.nan
        a = 1.0 + tail.size / np.sum(np.log(tail / (xm - 0.5)))
        srt = np.sort(tail)
        emp = np.arange(srt.size) / srt.size
        theo = 1.0 - (srt / xm) ** (1.0 - a)
        return a, float(np.max(np.abs(emp - theo)))

    if xmin is not None:
        a, ks = fit_at(float(xmin))
        return a, float(xmin), int(np.sum(x >= xmin)), ks

    candidates = np.unique(x)
    if candidates.size < 10:
        # too few distinct values to choose an xmin: the sample has no tail to
        # speak of (a bimodal all-or-nothing distribution does this)
        return np.nan, np.nan, 0, np.nan

    best = (np.nan, np.nan, 0, np.inf)
    for xm in candidates[:-9]:
        a, ks = fit_at(xm)
        if np.isfinite(ks) and ks < best[3]:
            best = (a, float(xm), int(np.sum(x >= xm)), ks)
    return best if np.isfinite(best[3]) else (np.nan, np.nan, 0, np.nan)


def loglik_ratio_exponential(samples, xmin, alpha):
    """
    Vuong-style likelihood-ratio test of a power law against an exponential
    tail, both fitted above `xmin`.

    Returns (R, p). R > 0 favours the power law, R < 0 the exponential; p is
    the two-sided significance of R. A large p means the data cannot
    distinguish the two, which is an honest answer and should be reported as
    one rather than hidden.
    """
    from math import erfc, sqrt

    x = np.asarray(samples, dtype=float)
    tail = x[x >= xmin]
    n = tail.size
    if n < 10:
        return np.nan, np.nan

    ll_pl = np.log((alpha - 1.0) / xmin) - alpha * np.log(tail / xmin)
    lam = 1.0 / np.mean(tail - xmin) if np.mean(tail - xmin) > 0 else np.nan
    if not np.isfinite(lam):
        return np.nan, np.nan
    ll_ex = np.log(lam) - lam * (tail - xmin)

    diff = ll_pl - ll_ex
    R = float(np.sum(diff))
    sigma = float(np.std(diff))
    if sigma == 0:
        return R, np.nan
    p = erfc(abs(R) / (sqrt(2.0 * n) * sigma))
    return R, float(p)


def bimodality(samples, total, low=0.02, high=0.90):
    """
    Fraction of outcomes at each extreme.

    An all-or-nothing transition puts nearly every outcome in one of the two
    tails and almost none in between, which is qualitatively different from a
    scale-free cascade where events of every size occur. Reporting this
    distinguishes the two rather than forcing a power-law fit onto a
    distribution that has no tail.
    """
    f = np.asarray(samples, dtype=float) / total
    n = f.size
    if n == 0:
        return {"n": 0}
    return {
        "n": n,
        "frac_negligible": float(np.mean(f < low)),
        "frac_total": float(np.mean(f > high)),
        "frac_intermediate": float(np.mean((f >= low) & (f <= high))),
    }


def describe_tail(samples, label=""):
    """Summary of a sample's tail behaviour, for printing in a notebook."""
    x = np.asarray(samples, dtype=float)
    x = x[x > 0]
    pad = " " * len(label)
    if x.size == 0:
        return f"{label}no non-zero events"

    head = (f"{label}n={x.size}  median={np.median(x):.0f}  "
            f"mean={x.mean():.1f}  max={x.max():.0f}  "
            f"mean/median={x.mean() / max(np.median(x), 1):.1f}")

    a, xmin, n_tail, ks = mle_power_law(x)
    if not np.isfinite(a):
        return (head + f"\n{pad}too few distinct sizes for a tail fit -- the "
                       f"distribution has no scale-free range")

    R, p = loglik_ratio_exponential(x, xmin, a)
    verdict = ("power law favoured" if (R > 0 and np.isfinite(p) and p < 0.1)
               else "inconclusive")
    return (head +
            f"\n{pad}MLE power law: alpha={a:.2f}, xmin={xmin:.0f}, "
            f"n_tail={n_tail}, KS={ks:.3f}"
            f"\n{pad}vs exponential: R={R:.1f}, p={p:.3f} ({verdict})")
