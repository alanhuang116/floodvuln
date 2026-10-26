"""Calibration and validation run: the whole benchmark programme, end to end.

Outputs (all under reports/ and data/processed/):
    model_global.json          fitted hierarchy
    bench_hold_out_event.csv   leave-one-event-out
    bench_leave_region.csv     leave-one-state-out (zero local evidence)
    bench_learning_curve.csv   error against local sample size
    bench_summary.md           human-readable summary
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from floodvuln import evidence as EV          # noqa: E402
from floodvuln import model as M              # noqa: E402
from floodvuln import validate as V           # noqa: E402
from floodvuln.calibrate import HierarchicalVulnerability  # noqa: E402

PROC = os.path.join(HERE, "..", "data", "processed")
REP = os.path.join(HERE, "..", "reports")
DATA = os.path.join(PROC, "calibration.parquet")

EVENTS = ["Hurricane Harvey", "Superstorm Sandy", "Hurricane Katrina", "Hurricane Ike",
          "Hurricane Irma", "Hurricane Florence", "Hurricane Ida", "Hurricane Matthew",
          "Hurricane Isaac", "Hurricane Michael", "Hurricane Rita", "Hurricane Sandy"]
REGIONS = ["TX", "LA", "NJ", "NY", "FL", "NC", "SC", "MO", "IA"]


def load() -> pd.DataFrame:
    path = DATA if os.path.exists(DATA) else DATA.replace(".parquet", ".csv")
    df = pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)
    df = df[df["damage_ratio"].notna() & df["depth_m"].notna()].copy()
    df["group_key"] = df["group_key"].fillna("RES.SF.1.UNK")
    df["state"] = df["state"].fillna("XX")
    return df


def baselines(train: pd.DataFrame, test: pd.DataFrame, curves) -> list[V.Forecast]:
    d = test["depth_m"].to_numpy()
    out = []
    out.append(V.Forecast("naive_constant_mean", "deterministic",
                          np.full(len(test), train["damage_ratio"].mean())))
    jrc = EV.curve_interpolator(curves, "Residential buildings", "North AMERICA")
    out.append(V.deterministic_from_curve(jrc, d, "JRC_NA_residential_published"))
    fitted = V.fit_deterministic_curve(train["depth_m"].to_numpy(),
                                       train["damage_ratio"].to_numpy())
    out.append(V.deterministic_from_curve(fitted, d, "single_curve_fitted_on_train"))
    return out


def run_fold(train: pd.DataFrame, test: pd.DataFrame, curves, tag: str,
             allow_local: bool, taus=None) -> list[dict]:
    ta, tl = (None, None) if taus is None else taus
    hv = HierarchicalVulnerability.fit(
        train["depth_m"].to_numpy(), train["damage_ratio"].to_numpy(),
        train["group_key"].to_numpy(),
        train["state"].to_numpy() if allow_local else None,
        verbose=False, tau_arch=ta, tau_local=tl, with_theta_cov=False)

    y = test["damage_ratio"].to_numpy()
    rows = []
    for f in baselines(train, test, curves):
        r = f.score(y); r["fold"] = tag; rows.append(r)

    f = V.probabilistic_by_group(hv, test["depth_m"].to_numpy(),
                                 test["group_key"].to_numpy(), None, "global",
                                 "FloodVuln_G0_global_fit")
    r = f.score(y); r["fold"] = tag; rows.append(r)

    f = V.probabilistic_by_group(hv, test["depth_m"].to_numpy(),
                                 test["group_key"].to_numpy(), None, "archetype",
                                 "FloodVuln_G1_archetype")
    r = f.score(y); r["fold"] = tag; rows.append(r)

    if allow_local:
        f = V.probabilistic_by_group(hv, test["depth_m"].to_numpy(),
                                     test["group_key"].to_numpy(),
                                     test["state"].to_numpy(), "local",
                                     "FloodVuln_G4_local")
        r = f.score(y); r["fold"] = tag; rows.append(r)
    return rows


def main() -> None:
    os.makedirs(REP, exist_ok=True)
    curves = EV.load_curves()
    df = load()
    print(f"observations: {len(df):,}")
    print(f"groups: {df['group_key'].nunique()}   states: {df['state'].nunique()}")

    # ---------------- full fit, for the shipped model ----------------
    model_path = os.path.join(PROC, "model_global.json")
    if os.path.exists(model_path) and os.environ.get("FV_REFIT") != "1":
        hv = HierarchicalVulnerability.load(model_path)
        print(f"loaded existing full fit ({len(hv.archetypes)} archetypes, "
              f"{len(hv.locals_)} local units)")
    else:
        t0 = time.time()
        hv = HierarchicalVulnerability.fit(
            df["depth_m"].to_numpy(), df["damage_ratio"].to_numpy(),
            df["group_key"].to_numpy(), df["state"].to_numpy(), verbose=True)
        print(f"full hierarchical fit in {time.time() - t0:.1f}s")
        hv.meta["snapshot"] = EV.provenance_hash(
            os.path.join(HERE, "..", "data", "raw", "jrc_global_ddf.xlsx"))
        hv.save(model_path)
    TAUS = (hv.tau_arch, hv.tau_local)

    # ---------------- leave-one-event-out ----------------
    rows = []
    present = [e for e in EVENTS if (df["floodEvent"] == e).sum() >= 3000]
    print(f"\nhold-out events: {present}")
    for ev in present:
        te = df[df["floodEvent"] == ev]
        tr = df[df["floodEvent"] != ev]
        t1 = time.time()
        rows += run_fold(tr, te, curves, ev, allow_local=True, taus=TAUS)
        print(f"  {ev}: n_test={len(te):,}  ({time.time() - t1:.0f}s)", flush=True)
    ev_df = pd.DataFrame(rows)
    ev_df.to_csv(os.path.join(REP, "bench_hold_out_event.csv"), index=False)

    # ---------------- leave-one-region-out ----------------
    rows = []
    present_r = [s for s in REGIONS if (df["state"] == s).sum() >= 5000]
    print(f"\nhold-out regions: {present_r}")
    for st in present_r:
        te = df[df["state"] == st]
        tr = df[df["state"] != st]
        t1 = time.time()
        rows += run_fold(tr, te, curves, st, allow_local=False, taus=TAUS)
        print(f"  {st}: n_test={len(te):,}  ({time.time() - t1:.0f}s)", flush=True)
    rg_df = pd.DataFrame(rows)
    rg_df.to_csv(os.path.join(REP, "bench_leave_region.csv"), index=False)

    # ---------------- sparse-data learning curve ----------------
    target_state = max(present_r, key=lambda s: (df["state"] == s).sum())
    gk = df[df["state"] == target_state]["group_key"].value_counts().index[0]
    print(f"\nlearning curve: state={target_state} archetype={gk}")
    tr = df[df["state"] != target_state]
    hv_lc = HierarchicalVulnerability.fit(
        tr["depth_m"].to_numpy(), tr["damage_ratio"].to_numpy(),
        tr["group_key"].to_numpy(), None, verbose=False,
        tau_arch=hv.tau_arch, tau_local=hv.tau_local)
    hv_lc.tau_local = hv.tau_local

    loc = df[(df["state"] == target_state) & (df["group_key"] == gk)]
    rng = np.random.default_rng(17)
    hold = rng.permutation(len(loc))
    n_test = min(40000, len(loc) // 2)
    test_lc = loc.iloc[hold[:n_test]]
    pool_lc = loc.iloc[hold[n_test:]]
    print(f"  local pool={len(pool_lc):,}  test={len(test_lc):,}")

    lc = V.learning_curve(hv_lc, pool_lc, test_lc, gk, repeats=8)
    lc["state"] = target_state
    lc["group_key"] = gk
    lc.to_csv(os.path.join(REP, "bench_learning_curve.csv"), index=False)

    # ---------------- summary ----------------
    write_summary(df, hv, ev_df, rg_df, lc, target_state, gk)
    print("\nwrote reports/bench_summary.md")


def write_summary(df, hv, ev_df, rg_df, lc, target_state, gk) -> None:
    L = []
    a = L.append
    a("# FloodVuln calibration and validation summary\n")
    a(f"- observations: **{len(df):,}**")
    a(f"- archetype groups: **{df['group_key'].nunique()}**, "
      f"regions: **{df['state'].nunique()}**")
    a(f"- depth range used: {df['depth_m'].min():.2f} to {df['depth_m'].max():.2f} m")
    a(f"- share exactly 0 damage: {(df['damage_ratio'] <= 1e-4).mean() * 100:.1f}%, "
      f"exactly total: {(df['damage_ratio'] >= 0.9999).mean() * 100:.1f}%\n")

    def agg(d):
        g = (d.groupby("model")[["MAE", "RMSE", "bias", "CRPS", "coverage_80",
                                 "PIT_KS", "calibration_slope", "sharpness_p10_p90"]]
             .mean().sort_values("CRPS"))
        return g.round(4)

    a("## Leave-one-event-out (mean over folds)\n")
    a(agg(ev_df).to_markdown())
    a("")
    a("## Leave-one-region-out, zero local evidence in the held-out region\n")
    a(agg(rg_df).to_markdown())
    a("")

    a(f"## Sparse-data learning curve ({target_state}, {gk})\n")
    piv = (lc.groupby(["method", "n_local"])[["MAE", "CRPS", "coverage_80"]]
           .mean().reset_index())
    a(piv.pivot(index="n_local", columns="method",
                values=["MAE", "CRPS"]).round(4).to_markdown())
    a("")

    with open(os.path.join(REP, "bench_summary.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
