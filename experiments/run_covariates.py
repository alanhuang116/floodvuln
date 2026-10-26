"""Does adding hazard evidence beyond depth actually reduce error?

The product specification claims multivariable vulnerability helps "when data
permit", citing a study that reported roughly 20% MAE reduction. NFIP carries
one extra hazard variable at scale (`floodWaterDuration`) plus a cause-of-damage
code, so the claim is testable on this dataset rather than merely repeated.

The event-level bias found in the leave-one-event-out run motivates a second
question: is what is missing a *hazard* dimension, or an *event* effect that no
per-record covariate can absorb? Both are tested here.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from floodvuln import model as M                # noqa: E402
from floodvuln import validate as V             # noqa: E402
from floodvuln.calibrate import HierarchicalVulnerability  # noqa: E402

PROC = os.path.join(HERE, "..", "data", "processed")
REP = os.path.join(HERE, "..", "reports")

USE = ["group_key", "state", "depth_m", "damage_ratio", "floodEvent",
       "floodWaterDuration", "causeOfDamage", "yearOfLoss"]


def duration_band(v: pd.Series) -> pd.Series:
    x = pd.to_numeric(v, errors="coerce")
    return pd.cut(x, [-0.1, 0.9, 24, 72, 1e9],
                  labels=["none", "under_24h", "24_to_72h", "over_72h"])


def main() -> None:
    df = pd.read_csv(os.path.join(PROC, "calibration.csv"), low_memory=False,
                     usecols=lambda c: c in USE)
    df["dur"] = duration_band(df["floodWaterDuration"])
    print(f"rows {len(df):,}")
    print("\n=== floodWaterDuration availability and signal ===")
    t = (df.assign(d=df["dur"])
         .groupby("d", observed=True)
         .agg(n=("damage_ratio", "size"), mean_dr=("damage_ratio", "mean"),
              med_depth=("depth_m", "median")))
    t["share"] = (t["n"] / len(df)).round(4)
    print(t.round(3).to_string())

    # Depth is confounded with duration, so compare within depth bands.
    print("\n=== mean damage ratio by depth band x duration band ===")
    df["dband"] = pd.cut(df["depth_m"], [-2, 0.01, 0.35, 0.7, 1.2, 8],
                         labels=["<=0", "0-0.35", "0.35-0.7", "0.7-1.2", ">1.2"])
    piv = df.pivot_table(index="dband", columns="dur", values="damage_ratio",
                         aggfunc="mean", observed=True)
    cnt = df.pivot_table(index="dband", columns="dur", values="damage_ratio",
                         aggfunc="size", observed=True)
    print(piv.round(3).to_string())
    print("\ncounts:")
    print(cnt.to_string())

    # ---------------- does it improve out-of-sample prediction? ----------------
    print("\n=== leave-one-event-out with and without a duration stratum ===")
    rows = []
    for ev in ["Hurricane Katrina", "Hurricane Harvey", "Hurricane Sandy", "Hurricane Ike"]:
        te = df[df.floodEvent == ev]
        tr = df[df.floodEvent != ev]
        if len(te) < 5000:
            continue
        y = te["damage_ratio"].to_numpy()

        base = HierarchicalVulnerability.fit(
            tr["depth_m"].to_numpy(), tr["damage_ratio"].to_numpy(),
            tr["group_key"].to_numpy(), None, verbose=False, with_theta_cov=False)
        f0 = V.probabilistic_by_group(base, te["depth_m"].to_numpy(),
                                      te["group_key"].to_numpy(), None,
                                      "archetype", "depth_only")
        r0 = f0.score(y); r0.update(fold=ev, variant="depth + archetype")
        rows.append(r0)

        # archetype x duration as the grouping: the cheapest way to let the
        # hierarchy carry a second hazard dimension without changing the core
        trk = (tr["group_key"].astype(str) + "/"
               + tr["dur"].astype(str).fillna("none")).to_numpy()
        tek = (te["group_key"].astype(str) + "/"
               + te["dur"].astype(str).fillna("none")).to_numpy()
        dur_m = HierarchicalVulnerability.fit(
            tr["depth_m"].to_numpy(), tr["damage_ratio"].to_numpy(), trk, None,
            verbose=False, with_theta_cov=False, tau_arch=base.tau_arch)
        f1 = V.probabilistic_by_group(dur_m, te["depth_m"].to_numpy(), tek, None,
                                      "archetype", "depth_archetype_duration")
        r1 = f1.score(y); r1.update(fold=ev, variant="+ duration band")
        rows.append(r1)

        # Oracle event offset: fit a single 4-parameter shift on the held-out
        # event's own damage ratios. This is not a usable forecast, it is an
        # upper bound on what any amount of event-level information could buy,
        # and therefore separates "missing covariate" from "irreducible spread".
        cells = M.make_cells(te["depth_m"].to_numpy(), y)
        from floodvuln.calibrate import _fit_shifted
        ev_off = _fit_shifted(base.theta, cells, np.zeros(4), np.full(4, 5.0))
        p = np.empty((4, len(te)))
        for k in np.unique(te["group_key"].to_numpy()):
            m = (te["group_key"] == k).to_numpy()
            o = base.offsets_for(k, None, "archetype") + ev_off
            pp = M.predict_params(base.theta, te["depth_m"].to_numpy()[m], o)
            for i in range(4):
                p[i, m] = pp[i]
        mean, _ = M.moments(*p)
        r2 = V.Forecast("oracle_event_offset", "probabilistic", mean,
                        (p[0], p[1], p[2], p[3])).score(y)
        r2.update(fold=ev, variant="+ oracle event offset (upper bound)")
        rows.append(r2)

        print(f"  {ev}: n={len(te):,}  "
              f"MAE {r0['MAE']:.4f} -> {r1['MAE']:.4f} -> {r2['MAE']:.4f}   "
              f"CRPS {r0['CRPS']:.4f} -> {r1['CRPS']:.4f} -> {r2['CRPS']:.4f}", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(REP, "bench_covariates.csv"), index=False)
    print("\n=== mean over folds ===")
    print(out.groupby("variant")[["MAE", "RMSE", "bias", "CRPS", "coverage_80"]]
          .mean().round(4).to_string())


if __name__ == "__main__":
    main()
