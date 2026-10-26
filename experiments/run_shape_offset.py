"""Does a shape offset close the gap that the level-only offset leaves open?

The learning curve showed an unpooled local refit beating the hierarchical model
from roughly ten local records upward, which inverts the expected ordering. The
diagnosis is that regional variation lives in the *slope* of the depth response,
not only its level, and a four-parameter offset can only move the level.

This experiment tests the fix directly: the same hierarchy, the same data, the
same held-out sample, with a fifth offset component that scales the depth
response. Three arms are compared at each local sample size:

    level only    the shipped 4-parameter offset
    + shape       5 parameters, the proposed fix
    unpooled      a full 32-parameter refit on the local sample alone
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np
import pandas as pd
from scipy.optimize import minimize

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from floodvuln import model as M                # noqa: E402
from floodvuln import validate as V             # noqa: E402
from floodvuln.calibrate import HierarchicalVulnerability  # noqa: E402

PROC = os.path.join(HERE, "..", "data", "processed")
REP = os.path.join(HERE, "..", "reports")

STATE, GK = "LA", "RES.SF.1.UNK"
SIZES = (0, 10, 25, 50, 100, 250, 1000, 5000)
REPEATS = 6
N_TEST = 12000
# Prior scale on the shape offset. Wide enough to be led by data at moderate n,
# tight enough that a handful of records cannot invent a slope.
TAU_SHAPE = 0.35


def fit_offset(theta, cells, base, tau, k):
    """Fit a k-element offset under a Gaussian shrinkage prior."""
    tau = np.asarray(tau, float)[:k]

    def obj(o):
        full = np.concatenate([base[:4] + o[:4], [base[4] + o[4]] if k == 5 else []])
        return (M.neg_loglik(theta, cells, full, 0.0)
                + 0.5 * float(np.sum((o / np.maximum(tau, 1e-6)) ** 2)))

    r = minimize(obj, np.zeros(k), method="L-BFGS-B",
                 options={"maxiter": 400, "ftol": 1e-11})
    out = np.zeros(5)
    out[:k] = r.x
    return out


def main() -> None:
    df = pd.read_csv(os.path.join(PROC, "calibration.csv"), low_memory=False,
                     usecols=["group_key", "state", "depth_m", "damage_ratio"])
    hv = HierarchicalVulnerability.load(os.path.join(PROC, "model_global.json"))

    # refit the archetype level without the target state, so nothing leaks
    tr = df[df.state != STATE]
    trg = tr[tr.group_key == GK]
    cells_arch = M.make_cells(trg.depth_m.values, trg.damage_ratio.values)
    base4 = M.fit_offsets(cells_arch, hv.theta, tau=hv.tau_arch)
    base = np.concatenate([base4, [0.0]])
    print(f"archetype offset refitted without {STATE}: {np.round(base4, 3)}")

    loc = df[(df.state == STATE) & (df.group_key == GK)].reset_index(drop=True)
    rng = np.random.default_rng(23)
    perm = rng.permutation(len(loc))
    test = loc.iloc[perm[:N_TEST]]
    pool = loc.iloc[perm[N_TEST:]]
    y = test.damage_ratio.values
    dt = test.depth_m.values
    print(f"local pool={len(pool):,}  test={len(test):,}")

    tau5 = np.concatenate([hv.tau_local, [TAU_SHAPE]])
    rows = []
    t0 = time.time()
    for n in SIZES:
        reps = 1 if n == 0 else REPEATS
        for rep in range(reps):
            if n == 0:
                arms = {"level only": base, "+ shape": base}
            else:
                take = rng.choice(len(pool), size=min(n, len(pool)), replace=False)
                s = pool.iloc[take]
                c = M.make_cells(s.depth_m.values, s.damage_ratio.values)
                arms = {
                    "level only": base + fit_offset(hv.theta, c, base, hv.tau_local, 4),
                    "+ shape": base + fit_offset(hv.theta, c, base, tau5, 5),
                }
            for name, off in arms.items():
                p = M.predict_params(hv.theta, dt, off)
                mean, _ = M.moments(*p)
                r = V.Forecast(name, "probabilistic", mean, p).score(y)
                r.update(n_local=n, rep=rep, arm=name)
                rows.append(r)

            if n >= 10:
                take = rng.choice(len(pool), size=min(n, len(pool)), replace=False)
                s = pool.iloc[take]
                try:
                    g = M.fit_global(M.make_cells(s.depth_m.values, s.damage_ratio.values),
                                     maxiter=300)
                    p = M.predict_params(g["theta"], dt)
                    mean, _ = M.moments(*p)
                    r = V.Forecast("unpooled", "probabilistic", mean, p).score(y)
                    r.update(n_local=n, rep=rep, arm="unpooled")
                    rows.append(r)
                except Exception:  # noqa: BLE001
                    pass
        print(f"  n={n:>5}  ({time.time() - t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(REP, "bench_shape_offset.csv"), index=False)

    piv = out.groupby(["arm", "n_local"])[["MAE", "CRPS", "coverage_80"]].mean()
    print(f"\n=== {STATE} / {GK}: does a shape offset fix the pooling? ===")
    print(f"{'n':>6} | {'level only':>18} | {'+ shape':>18} | {'unpooled':>18}")
    print(f"{'':>6} | {'MAE':>8} {'CRPS':>9} | {'MAE':>8} {'CRPS':>9} | {'MAE':>8} {'CRPS':>9}")
    for n in SIZES:
        cells = []
        for arm in ("level only", "+ shape", "unpooled"):
            if (arm, n) in piv.index:
                r = piv.loc[(arm, n)]
                cells.append(f"{r['MAE']:8.4f} {r['CRPS']:9.4f}")
            else:
                cells.append(f"{'-':>8} {'-':>9}")
        print(f"{n:>6} | {cells[0]} | {cells[1]} | {cells[2]}")

    print("\nCRPS change from level-only to +shape, by n:")
    for n in SIZES:
        if ("level only", n) in piv.index and ("+ shape", n) in piv.index:
            a = piv.loc[("level only", n), "CRPS"]
            b = piv.loc[("+ shape", n), "CRPS"]
            print(f"  n={n:>5}: {100 * (b - a) / a:+6.1f}%")


if __name__ == "__main__":
    main()
