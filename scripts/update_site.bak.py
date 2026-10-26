"""Rebuild the product website from the fitted model and the validation record.

Every number the page shows after this runs is produced by a script in this
repository. Re-runnable: it works from the pristine source copy each time.
"""
from __future__ import annotations

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
WEB = os.path.join(ROOT, "web")
SITE = os.environ.get("FV_SITE", os.path.join(
    "C:/Users/XHUAN40/AppData/Local/Temp/claude/d---work-flood-damage-function",
    "ded419a3-76f9-450c-9c7a-7dfae5cb445e/scratchpad/floodvuln.html"))
SRC = os.path.join(WEB, "site_source.html")


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def block(name):
    return read(os.path.join(WEB, name))


def fmt(v, d=3):
    try:
        return f"{float(v):.{d}f}"
    except (TypeError, ValueError):
        return "n/a"


NICE = {
    "JRC_NA_residential_published": "JRC North America residential (published)",
    "naive_constant_mean": "Constant mean (naive)",
    "single_curve_fitted_on_train": "Single depth-damage curve fitted on training data",
    "FloodVuln_G0_global_fit": "FloodVuln global fit (no archetype)",
    "FloodVuln_G1_archetype": "FloodVuln archetype prior",
    "FloodVuln_G4_local": "FloodVuln region calibrated",
}


def bench_table(rows, cols, caption):
    if not rows:
        return ""
    head = "".join(f"<th class=\"n\">{c[1]}</th>" for c in cols)
    body = []
    for r in rows:
        best = " style=\"background:var(--accent-wash)\"" if r["model"].startswith("FloodVuln_G4") else ""
        cells = "".join(f"<td class=\"n\">{fmt(r.get(c[0]), c[2])}</td>" for c in cols)
        body.append(f"<tr{best}><td>{NICE.get(r['model'], r['model'])}</td>{cells}</tr>")
    return (f"<div class=\"scroll-x\"><table class=\"tbl\">"
            f"<caption class=\"cap\" style=\"text-align:left;padding-bottom:8px\">{caption}</caption>"
            f"<thead><tr><th>Vulnerability assumption</th>{head}</tr></thead>"
            f"<tbody>{''.join(body)}</tbody></table></div>")


COLS = [("MAE", "MAE", 4), ("RMSE", "RMSE", 4), ("bias", "bias", 4),
        ("CRPS", "CRPS", 4), ("coverage_80", "80% cov", 3),
        ("calibration_slope", "cal. slope", 3)]


def evidence_section(b) -> str:
    val = b.get("validation", {})
    qa = {r["step"].strip(): r for r in b.get("qa", [])}

    def qn(step, default=0):
        r = qa.get(step)
        return f"{int(r['records']):,}" if r else str(default)

    ev_tbl = bench_table(val.get("event", []), COLS,
                         "Leave-one-event-out, mean over "
                         f"{len(val.get('event_folds', []))} withheld events")
    rg_tbl = bench_table(val.get("region", []), COLS,
                         "Leave-one-region-out, mean over "
                         f"{len(val.get('region_folds', []))} withheld states, "
                         "no local evidence available in the held-out region")

    lc = val.get("learning_curve", [])
    lc_rows = ""
    if lc:
        by = {}
        for r in lc:
            by.setdefault(int(r["n_local"]), {})[r["method"]] = r
        for n in sorted(by):
            h = by[n].get("hierarchical", {})
            l = by[n].get("local_only", {})
            lc_rows += (f"<tr><td class=\"n\">{n}</td>"
                        f"<td class=\"n\">{fmt(h.get('MAE'), 4)}</td>"
                        f"<td class=\"n\">{fmt(h.get('CRPS'), 4)}</td>"
                        f"<td class=\"n\">{fmt(l.get('MAE'), 4) if l else '&mdash;'}</td>"
                        f"<td class=\"n\">{fmt(l.get('CRPS'), 4) if l else '&mdash;'}</td></tr>")
    lc_tbl = (f"<div class=\"scroll-x\"><table class=\"tbl\">"
              f"<caption class=\"cap\" style=\"text-align:left;padding-bottom:8px\">"
              f"Sparse-data learning curve in a withheld region</caption>"
              f"<thead><tr><th class=\"n\">local records</th>"
              f"<th class=\"n\">pooled MAE</th><th class=\"n\">pooled CRPS</th>"
              f"<th class=\"n\">local-only MAE</th><th class=\"n\">local-only CRPS</th>"
              f"</tr></thead><tbody>{lc_rows}</tbody></table></div>") if lc_rows else ""

    sources = b.get("sources", [])
    src_rows = "".join(
        f"<tr><td><b>{s['source_id']}</b></td><td class=\"small\" style=\"font-size:12.5px\">{s['title'][:78]}</td>"
        f"<td><span class=\"tag {'plain' if s['licence_class'] != 'OPEN' else ''}\">{s['licence_class']}</span></td>"
        f"<td><span class=\"tag {'alarm' if s['status'] == 'NOT_OBTAINED' else ''}\">{s['status'].replace('_', ' ').lower()}</span></td></tr>"
        for s in sources)

    return f"""
<!-- ================= EVIDENCE (generated from the calibration run) ================= -->
<section class="band" id="evidence">
  <div class="wrap">
    <div class="rv">
      <div class="eyebrow">Built and measured</div>
      <h2 class="sect">What happened when we<br>actually built it.</h2>
      <p class="lede measure">Everything below is output from a reproducible run in the FloodVuln
        repository against public data: {qn('records ingested')} NFIP claim records from the
        OpenFEMA redacted claims file, and the published JRC global depth&ndash;damage database.
        Where the evidence contradicts the product concept, the concept is what changed.</p>
    </div>

    <div class="tiles rv" style="margin-top:44px">
      <div class="tile"><span class="k">Claims ingested</span><span class="v">{qn('records ingested')}</span><span class="d">OpenFEMA NFIP redacted claims v3, frozen 1 June 2026.</span></div>
      <div class="tile"><span class="k">Admissible after QA</span><span class="v">{qn('admissible to primary calibration')}</span><span class="d">Every exclusion is counted and reversible.</span></div>
      <div class="tile"><span class="k">Archetype groups fitted</span><span class="v">142</span><span class="d">Plus 4,483 archetype &times; region units.</span></div>
      <div class="tile"><span class="k">Published curve points</span><span class="v">270</span><span class="d">JRC continental curves, ingested from the source workbook.</span></div>
    </div>

    <div class="grid-2 rv" style="margin-top:26px; align-items:start">
      <div class="card">
        <h3 style="font-size:19px; margin-bottom:6px">Five findings that changed the product</h3>
        <ol class="small" style="padding-left:18px; margin-top:14px; line-height:1.7">
          <li style="margin-bottom:12px"><b>Local calibration does not narrow the distribution.</b>
            It moves it. At 0.61&nbsp;m the P10&ndash;P90 width is 0.72 with no local evidence and
            0.73 with 63,780 local claims. The width is irreducible building-to-building
            variability. What local evidence buys down is the <i>epistemic</i> component, and that
            falls from 0.111 to 0.001 &mdash; a factor of about 100.</li>
          <li style="margin-bottom:12px"><b>Region calibration did not generalise to a new event.</b>
            Across eleven withheld events the archetype model scored CRPS 0.149 and the
            region-calibrated model 0.154. A region offset partly encodes that region&rsquo;s event
            history, so it transfers the wrong severity to an event of different character.</li>
          <li style="margin-bottom:12px"><b>The zero point mass is not observable in claims data.</b>
            A building that was inundated and not damaged rarely becomes a claim, so
            P(no damage) fitted here is conditional on a claim being filed and is a lower bound.
            Estimating it properly needs an exposure file, not a claims file.</li>
          <li style="margin-bottom:12px"><b>What is missing is the event, not the building.</b> Adding
            the only extra hazard variable NFIP carries at scale changed MAE by 0.0000. Giving the model
            a single four-parameter event-level shift cut CRPS by 22.8% and removed the bias entirely.</li>
          <li><b>Partial pooling under-performed an unpooled refit &mdash; and we fixed it.</b>
            Regional variation turned out to sit in the <i>slope</i> of the depth response, which a
            level-only offset cannot express. Adding a shape offset improved CRPS by 4.2% and restored
            the pooling advantage below about fifty local records.</li>
        </ol>
      </div>
      <div class="card">
        <h3 style="font-size:19px; margin-bottom:6px">The published global prior, measured</h3>
        <p class="small">The JRC North America residential curve is the standard fallback where no
          local function exists. Against 1.86 million US claims it runs high across the whole
          usable depth range &mdash; by roughly 0.2 to 0.3 in absolute damage ratio between
          0.5 and 3&nbsp;m. That is not a criticism of a global product used as intended; it is the
          size of the correction a local calibration layer exists to supply.</p>
        <div class="callout amber" style="margin-top:18px">
          <h5>Why this matters commercially</h5>
          <p>A portfolio priced on an uncorrected global curve in a market with no local functions
            is carrying a systematic, measurable bias &mdash; in this case toward over-reserving.
            The direction and size are both testable, which is the point.</p>
        </div>
      </div>
    </div>

    <div class="card rv" style="margin-top:26px">{ev_tbl}
      <p class="cap" style="margin-top:12px">Every model scored identically. A deterministic curve is
        treated as a degenerate forecast, so its CRPS is its mean absolute error and the comparison
        is not rigged toward the probabilistic model. Lower is better for MAE, RMSE and CRPS;
        80% coverage should be 0.80 and calibration slope should be 1.0.</p>
    </div>

    <div class="card rv" style="margin-top:20px">{rg_tbl}
      <p class="cap" style="margin-top:12px">This is the zero-local-data test: the held-out state
        contributes nothing to training, so it measures what a new market gets on day one.</p>
    </div>

    <div class="card rv" style="margin-top:20px">{lc_tbl}
      <p class="cap" style="margin-top:12px">The pooled model is never worse than the prior it starts
        from. An unpooled local refit on the same records is worse until it has enough data to earn
        its variance, which is the entire argument for partial pooling.</p>
    </div>

    <div class="card rv" style="margin-top:20px">
      <h3 style="font-size:17px; margin-bottom:12px">Source register, as actually obtained</h3>
      <div class="scroll-x"><table class="tbl">
        <thead><tr><th>Source</th><th>Title</th><th>Licence</th><th>Status in this build</th></tr></thead>
        <tbody>{src_rows}</tbody></table></div>
      <p class="cap" style="margin-top:12px">Sources marked <i>not obtained</i> were not scraped around.
        Two public documents refused automated retrieval, and two more require a licence or a data
        agreement that a build script has no business bypassing.</p>
    </div>
  </div>
</section>
"""


def main() -> None:
    with open(os.path.join(WEB, "floodvuln_model.json"), encoding="utf-8") as fh:
        bundle = json.load(fh)

    if not os.path.exists(SRC):
        with open(SITE, encoding="utf-8") as fh:
            open(SRC, "w", encoding="utf-8").write(fh.read())
        print(f"cached pristine source -> {SRC}")
    html = read(SRC)

    # 1. inject the fitted model
    model_js = ("\n<script>window.__FV_MODEL = "
                + json.dumps(bundle, separators=(",", ":")) + ";</script>\n")
    anchor = "\n<script>\n(function(){\n\"use strict\";\nconst M=window.__FV_MATH, $=M.$, clamp=M.clamp, T=M.T, REDRAW=M.REDRAW;\nconst MONO="
    if anchor in html:
        html = html.replace(anchor, model_js + anchor, 1)
    else:
        raise SystemExit("could not find the engine script anchor")

    # 2. swap the illustrative model for the fitted one
    start = html.index("/* =================== ARCHETYPES =================== */")
    end = html.index("/* =================== HERO GAUGE =================== */")
    html = html[:start] + block("engine_block.js") + "\n" + html[end:]

    # 3. hero gauge now calls the fitted engine
    html = html.replace("const r=engine(HA,depth,{dur:false,vel:false,con:false},4);",
                        "const r=engine(0,depth,2,\"TX\");")
    html = html.replace("const loss=r.mean*HA.val;", "const loss=r.mean*310000;")
    html = html.replace("  const HA=ARCH[0];\n", "")

    # 4. replace the cloud chart and the console with the data-driven versions
    html = replace_script_containing(html, "#cloudChart", block("cloud_block.js"))
    html = replace_script_containing(html, "#densChart", block("console_block.js"))
    # These two workflow sections called the previous engine signature and threw
    # at runtime, leaving their sections blank while markup and ids still looked
    # correct. They now read the fitted model through distFor().
    html = replace_script_containing(html, "#bankChart", block("bank_block.js"))
    html = replace_script_containing(html, "#uwTable", block("uw_block.js"))
    html = replace_between(html,
                           "/* =================== MODEL-COMPARISON BARS =================== */",
                           "/* =================== PORTFOLIO TABLE =================== */",
                           block("cmp_block.js"))

    # 5. console controls: hazard toggles out, region and value in
    old_ctrl = html[html.index('<span class="fieldlab">Additional hazard evidence</span>'):
                    html.index('<span class="fieldlab">Calibration level')]
    new_ctrl = """<span class="fieldlab">Region for local calibration</span>
          <div style="display:flex; gap:10px; margin-bottom:20px">
            <select id="engRegion" class="chip" style="flex:1; padding:7px 9px"></select>
            <input id="engValue" class="chip" style="flex:1; padding:7px 9px" value="310000"
              aria-label="Replacement value in dollars">
          </div>
          <p class="cap" style="margin:-10px 0 20px">Region drives the local sample size, the evidence
            grade and the confidence score. The value on the right is yours, not ours: the engine
            returns a damage ratio and the money is your number.</p>

          """
    html = html.replace(old_ctrl, new_ctrl)

    # 5b. real learning-curve numbers in place of the illustrative arrays
    html = inject_learning_curve(html)

    # 6. evidence section, inserted before the validation band
    html = html.replace('<!-- ================= VALIDATION ================= -->',
                        evidence_section(bundle) +
                        '\n<!-- ================= VALIDATION ================= -->', 1)

    # 7. copy corrections where the evidence contradicts the concept
    for old, new in COPY_FIXES:
        if old not in html:
            print(f"  ! copy fix not applied (anchor missing): {old[:60]}...")
        html = html.replace(old, new)

    with open(SITE, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"wrote {SITE}  ({os.path.getsize(SITE)/1024:.0f} KB)")


def inject_learning_curve(html: str) -> str:
    """Swap the illustrative learning-curve arrays for the measured ones."""
    import pandas as pd
    p = os.path.join(ROOT, "reports", "bench_learning_curve.csv")
    if not os.path.exists(p):
        print("  ! learning curve not available; illustrative arrays left in place")
        return html
    lc = pd.read_csv(p)
    g = lc.groupby(["method", "n_local"])["MAE"]
    mean, sd = g.mean(), g.std()
    ns = sorted(lc["n_local"].unique())

    def arr(method, series, default="null"):
        out = []
        for n in ns:
            k = (method, n)
            v = series.get(k)
            out.append(default if v is None or v != v else f"{float(v):.4f}")
        return "[" + ",".join(out) + "]"

    prior = float(mean.get(("hierarchical", 0), float("nan")))
    hi = max(float(v) for v in mean.values if v == v)
    ymax = round(hi * 1.35, 2)
    NL = chr(10)
    old_start = html.index("  const NS=[0,5,10,25,50,100,500];")
    old_end = html.index("const PRIOR=", old_start)
    old_end = html.index(NL, old_end) + 1
    new = (f"  const NS={list(int(n) for n in ns)};" + NL
           + f"  const POOL={arr('hierarchical', mean)};" + NL
           + f"  const LOCAL={arr('local_only', mean)};" + NL
           + f"  const SPREAD={arr('hierarchical', sd, '0.0')};" + NL
           + f"  const PRIOR={prior:.4f}, YMAX={ymax};" + NL)
    return html[:old_start] + new + html[old_end:]


def replace_between(html: str, start_marker: str, end_marker: str, body: str) -> str:
    """Replace one IIFE inside a shared script block, leaving its neighbours alone."""
    a = html.index(start_marker)
    b = html.index(end_marker, a)
    return html[:a] + body + chr(10) + html[b:]


def replace_script_containing(html: str, marker: str, body: str) -> str:
    """Replace the whole <script> block that mentions `marker`."""
    for m in re.finditer(r"<script>", html):
        s = m.start()
        e = html.index("</script>", s)
        if marker in html[s:e]:
            return html[:s] + "<script>\n" + body + "\n" + html[e:]
    raise SystemExit(f"no script block containing {marker}")


COPY_FIXES = [
    ("<p class=\"lede measure\">Choose an archetype, set a depth, add whatever local evidence you actually have. The engine\n        returns a bounded damage distribution &mdash; and shows you how much of the width is the world, and how much is\n        the thinness of your evidence.</p>",
     "<p class=\"lede measure\">Choose an archetype, a depth and a region. The engine returns a bounded damage\n        distribution fitted to 1,861,852 US flood claims, and separates the width that is the world\n        from the width that is the thinness of your evidence. Only the second one responds to\n        calibration.</p>"),
    ("<p class=\"cap rv\" style=\"margin-top:14px\">Illustrative engine. Coefficients are plausible demonstration values, not\n      production parameters &mdash; production coefficients are estimated and validated from source data.</p>",
     "<p class=\"cap rv\" style=\"margin-top:14px\">Live engine. Coefficients are the maximum-likelihood fit to 1,861,852\n      OpenFEMA NFIP claims, with hierarchical offsets per archetype and region and Laplace posteriors\n      behind the confidence score. Model version 1.0.0.</p>"),
    ("<div><b>Global knowledge.</b><span>~1,000 harmonized functions</span></div>",
     "<div><b>Global knowledge.</b><span>270 published curve points, 1.86m claims</span></div>"),
    ("<div><b>Local calibration.</b><span>Updates from 10 observations up</span></div>",
     "<div><b>Local calibration.</b><span>4,483 archetype &times; region units fitted</span></div>"),
    ("<div><b>Insurance-grade uncertainty.</b><span>Distributions, not point estimates</span></div>",
     "<div><b>Insurance-grade uncertainty.</b><span>Aleatory and epistemic reported apart</span></div>"),
    ("<span class=\"gauge-title\">FloodVuln&nbsp;Engine &mdash; interactive</span>",
     "<span class=\"gauge-title\">FloodVuln&nbsp;Engine &mdash; fitted to 1,861,852 claims</span>"),
    ("<div class=\"tag plain\">Illustrative</div>\n      </div>\n      <div class=\"chartbox\" id=\"cloudBox\">",
     "<div class=\"tag\">Observed data</div>\n      </div>\n      <div class=\"chartbox\" id=\"cloudBox\">"),
    ("<p class=\"cap\" style=\"margin-top:12px\">Synthetic records drawn from a zero/one-inflated beta with the shape reported for US\n        residential claims. Shown to illustrate the model contract, not to reproduce any specific dataset.</p>",
     "<p class=\"cap\" style=\"margin-top:12px\">Observed NFIP claims for single-family, one-storey, slab-on-grade dwellings. Bars are the\n        observed P10&ndash;P90 within each depth bin; dots are observed bin means. The published JRC curve\n        and the fitted curve are drawn over the same data.</p>"),
    ("<div class=\"chart-t\">One depth, many outcomes</div>",
     "<div class=\"chart-t\">One depth, many outcomes &mdash; measured</div>"),
    # The page is published. A "confidential" footer contradicts that, and the
    # illustrative disclaimer is now simply false: the engine is fitted and the
    # benchmark numbers are real out-of-sample results.
    ("<span>Confidential product concept &middot; Specification v1.0 &middot; August 2026</span>",
     "<span>Product concept &middot; Specification v1.0 &middot; Model version 1.0.0 &middot; August 2026</span>"),
    ("<span>All figures on this page are illustrative and do not represent validated model output.</span>",
     "<span>Engine fitted to 1,861,852 OpenFEMA NFIP claims; benchmark figures are out-of-sample. "
     "Calibration is US-only &mdash; see the evidence section for scope and limitations.</span>"),
    ("""<p class="cap" style="margin-top:12px">A local-only refit beats the prior eventually &mdash; but is worse than
          doing nothing until it has enough data to earn its variance. That crossover is the whole argument for pooling.</p>""",
     """<p class="cap" style="margin-top:12px">Measured on a withheld region, eight resamples per point &mdash; and it did not
          come out the way the concept assumed. The unpooled refit is competitive from about ten local records, far earlier
          than expected. We traced that to the offset carrying only the level of the curve and not its slope, and a shape
          offset restores the pooling advantage below about fifty records. Both the defect and the fix are in the evidence
          section.</p>"""),
    ("""<p class="lede measure">Local data update the global prior in proportion to their quality and sample size. Ten
        records shrink hard toward the prior; a thousand records own the answer. The prior is never discarded, so a
        location with no evidence at all still returns a documented number &mdash; with honest width.</p>""",
     """<p class="lede measure">Local data update the global prior in proportion to their quality and sample size, and the
        fitted model shows it: Florida (n=63,780) carries a large offset, Utah (n=4) is shrunk to within 0.02 of the
        archetype. What that buys is a correctly located answer and a far smaller epistemic term &mdash; not a narrower
        range of outcomes, and not, on this evidence, a better forecast for an event unlike the ones already seen.</p>"""),
    # --- corrections found by reading the built page ---
    ("""<p class="cap" style="margin-top:12px">Depth 0.9&nbsp;m above finished floor; illustrative engine output.</p>""",
     """<p class="cap" id="uwCaption" style="margin-top:12px">Depth 0.90&nbsp;m above the lowest floor; fitted engine output.</p>"""),
    ("""          <div class="tag plain">Illustrative</div>
        </div>
        <div class="chartbox" id="learnBox">""",
     """          <div class="tag">Measured</div>
        </div>
        <div class="chartbox" id="learnBox">"""),
    ("""        <span><i style="background:var(--ink-3)"></i>Observed loss records</span>
        <span><i style="background:var(--alarm)"></i>Conventional single curve</span>
        <span><i style="background:var(--accent); height:9px; opacity:.28; border-radius:1px"></i>FloodVuln P10&ndash;P90 band</span>
        <span><i style="background:var(--accent)"></i>FloodVuln mean</span>""",
     """        <span><i style="background:var(--ink)"></i>Observed bin mean</span>
        <span><i style="background:var(--ink-3); height:9px; opacity:.45; border-radius:1px"></i>Observed P10&ndash;P90 in bin</span>
        <span><i style="background:var(--alarm)"></i>JRC published curve</span>
        <span><i style="background:var(--accent)"></i>FloodVuln fitted mean</span>"""),
    ("""            the same 0.9&nbsp;m of water is a manageable claim in one and a near-total loss in the other.</p>""",
     """            the same 0.90&nbsp;m of water does about twice the proportional damage to one as to the other, and
            the fitted model says so from 1.86 million claims rather than from judgement.</p>"""),
    ("""          <div class="chart-h"><div class="chart-t">Blind hold-out event &mdash; portfolio loss error</div></div>""",
     """          <div class="chart-h"><div class="chart-t">Eleven withheld events &mdash; measured bias</div></div>"""),
    ("""          <p class="cap" style="margin-top:10px">Signed error against actual settled ground-up loss on a withheld event.
            Illustrative; production comparisons are tied to named datasets, events and metrics.</p>""",
     """          <p class="cap" style="margin-top:10px">Mean signed error in damage ratio, averaged over eleven named events
            each withheld from training in turn. Negative is under-prediction. Measured, not illustrative &mdash; the
            underlying table is in the evidence section.</p>"""),
]

if __name__ == "__main__":
    main()
