"""
Shared figure helpers.

Keeping style and the lattice colour map here means every notebook produces
consistent figures and no notebook repeats plotting boilerplate.
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch

# consistent across every notebook, so a colour means the same thing throughout
COLOURS = {
    "layered": "#eb6834",
    "ba": "#2a78d6",
    "er": "#898781",
    "lattice": "#1baf7a",
    "unremediated": "#2a78d6",
    "overload": "#eda100",
    "false_positive": "#e34948",
    "total": "#0b0b0b",
}

# lattice cell states -> colour. Index order matches the state constants in
# src/lattice.py: HEALTHY, SHEDDING, DOWN, QUARANTINING, QUARANTINED, DEGRADED
STATE_COLOURS = ["#e8e6df",   # healthy      pale grey
                 "#f7b267",   # shedding     amber, transient
                 "#8a6a3a",   # down         brown, lost to overload
                 "#f08080",   # quarantining pink, transient
                 "#c0392b",   # quarantined  red, lost to the detector
                 "#6250d6"]   # degraded     violet, a genuine fault

STATE_LABELS = ["healthy", "shedding", "down (overload)",
                "quarantining", "quarantined (detector)", "degraded (fault)"]


def use_house_style():
    """Apply the project's matplotlib defaults. Call once per notebook."""
    plt.rcParams.update({
        "figure.dpi": 110,
        "font.size": 10,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titlesize": 11,
        "legend.frameon": False,
    })


def lattice_cmap():
    """Discrete colour map and norm for plotting a lattice state array."""
    cmap = ListedColormap(STATE_COLOURS)
    norm = BoundaryNorm(np.arange(-0.5, len(STATE_COLOURS) + 0.5), cmap.N)
    return cmap, norm


def show_lattice(state, ax=None, title=None, legend=False):
    """Render one lattice configuration."""
    if ax is None:
        _, ax = plt.subplots(figsize=(4, 4))
    cmap, norm = lattice_cmap()
    ax.imshow(state, cmap=cmap, norm=norm, interpolation="nearest")
    ax.set_xticks([]); ax.set_yticks([]); ax.grid(False)
    if title:
        ax.set_title(title)
    if legend:
        present = sorted(set(np.unique(state).tolist()))
        ax.legend(handles=[Patch(facecolor=STATE_COLOURS[s],
                                 label=STATE_LABELS[s]) for s in present],
                  loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8)
    return ax


def lattice_strip(snapshots, titles=None, figsize=None):
    """A row of lattice snapshots, for showing a cascade developing."""
    n = len(snapshots)
    fig, axes = plt.subplots(1, n, figsize=figsize or (2.6 * n, 2.9))
    axes = np.atleast_1d(axes)
    for k, (ax, snap) in enumerate(zip(axes, snapshots)):
        show_lattice(snap, ax=ax,
                     title=titles[k] if titles else f"t = {k}")
    fig.tight_layout()
    return fig, axes


def damage_decomposition(ax, thetas, parts, labels=None, colours=None):
    """
    Stacked area plot of damage by source against detector threshold.

    `parts` is a sequence of arrays in stacking order. Plotting the components
    rather than only the total is what makes a U-curve interpretable: the two
    arms of the U have different causes.
    """
    labels = labels or ["unremediated fault-time", "overload",
                        "false-positive quarantine"]
    colours = colours or [COLOURS["unremediated"], COLOURS["overload"],
                          COLOURS["false_positive"]]
    ax.stackplot(thetas, *parts, labels=labels, colors=colours, alpha=0.85)
    ax.set_xlabel(r"detector threshold $\theta$")
    ax.set_ylabel("damage (cell-equivalents per cell)")
    ax.legend(fontsize=8, loc="upper center")
    return ax


def mark_minimum(ax, x, y, label=None, colour="#0b0b0b"):
    """Annotate the interior minimum of a U-curve."""
    i = int(np.argmin(y))
    ax.axvline(x[i], color=colour, ls=":", lw=1)
    ax.annotate(label or f"min at {x[i]:.2f}",
                xy=(x[i], y[i]), xytext=(6, 14),
                textcoords="offset points", fontsize=8, color=colour)
    return x[i], y[i]
