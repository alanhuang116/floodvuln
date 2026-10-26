"""Reconnaissance on the raw NFIP pull: what is actually usable, and how messy is it.

Run before writing any harmonisation rules, so the rules are driven by the data
rather than by assumption.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

RAW = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "nfip_claims.csv")

USE = [
    "id", "yearOfLoss", "state", "floodEvent", "causeOfDamage",
    "waterDepth", "interiorWaterDepth", "exteriorWaterDepth",
    "buildingDamageAmount", "buildingPropertyValue", "buildingReplacementCost",
    "occupancyType", "numberOfFloorsInTheInsuredBuilding", "foundationType",
    "basementEnclosureCrawlspaceType", "elevatedBuildingIndicator",
    "replacementCostBasis", "totalBuildingInsuranceCoverage",
    "amountPaidOnBuildingClaim",
]


def main() -> None:
    nrows = int(sys.argv[1]) if len(sys.argv) > 1 else None
    df = pd.read_csv(RAW, usecols=lambda c: c in USE, nrows=nrows, low_memory=False)
    print(f"rows read: {len(df):,}\n")

    print("=== missingness (%) ===")
    print((df.isna().mean() * 100).round(1).sort_values().to_string())

    wd = pd.to_numeric(df["waterDepth"], errors="coerce")
    print("\n=== waterDepth (raw, documented as inches) ===")
    print(wd.describe(percentiles=[.01, .05, .25, .5, .75, .9, .95, .99]).round(2).to_string())
    print("\nvalue counts of the 25 most common raw values:")
    print(wd.value_counts().head(25).to_string())
    print(f"\nnegative: {(wd < 0).mean() * 100:.2f}%   zero: {(wd == 0).mean() * 100:.2f}%   "
          f"<= 20: {(wd.between(0, 20)).mean() * 100:.2f}%   > 200: {(wd > 200).mean() * 100:.3f}%")

    iw = pd.to_numeric(df["interiorWaterDepth"], errors="coerce")
    both = df[wd.notna() & iw.notna()].copy()
    print(f"\n=== waterDepth vs interiorWaterDepth (n={len(both):,}) ===")
    if len(both):
        w, i = wd[both.index], iw[both.index]
        ratio = (i / w.replace(0, np.nan))
        print("ratio interior/waterDepth quantiles:")
        print(ratio.quantile([.05, .25, .5, .75, .95]).round(2).to_string())
        # if waterDepth were sometimes in feet, ratio would cluster near 12
        for lo, hi in [(1, 24), (25, 60), (61, 400)]:
            m = w.between(lo, hi)
            if m.sum() > 200:
                print(f"  waterDepth in [{lo},{hi}] n={m.sum():,}  "
                      f"median interior={i[m].median():.0f} in  median ratio={ratio[m].median():.2f}")

    print("\n=== damage ratio denominators ===")
    dmg = pd.to_numeric(df["buildingDamageAmount"], errors="coerce")
    acv = pd.to_numeric(df["buildingPropertyValue"], errors="coerce")
    rc = pd.to_numeric(df["buildingReplacementCost"], errors="coerce")
    for name, den in [("buildingPropertyValue (ACV)", acv), ("buildingReplacementCost", rc)]:
        ok = den.notna() & (den > 1000) & dmg.notna()
        dr = (dmg[ok] / den[ok])
        print(f"{name}: usable {ok.sum():,} ({ok.mean() * 100:.1f}%)  "
              f"DR med={dr.median():.3f} mean={dr.mean():.3f} "
              f">1: {(dr > 1).mean() * 100:.2f}%  ==0: {(dr == 0).mean() * 100:.2f}%")
    both_den = acv.notna() & rc.notna() & (acv > 1000) & (rc > 1000)
    if both_den.sum() > 100:
        r = (acv[both_den] / rc[both_den])
        print(f"ACV / ReplacementCost ratio (n={both_den.sum():,}): "
              f"median={r.median():.3f}  q25={r.quantile(.25):.3f} q75={r.quantile(.75):.3f}")

    print("\n=== categorical structure ===")
    for c in ["occupancyType", "numberOfFloorsInTheInsuredBuilding", "foundationType",
              "basementEnclosureCrawlspaceType", "replacementCostBasis",
              "elevatedBuildingIndicator", "causeOfDamage"]:
        vc = df[c].value_counts(dropna=False).head(10)
        print(f"\n-- {c}\n{vc.to_string()}")

    print("\n=== top events ===")
    print(df["floodEvent"].value_counts().head(20).to_string())
    print("\n=== top states ===")
    print(df["state"].value_counts().head(15).to_string())
    print("\n=== years ===")
    print(df["yearOfLoss"].describe().round(0).to_string())


if __name__ == "__main__":
    main()
