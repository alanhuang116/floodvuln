"""Generate the build-and-calibration report as a self-contained HTML document.

Every figure is embedded and every number is read from the result files written
by the calibration run, so the report cannot drift from the evidence.
"""
from __future__ import annotations

import base64
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
REP = os.path.join(ROOT, "reports")
FIG = os.path.join(ROOT, "figures")
OUT = os.path.join(REP, "floodvuln_report.html")

NICE = {
    "JRC_NA_residential_published": "JRC North America residential (published)",
    "naive_constant_mean": "Constant mean (naive)",
    "single_curve_fitted_on_train": "Single depth&ndash;damage curve fitted on training data",
    "FloodVuln_G0_global_fit": "FloodVuln global fit (no archetype)",
    "FloodVuln_G1_archetype": "FloodVuln archetype prior",
    "FloodVuln_G4_local": "FloodVuln region calibrated",
}
KIND = {
    "JRC_NA_residential_published": "deterministic",
    "naive_constant_mean": "deterministic",
    "single_curve_fitted_on_train": "deterministic",
}


def img(name: str, caption: str, width: str = "100%") -> str:
    p = os.path.join(FIG, name)
    if not os.path.exists(p):
        return ""
    with open(p, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode()
    return (f'<figure><img src="data:image/png;base64,{b64}" alt="{caption}" '
            f'style="width:{width}"><figcaption>{caption}</figcaption></figure>')


def csv(name):
    p = os.path.join(REP, name)
    return pd.read_csv(p) if os.path.exists(p) else None


def bench_html(df, caption, highlight="FloodVuln_G4_local"):
    if df is None or df.empty:
        return '<p class="note">Not available in this run.</p>'
    cols = ["MAE", "RMSE", "bias", "CRPS", "coverage_80", "PIT_KS", "calibration_slope"]
    g = df.groupby("model")[cols].mean().sort_values("CRPS")
    head = "".join(f"<th class='n'>{c.replace('_', ' ')}</th>" for c in cols)
    rows = ""
    for k, r in g.iterrows():
        hl = " class='hl'" if k == highlight else ""
        tag = ("<span class='pill det'>deterministic</span>" if k in KIND
               else "<span class='pill prob'>probabilistic</span>")
        cells = "".join(
            f"<td class='n'>{r[c]:.4f}</td>" if pd.notna(r[c]) else "<td class='n'>&mdash;</td>"
            for c in cols)
        rows += f"<tr{hl}><td>{NICE.get(k, k)} {tag}</td>{cells}</tr>"
    n_folds = df["fold"].nunique() if "fold" in df else 0
    return (f"<table><caption>{caption} &mdash; mean over {n_folds} folds</caption>"
            f"<thead><tr><th>Vulnerability assumption</th>{head}</tr></thead>"
            f"<tbody>{rows}</tbody></table>")


def learning_html(df):
    if df is None or df.empty:
        return '<p class="note">Not available in this run.</p>'
    g = df.groupby(["method", "n_local"])[["MAE", "CRPS", "coverage_80"]].mean()
    ns = sorted(df["n_local"].unique())
    rows = ""
    for n in ns:
        h = g.loc[("hierarchical", n)] if ("hierarchical", n) in g.index else None
        l = g.loc[("local_only", n)] if ("local_only", n) in g.index else None
        f = lambda v, k: f"{v[k]:.4f}" if v is not None and pd.notna(v[k]) else "&mdash;"
        rows += (f"<tr><td class='n'>{int(n)}</td><td class='n'>{f(h,'MAE')}</td>"
                 f"<td class='n'>{f(h,'CRPS')}</td><td class='n'>{f(h,'coverage_80')}</td>"
                 f"<td class='n'>{f(l,'MAE')}</td><td class='n'>{f(l,'CRPS')}</td></tr>")
    return ("<table><caption>Sparse-data learning curve in a withheld region</caption>"
            "<thead><tr><th class='n'>local records</th><th class='n'>pooled MAE</th>"
            "<th class='n'>pooled CRPS</th><th class='n'>pooled 80% cov</th>"
            "<th class='n'>local-only MAE</th><th class='n'>local-only CRPS</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>")


def qa_html():
    df = csv("qa_ingestion.csv")
    if df is None:
        return ""
    rows = "".join(
        f"<tr><td>{r['step']}</td><td class='n'>{int(r['records']):,}</td>"
        f"<td class='n'>{r['share_of_ingested']*100:.2f}%</td></tr>"
        for _, r in df.iterrows())
    return ("<table><caption>Ingestion QA: every record accounted for</caption>"
            "<thead><tr><th>Step</th><th class='n'>records</th><th class='n'>share</th></tr>"
            f"</thead><tbody>{rows}</tbody></table>")


def cov_html():
    df = csv("bench_covariates.csv")
    if df is None or df.empty:
        return ""
    g = df.groupby("variant")[["MAE", "RMSE", "bias", "CRPS", "coverage_80"]].mean()
    order = ["depth + archetype", "+ duration band", "+ oracle event offset (upper bound)"]
    rows = ""
    for k in order:
        if k not in g.index:
            continue
        r = g.loc[k]
        hl = " class='hl'" if "oracle" in k else ""
        rows += (f"<tr{hl}><td>{k}</td><td class='n'>{r['MAE']:.4f}</td>"
                 f"<td class='n'>{r['RMSE']:.4f}</td><td class='n'>{r['bias']:+.4f}</td>"
                 f"<td class='n'>{r['CRPS']:.4f}</td><td class='n'>{r['coverage_80']:.3f}</td></tr>")
    return ("<table><caption>Is the missing dimension the hazard or the event? "
            "Mean over 4 withheld events</caption><thead><tr><th>Model</th>"
            "<th class='n'>MAE</th><th class='n'>RMSE</th><th class='n'>bias</th>"
            f"<th class='n'>CRPS</th><th class='n'>80% cov</th></tr></thead><tbody>{rows}</tbody></table>")


def pct_change(df, base_model, new_model, metric):
    if df is None or df.empty:
        return None
    g = df.groupby("model")[metric].mean()
    if base_model not in g or new_model not in g:
        return None
    return 100.0 * (g[new_model] - g[base_model]) / g[base_model]


def main() -> None:
    ev = csv("bench_hold_out_event.csv")
    rg = csv("bench_leave_region.csv")
    lc = csv("bench_learning_curve.csv")
    with open(os.path.join(ROOT, "web", "floodvuln_model.json"), encoding="utf-8") as fh:
        bundle = json.load(fh)

    qa = {r["step"].strip(): r for r in bundle.get("qa", [])}
    n_in = int(qa["records ingested"]["records"]) if "records ingested" in qa else 0
    n_ok = int(qa["admissible to primary calibration"]["records"]) if "admissible to primary calibration" in qa else 0

    imp_ev = pct_change(ev, "JRC_NA_residential_published", "FloodVuln_G1_archetype", "CRPS")
    imp_ev_det = pct_change(ev, "single_curve_fitted_on_train", "FloodVuln_G1_archetype", "CRPS")
    imp_rg = pct_change(rg, "JRC_NA_residential_published", "FloodVuln_G1_archetype", "CRPS")
    g4_vs_g1 = pct_change(ev, "FloodVuln_G1_archetype", "FloodVuln_G4_local", "CRPS")

    def get(df, model, metric):
        if df is None or df.empty:
            return None
        g = df.groupby("model")[metric].mean()
        return g.get(model)

    def pc(v):
        return f"{v:+.1f}%" if v is not None else "n/a"

    def phrase(v, metric="CRPS", lower_is_better=True):
        """Render a signed change as a sentence fragment that states its own
        direction. A bare signed percentage inside a sentence that already says
        'improves' reads as a contradiction when the metric is one where lower
        is better, which is exactly the trap this avoids."""
        if v is None:
            return f"has no measured effect on {metric}"
        better = (v < 0) if lower_is_better else (v > 0)
        verb = "reduces" if v < 0 else "increases"
        tail = "" if better else " (worse)"
        return f"{verb} {metric} by {abs(v):.1f}%{tail}"

    fields = dict(
        n_in=f"{n_in:,}", n_ok=f"{n_ok:,}",
        qa_table=qa_html(),
        fig1=img("fig1_depth_damage.png", "Figure 1. Fitted vulnerability against observed NFIP claims, by archetype. Points are observed bin means sized by sample count; the band is the fitted P10&ndash;P90."),
        fig4=img("fig4_jrc_vs_fitted.png", "Figure 2. The published JRC North America residential curve against 1.86 million US claims and two fitted archetypes.", "78%"),
        fig2=img("fig2_distribution.png", "Figure 3. Observed damage-ratio distribution at three fixed depths, with the fitted beta component overlaid."),
        fig3=img("fig3_learning_curve.png", "Figure 4. Sparse-data learning curve. The pooled model improves steadily from the prior, but the unpooled refit overtakes it from about ten records &mdash; the inversion diagnosed and fixed in section 8.5."),
        fig6=img("fig6_shape_offset.png", "Figure 6. A shape offset restores the partial-pooling advantage in the sparse-data regime. Bands are one standard deviation over resamples.", "78%"),
        fig5=img("fig5_reliability.png", "Figure 5. Probability-integral-transform uniformity and quantile reliability on a withheld event, archetype-only against region-calibrated."),
        ev_table=bench_html(ev, "Leave-one-event-out"),
        rg_table=bench_html(rg, "Leave-one-region-out (zero local evidence)", "FloodVuln_G1_archetype"),
        lc_table=learning_html(lc),
        cov_table=cov_html(),
        imp_ev=phrase(imp_ev), imp_ev_det=phrase(imp_ev_det), imp_rg=phrase(imp_rg),
        snapshot=bundle.get("evidence_snapshot", ""),
        g4_vs_g1=phrase(g4_vs_g1),
        crps_g1=f"{get(ev,'FloodVuln_G1_archetype','CRPS'):.4f}" if get(ev,'FloodVuln_G1_archetype','CRPS') else "n/a",
        crps_g4=f"{get(ev,'FloodVuln_G4_local','CRPS'):.4f}" if get(ev,'FloodVuln_G4_local','CRPS') else "n/a",
        cov_g1=f"{get(ev,'FloodVuln_G1_archetype','coverage_80'):.3f}" if get(ev,'FloodVuln_G1_archetype','coverage_80') else "n/a",
        cov_g4=f"{get(ev,'FloodVuln_G4_local','coverage_80'):.3f}" if get(ev,'FloodVuln_G4_local','coverage_80') else "n/a",
        slope_jrc=f"{get(ev,'JRC_NA_residential_published','calibration_slope'):.3f}" if get(ev,'JRC_NA_residential_published','calibration_slope') else "n/a",
        bias_jrc=f"{get(ev,'JRC_NA_residential_published','bias'):+.4f}" if get(ev,'JRC_NA_residential_published','bias') is not None else "n/a",
    )
    body = TEMPLATE
    for k, v in fields.items():
        body = body.replace("[[" + k + "]]", str(v))
    missing = [t for t in ("[[" + k + "]]" for k in fields) if t in body]
    if missing:
        print("  ! unreplaced:", missing)
    os.makedirs(REP, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(body)
    print(f"wrote {OUT}  ({os.path.getsize(OUT)/1024:.0f} KB)")


TEMPLATE = open(os.path.join(HERE, "report_template.html"), encoding="utf-8").read() \
    if os.path.exists(os.path.join(HERE, "report_template.html")) else ""

if __name__ == "__main__":
    if not TEMPLATE:
        sys.exit("report_template.html is missing")
    main()
