"""Export the fitted engine and its validation record into a web bundle.

The website ships with illustrative coefficients. This replaces them with the
parameters actually fitted to 1.86 million NFIP claims, plus the published JRC
curve used as the G0 prior and the measured benchmark results, so every number
the page displays is traceable to a run in this repository.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from floodvuln import evidence as EV            # noqa: E402
from floodvuln import model as M                # noqa: E402
from floodvuln.calibrate import HierarchicalVulnerability  # noqa: E402
from floodvuln.predict import load_offset_cov                # noqa: E402

PROC = os.path.join(HERE, "..", "data", "processed")
REP = os.path.join(HERE, "..", "reports")
WEB = os.path.join(HERE, "..", "web")

# Archetypes surfaced in the interactive console, chosen for evidence volume
# and for spanning the configurations that actually separate the curves.
FEATURED = [
    ("RES.SF.1.SLAB", "Single-family, 1 storey, slab"),
    ("RES.SF.1.CRAWL", "Single-family, 1 storey, crawlspace"),
    ("RES.SF.2.SLAB", "Single-family, 2 storey, slab"),
    ("RES.SF.2.BASEMENT", "Single-family, 2 storey, basement"),
    ("RES.SF.1.ELEV_ENCL", "Single-family, elevated w/ enclosure"),
    ("RES.SF.MH.UNK", "Manufactured home"),
    ("RES.MF2_4.2.UNK", "Small multifamily, 2 storey"),
    ("COM.MIXED.1.UNK", "Commercial, 1 storey"),
]

FEATURED_STATES = ["TX", "LA", "FL", "NJ", "NY", "NC", "MO", "PA", "SC", "VA"]


def load_calibration_counts() -> pd.DataFrame:
    path = os.path.join(PROC, "calibration.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, usecols=["group_key", "state", "depth_m", "damage_ratio"],
                       low_memory=False)


def empirical_curve(df: pd.DataFrame, group_key: str) -> list[dict]:
    """Binned observed means, so the page can show data behind the curve."""
    s = df[df.group_key == group_key]
    if len(s) < 500:
        return []
    edges = np.array([-2, -0.6, -0.15, 0.01, 0.3, 0.6, 0.95, 1.4, 2.0, 2.8, 4.0, 8.0])
    idx = np.clip(np.searchsorted(edges, s.depth_m, side="right") - 1, 0, len(edges) - 2)
    out = []
    for b in range(len(edges) - 1):
        m = idx == b
        if m.sum() < 40:
            continue
        v = s.damage_ratio[m]
        out.append({"d": round(float(s.depth_m[m].mean()), 3),
                    "n": int(m.sum()),
                    "mean": round(float(v.mean()), 4),
                    "p10": round(float(v.quantile(0.10)), 4),
                    "p90": round(float(v.quantile(0.90)), 4)})
    return out


def main() -> None:
    os.makedirs(WEB, exist_ok=True)
    hv = HierarchicalVulnerability.load(os.path.join(PROC, "model_global.json"))
    ocov = load_offset_cov(os.path.join(PROC, "offset_cov.npz"))
    curves = EV.load_curves()
    df = load_calibration_counts()
    tau_l2 = np.diag(np.asarray(hv.tau_local, float) ** 2)

    def cov_of(kind, key, fallback):
        c = ocov.get((kind, key))
        return (c if c is not None else fallback)

    bundle: dict = {
        "model_version": "1.0.0",
        "knots": M.KNOTS.tolist(),
        "width": M.WIDTH,
        "theta": [round(float(v), 6) for v in hv.theta],
        "tau_arch": [round(float(v), 4) for v in hv.tau_arch],
        "tau_local": [round(float(v), 4) for v in hv.tau_local],
        "conf_scale": 0.055,
        "meta": hv.meta,
    }

    # --- archetypes ---
    arche = []
    for key, label in FEATURED:
        if key not in hv.archetypes:
            continue
        lv = hv.archetypes[key]
        # An unseen region inherits the between-region prior variance on top of
        # the archetype's own posterior: that is what G1 honestly knows.
        ac = cov_of("arch", key, np.diag(np.asarray(hv.tau_arch, float) ** 2))
        arche.append({
            "key": key, "label": label,
            "offsets": [round(float(v), 5) for v in lv.offsets],
            "cov": [[round(float(x), 8) for x in row] for row in ac],
            "cov_unseen": [[round(float(x), 8) for x in row] for row in (ac + tau_l2)],
            "n": int(lv.n_obs),
            "empirical": empirical_curve(df, key) if len(df) else [],
        })
    bundle["archetypes"] = arche

    # --- local (state) offsets for the featured archetypes ---
    loc = {}
    for a in arche:
        for st in FEATURED_STATES:
            k = f"{a['key']}@{st}"
            if k in hv.locals_:
                lv = hv.locals_[k]
                c = cov_of("local", k, tau_l2)
                loc[k] = {"offsets": [round(float(v), 5) for v in lv.offsets],
                          "cov": [[round(float(x), 8) for x in row] for row in c],
                          "n": int(lv.n_obs)}
    bundle["locals"] = loc

    # --- JRC published prior for G0 ---
    jrc = {}
    for cls in curves.damage_class.unique():
        sel = curves[curves.damage_class == cls]
        jrc[cls] = {c: sorted(zip(g.depth_m.tolist(), g.damage_factor.tolist()))
                    for c, g in sel.groupby("continent")}
    bundle["jrc"] = jrc

    # --- validation record ---
    val = {}
    for name, fn in [("event", "bench_hold_out_event.csv"),
                     ("region", "bench_leave_region.csv")]:
        p = os.path.join(REP, fn)
        if not os.path.exists(p):
            continue
        d = pd.read_csv(p)
        agg = (d.groupby("model")[["MAE", "RMSE", "bias", "CRPS", "coverage_80",
                                   "PIT_KS", "calibration_slope"]]
               .mean().reset_index().sort_values("CRPS"))
        val[name] = json.loads(agg.round(4).to_json(orient="records"))
        val[name + "_folds"] = sorted(d["fold"].unique().tolist())
    lc_path = os.path.join(REP, "bench_learning_curve.csv")
    if os.path.exists(lc_path):
        lc = pd.read_csv(lc_path)
        agg = (lc.groupby(["method", "n_local"])[["MAE", "CRPS", "coverage_80"]]
               .mean().reset_index())
        val["learning_curve"] = json.loads(agg.round(4).to_json(orient="records"))
    bundle["validation"] = val

    # --- ingestion QA ---
    qa_path = os.path.join(REP, "qa_ingestion.csv")
    if os.path.exists(qa_path):
        bundle["qa"] = json.loads(pd.read_csv(qa_path).to_json(orient="records"))

    bundle["evidence_snapshot"] = EV.provenance_hash(
        os.path.join(HERE, "..", "data", "raw", "jrc_global_ddf.xlsx"))
    bundle["sources"] = json.loads(EV.registry_frame().to_json(orient="records"))

    out = os.path.join(WEB, "floodvuln_model.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, separators=(",", ":"))
    size = os.path.getsize(out) / 1024
    print(f"wrote {out}  ({size:.0f} KB)")
    print(f"  archetypes: {len(arche)}  locals: {len(loc)}  "
          f"validation blocks: {list(val)}")


if __name__ == "__main__":
    main()
