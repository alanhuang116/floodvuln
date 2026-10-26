"""Figures for the calibration report, in the product's own palette."""
from __future__ import annotations

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np              # noqa: E402
import pandas as pd             # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from floodvuln import evidence as EV            # noqa: E402
from floodvuln import model as M                # noqa: E402
from floodvuln.calibrate import HierarchicalVulnerability  # noqa: E402

PROC = os.path.join(HERE, "..", "data", "processed")
REP = os.path.join(HERE, "..", "reports")
FIG = os.path.join(HERE, "..", "figures")

TEAL, AMBER, SLATE, ALARM = "#008C7D", "#C2751A", "#3059AE", "#B32D3B"
INK, GREY, GRID = "#08191D", "#75898B", "#E3EAE9"

plt.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 150, "font.size": 9,
    "axes.edgecolor": GREY, "axes.linewidth": 0.8, "axes.grid": True,
    "grid.color": GRID, "grid.linewidth": 0.7, "axes.axisbelow": True,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": "white", "savefig.bbox": "tight",
    "font.family": "DejaVu Sans",
})


def load():
    df = pd.read_csv(os.path.join(PROC, "calibration.csv"), low_memory=False,
                     usecols=["group_key", "state", "depth_m", "damage_ratio", "floodEvent"])
    hv = HierarchicalVulnerability.load(os.path.join(PROC, "model_global.json"))
    return df, hv


def fig_depth_damage(df, hv):
    groups = [("RES.SF.1.SLAB", "1 storey, slab", TEAL),
              ("RES.SF.2.BASEMENT", "2 storey, basement", SLATE),
              ("RES.SF.MH.UNK", "manufactured home", AMBER)]
    d = np.linspace(-1.5, 5.0, 300)
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4), sharey=True)
    for ax, (gk, lab, col) in zip(axes, groups):
        s = df[df.group_key == gk]
        if len(s) < 300:
            ax.set_visible(False)
            continue
        p = hv.params(d, gk)
        mean, _ = M.moments(*p)
        lo = M.quantile(np.full(len(d), .10), *p)
        hi = M.quantile(np.full(len(d), .90), *p)
        ax.fill_between(d, lo, hi, color=col, alpha=.16, lw=0, label="P10-P90")
        ax.plot(d, mean, color=col, lw=2.2, label="fitted mean")

        edges = np.array([-1.5, -0.6, -0.15, 0.01, 0.3, 0.6, 0.95, 1.4, 2.0, 2.8, 4.0])
        idx = np.clip(np.searchsorted(edges, s.depth_m, side="right") - 1, 0, len(edges) - 2)
        xs, ys, ns = [], [], []
        for b in range(len(edges) - 1):
            m = idx == b
            if m.sum() >= 40:
                xs.append(s.depth_m[m].mean()); ys.append(s.damage_ratio[m].mean())
                ns.append(m.sum())
        ax.scatter(xs, ys, s=np.clip(np.array(ns) / 220, 12, 90), color=INK,
                   zorder=5, label="observed bin mean", edgecolor="white", linewidth=.6)
        ax.set_title(f"{lab}\nn = {len(s):,}", fontsize=9.5, color=INK)
        ax.set_xlabel("depth above lowest floor (m)")
        ax.set_xlim(-1.5, 5); ax.set_ylim(0, 1)
    axes[0].set_ylabel("damage ratio")
    axes[0].legend(frameon=False, fontsize=8, loc="upper left")
    fig.suptitle("Fitted vulnerability against observed NFIP claims, by archetype",
                 fontsize=11, color=INK, y=1.04)
    fig.savefig(os.path.join(FIG, "fig1_depth_damage.png"))
    plt.close(fig)


def fig_distribution(df, hv):
    gk = "RES.SF.1.SLAB"
    s = df[df.group_key == gk]
    bands = [(0.0, 0.35, "0.0-0.35 m"), (0.55, 0.95, "0.55-0.95 m"), (1.4, 2.4, "1.4-2.4 m")]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.2), sharey=True)
    for ax, (lo, hi, lab) in zip(axes, bands):
        m = s.depth_m.between(lo, hi)
        v = s.damage_ratio[m]
        ax.hist(v, bins=np.linspace(0, 1, 41), density=True, color=GRID,
                edgecolor=GREY, linewidth=.4, label=f"observed (n={m.sum():,})")
        dmid = (lo + hi) / 2
        p0, p1c, mu, phi = hv.params(np.array([dmid]), gk)
        from scipy.stats import beta as B
        x = np.linspace(.001, .999, 400)
        mid = float((1 - p0[0]) * (1 - p1c[0]))
        ax.plot(x, mid * B.pdf(x, mu[0] * phi[0], (1 - mu[0]) * phi[0]),
                color=TEAL, lw=2, label="fitted ZOIB density")
        ax.axvline(float(M.moments(p0, p1c, mu, phi)[0][0]), color=AMBER, lw=1.8,
                   label="fitted mean")
        ax.set_title(lab, fontsize=9.5, color=INK)
        ax.set_xlabel("damage ratio")
    axes[0].set_ylabel("density")
    axes[0].legend(frameon=False, fontsize=7.5)
    fig.suptitle("Observed damage-ratio distribution at fixed depth, single-family slab",
                 fontsize=11, color=INK, y=1.05)
    fig.savefig(os.path.join(FIG, "fig2_distribution.png"))
    plt.close(fig)


def fig_learning_curve():
    p = os.path.join(REP, "bench_learning_curve.csv")
    if not os.path.exists(p):
        return
    lc = pd.read_csv(p)
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 3.4))
    for ax, metric in zip(axes, ["MAE", "CRPS"]):
        for method, col, lab in [("hierarchical", AMBER, "hierarchical (partial pooling)"),
                                 ("local_only", SLATE, "local-only refit")]:
            g = lc[lc.method == method].groupby("n_local")[metric]
            mu_, sd = g.mean(), g.std()
            x = mu_.index.to_numpy()
            ax.plot(x, mu_.to_numpy(), color=col, lw=2, marker="o", ms=4, label=lab)
            ax.fill_between(x, (mu_ - sd).to_numpy(), (mu_ + sd).to_numpy(),
                            color=col, alpha=.15, lw=0)
        base = lc[(lc.method == "hierarchical") & (lc.n_local == 0)][metric].mean()
        ax.axhline(base, color=GREY, ls="--", lw=1.5, label="global prior, no local data")
        ax.set_xscale("symlog", linthresh=5)
        ax.set_xlabel("local observations used for calibration")
        ax.set_ylabel(metric)
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("Sparse-data learning curve in a held-out region", fontsize=11,
                 color=INK, y=1.03)
    fig.savefig(os.path.join(FIG, "fig3_learning_curve.png"))
    plt.close(fig)


def fig_jrc_vs_fitted(df, hv):
    curves = EV.load_curves()
    f = EV.curve_interpolator(curves, "Residential buildings", "North AMERICA")
    d = np.linspace(0, 5, 200)
    s = df[df.group_key.str.startswith("RES.SF")]
    edges = np.array([-0.2, 0.01, 0.3, 0.6, 0.95, 1.4, 2.0, 2.8, 4.0, 5.0])
    idx = np.clip(np.searchsorted(edges, s.depth_m, side="right") - 1, 0, len(edges) - 2)
    xs, ys = [], []
    for b in range(len(edges) - 1):
        m = idx == b
        if m.sum() >= 100:
            xs.append(s.depth_m[m].mean()); ys.append(s.damage_ratio[m].mean())

    fig, ax = plt.subplots(figsize=(6.6, 4.0))
    ax.plot(d, f(d), color=ALARM, lw=2.2, ls="--",
            label="JRC North America residential (published)")
    p = hv.params(d, "RES.SF.1.SLAB")
    ax.plot(d, M.moments(*p)[0], color=TEAL, lw=2.4, label="FloodVuln fitted, 1 storey slab")
    p2 = hv.params(d, "RES.SF.2.BASEMENT")
    ax.plot(d, M.moments(*p2)[0], color=SLATE, lw=2.0, label="FloodVuln fitted, 2 storey basement")
    ax.scatter(xs, ys, color=INK, s=34, zorder=6, edgecolor="white", linewidth=.7,
               label="observed NFIP bin mean, all single-family")
    ax.set_xlabel("depth above lowest floor (m)")
    ax.set_ylabel("damage ratio")
    ax.set_ylim(0, 1); ax.set_xlim(0, 5)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    ax.set_title("The published global prior against 1.86 million US claims",
                 fontsize=11, color=INK)
    fig.savefig(os.path.join(FIG, "fig4_jrc_vs_fitted.png"))
    plt.close(fig)


def fig_reliability(df, hv):
    """PIT and quantile reliability, archetype-only against locally calibrated.

    The comparison is the product thesis stated as a diagnostic: a national
    archetype curve applied to one region is visibly miscalibrated, and the
    local partial-pooling update is what removes the tilt.
    """
    ev = "Hurricane Harvey"
    s = df[df.floodEvent == ev]
    y = s.damage_ratio.to_numpy()
    d = s.depth_m.to_numpy()

    def params(level):
        p = np.empty((4, len(s)))
        gk = s.group_key.to_numpy()
        st = s.state.to_numpy()
        combo = np.char.add(np.char.add(gk.astype(str), "|"), st.astype(str))
        for k in np.unique(combo):
            m = combo == k
            a, l = k.split("|")
            o = hv.offsets_for(a, l if level == "local" else None, level)
            pp = M.predict_params(hv.theta, d[m], o)
            for i in range(4):
                p[i, m] = pp[i]
        return p

    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.5))
    levels = np.arange(0.05, 1.0, 0.05)
    for level, col, lab in [("archetype", SLATE, "archetype only (national)"),
                            ("local", TEAL, "locally calibrated (state)")]:
        p = params(level)
        pit = M.pit(y, p[0], p[1], p[2], p[3])
        axes[0].hist(pit, bins=20, range=(0, 1), density=True, histtype="step",
                     color=col, lw=2, label=lab)
        emp = [float(np.mean(y <= M.quantile(np.full(len(y), q), p[0], p[1], p[2], p[3])))
               for q in levels]
        axes[1].plot(levels, emp, color=col, lw=2.2, marker="o", ms=3.5, label=lab)
        ks = float(np.max(np.abs(np.sort(pit).searchsorted(levels) / len(pit) - levels)))
        print(f"   {level:10s} PIT KS = {ks:.3f}")

    axes[0].axhline(1.0, color=ALARM, ls="--", lw=1.5, label="calibrated")
    axes[0].set_xlabel("randomised PIT"); axes[0].set_ylabel("density")
    axes[0].set_title(f"PIT uniformity ({ev}, n={len(s):,})", fontsize=9.5, color=INK)
    axes[0].legend(frameon=False, fontsize=7.5)
    axes[1].plot([0, 1], [0, 1], color=ALARM, ls="--", lw=1.5, label="perfect")
    axes[1].set_xlabel("nominal quantile"); axes[1].set_ylabel("empirical coverage")
    axes[1].set_title("Quantile reliability", fontsize=9.5, color=INK)
    axes[1].legend(frameon=False, fontsize=7.5)
    fig.savefig(os.path.join(FIG, "fig5_reliability.png"))
    plt.close(fig)


def fig_shape_offset():
    p = os.path.join(REP, "bench_shape_offset.csv")
    if not os.path.exists(p):
        return
    d = pd.read_csv(p)
    g = d.groupby(["arm", "n_local"])["CRPS"].agg(["mean", "std"])
    fig, ax = plt.subplots(figsize=(6.8, 4.0))
    for arm, col, lab in [("level only", SLATE, "level-only offset (shipped)"),
                          ("+ shape", TEAL, "+ shape offset (proposed fix)"),
                          ("unpooled", ALARM, "unpooled local refit")]:
        if arm not in g.index.get_level_values(0):
            continue
        sub = g.loc[arm]
        x = sub.index.to_numpy()
        ax.plot(x, sub["mean"].to_numpy(), color=col, lw=2.2, marker="o", ms=4.5, label=lab)
        ax.fill_between(x, (sub["mean"] - sub["std"]).to_numpy(),
                        (sub["mean"] + sub["std"]).to_numpy(), color=col, alpha=.13, lw=0)
    ax.set_xscale("symlog", linthresh=10)
    ax.set_xlabel("local observations used for calibration")
    ax.set_ylabel("CRPS  (lower is better)")
    ax.set_title("A shape offset restores the partial-pooling advantage",
                 fontsize=11, color=INK)
    ax.legend(frameon=False, fontsize=8.5)
    fig.savefig(os.path.join(FIG, "fig6_shape_offset.png"))
    plt.close(fig)


def main():
    os.makedirs(FIG, exist_ok=True)
    df, hv = load()
    fig_depth_damage(df, hv); print("fig1")
    fig_distribution(df, hv); print("fig2")
    fig_learning_curve(); print("fig3")
    fig_jrc_vs_fitted(df, hv); print("fig4")
    fig_reliability(df, hv); print("fig5")
    fig_shape_offset(); print("fig6")


if __name__ == "__main__":
    main()
