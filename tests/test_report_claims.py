"""Verify the numbers asserted in the report and the website against source data.

Prose drifts from evidence. This checks the specific figures quoted in the
narrative against the files that produced them, so a wrong number in a sentence
fails loudly instead of being published.
"""
from __future__ import annotations

import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)

REPORT = os.path.join(ROOT, "reports", "floodvuln_report.html")
SITE = os.environ.get("FV_SITE", os.path.join(
    "C:/Users/XHUAN40/AppData/Local/Temp/claude/d---work-flood-damage-function",
    "ded419a3-76f9-450c-9c7a-7dfae5cb445e/scratchpad/floodvuln.html"))

FAILS: list[str] = []
WARNS: list[str] = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"   [{detail}]" if not ok else ""))
    if not ok:
        FAILS.append(f"{name}: {detail}")


def warn(name, detail):
    print(f"WARN  {name}   [{detail}]")
    WARNS.append(f"{name}: {detail}")


def contains(text, needle, name):
    check(name, needle in text, f"missing: {needle[:70]}")


def main():
    report = open(REPORT, encoding="utf-8").read()
    site = open(SITE, encoding="utf-8").read()
    qa = pd.read_csv(os.path.join(ROOT, "reports", "qa_ingestion.csv"))
    qam = {r["step"].strip(): r for _, r in qa.iterrows()}
    ev = pd.read_csv(os.path.join(ROOT, "reports", "bench_hold_out_event.csv"))
    rg = pd.read_csv(os.path.join(ROOT, "reports", "bench_leave_region.csv"))
    ge = ev.groupby("model")[["MAE", "CRPS", "coverage_80", "bias", "calibration_slope"]].mean()
    gr = rg.groupby("model")[["MAE", "CRPS", "coverage_80", "bias", "calibration_slope"]].mean()

    print("=== ingestion counts quoted in prose ===")
    n_in = int(qam["records ingested"]["records"])
    n_ok = int(qam["admissible to primary calibration"]["records"])
    contains(report, f"{n_in:,}", "report quotes the ingested count")
    contains(report, f"{n_ok:,}", "report quotes the admissible count")
    contains(site, f"{n_in:,}", "site quotes the ingested count")

    print("\n=== derived shares quoted in prose ===")
    inferred = int(qam["of which unit inferred"]["records"])
    datum = int(qam["of which datum corrected"]["records"])
    amb = int(qam["ambiguous depth value (12)"]["records"])
    acv = int(qam["on actual cash value basis"]["records"])
    check("96.7% depth inferred", abs(100 * inferred / n_in - 96.7) < 0.1,
          f"{100*inferred/n_in:.2f}%")
    check("3.3% datum corrected", abs(100 * datum / n_in - 3.3) < 0.15,
          f"{100*datum/n_in:.2f}%")
    check("1.3% ambiguous dropped", abs(100 * amb / n_in - 1.3) < 0.1,
          f"{100*amb/n_in:.2f}%")
    # the ACV share is quoted as a share of *admissible* in the prose
    share_of_admissible = 100 * acv / n_ok
    share_of_ingested = 100 * acv / n_in
    if "99.5% of admissible records" in report:
        check("ACV share denominator is correct",
              abs(share_of_admissible - 99.5) < 0.2,
              f"as share of admissible = {share_of_admissible:.2f}% "
              f"(as share of ingested = {share_of_ingested:.2f}%)")

    print("\n=== benchmark numbers quoted in the findings ===")
    def pct(base, new, metric="CRPS"):
        return 100 * (ge.loc[new, metric] - ge.loc[base, metric]) / ge.loc[base, metric]

    v = abs(pct("JRC_NA_residential_published", "FloodVuln_G1_archetype"))
    check("event CRPS gain vs JRC quoted correctly",
          f"reduces CRPS by {v:.1f}%" in report, f"computed {v:.1f}%")
    v2 = abs(pct("single_curve_fitted_on_train", "FloodVuln_G1_archetype"))
    check("event CRPS gain vs fitted single curve",
          f"reduces CRPS by {v2:.1f}%" in report, f"computed {v2:.1f}%")
    v3 = abs(100 * (gr.loc["FloodVuln_G1_archetype", "CRPS"]
                    - gr.loc["JRC_NA_residential_published", "CRPS"])
             / gr.loc["JRC_NA_residential_published", "CRPS"])
    check("region CRPS gain vs JRC", f"reduces CRPS by {v3:.1f}%" in report,
          f"computed {v3:.1f}%")

    g1 = ge.loc["FloodVuln_G1_archetype", "CRPS"]
    g4 = ge.loc["FloodVuln_G4_local", "CRPS"]
    check("G1 CRPS quoted", f"{g1:.4f}" in report, f"{g1:.4f}")
    check("G4 CRPS quoted", f"{g4:.4f}" in report, f"{g4:.4f}")
    check("G1 beats G4 on CRPS (the finding's premise)", g1 < g4,
          f"G1={g1:.4f} G4={g4:.4f}")
    d = 100 * (g4 - g1) / g1
    check("G4-vs-G1 penalty quoted", f"increases CRPS by {d:.1f}%" in report,
          f"computed {d:.1f}%")
    check("site quotes the same G1/G4 CRPS to 3dp",
          f"{g1:.3f}" in site and f"{g4:.3f}" in site, f"{g1:.3f} / {g4:.3f}")

    print("\n=== JRC baseline diagnostics ===")
    slope = ge.loc["JRC_NA_residential_published", "calibration_slope"]
    bias = ge.loc["JRC_NA_residential_published", "bias"]
    check("JRC calibration slope quoted", f"{slope:.3f}" in report, f"{slope:.3f}")
    check("JRC bias quoted", f"{bias:+.4f}" in report, f"{bias:+.4f}")
    check("JRC really does over-predict (bias > 0)", bias > 0, f"{bias:+.4f}")

    print("\n=== region coverage claim ===")
    cov = gr.loc["FloodVuln_G1_archetype", "coverage_80"]
    check("withheld-region coverage quoted", f"{cov:.3f}" in report, f"{cov:.3f}")

    print("\n=== JRC curve library ===")
    from floodvuln import evidence as EV
    curves = EV.load_curves()
    n_pts = len(curves)
    n_cls = curves.damage_class.nunique()
    conts = set(curves.continent.unique()) - {"GLOBAL"}
    check("270 curve points quoted", f"{n_pts} curve points" in report, f"{n_pts}")
    check("6 damage classes", n_cls == 6, f"{n_cls}")
    check("6 continents (excluding the GLOBAL column)", len(conts) == 6,
          f"{len(conts)}: {sorted(conts)}")
    f = EV.curve_interpolator(curves, "Residential buildings", "EUROPE")
    published = [0, 0.25, 0.40, 0.50, 0.60, 0.75, 0.85, 0.95, 1.00]
    got = [float(f(d)) for d in [0, 0.5, 1, 1.5, 2, 3, 4, 5, 6]]
    check("Europe residential reproduces the published values",
          np.allclose(got, published, atol=1e-9), f"{got}")

    print("\n=== depth-unit evidence ===")
    du = open(os.path.join(ROOT, "reports", "depth_units.md"), encoding="utf-8").read()
    m = re.search(r"Claims with both depths positive: \*\*([\d,]+)\*\*", du)
    if m:
        check("paired-depth count quoted in report", m.group(1) in report, m.group(1))
    m = re.search(r"whole feet entry\): \*\*([\d.]+)%\*\*", du)
    if m:
        check("digit-preference share quoted", m.group(1) + "%" in report, m.group(1))

    print("\n=== internal consistency of the site ===")
    check("site no longer claims figures are illustrative",
          "figures on this page are illustrative" not in site)
    check("site no longer marked confidential", "Confidential" not in site)
    check("site carries the US-only scope statement",
          "US-only" in site or "United States" in site)
    check("site states the zero-mass conditioning",
          "conditional on a claim" in site or "claim filed" in site)

    print("\n=== no unreplaced placeholders or contradictory phrasing ===")
    check("report has no unreplaced placeholders", "[[" not in report)
    check("report has no 'improves ... by -' phrasing",
          not re.search(r"improves [A-Za-z ]*by <b>-", report))

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED")
        for f_ in FAILS:
            print("  -", f_)
    if WARNS:
        print(f"{len(WARNS)} warnings")
    if not FAILS:
        print("all report claims verified against source data")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
