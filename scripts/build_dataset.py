"""Build the canonical calibration dataset from the raw OpenFEMA pulls.

Raw claims -> harmonised observations -> universal taxonomy -> parquet/CSV,
with a QA table that accounts for every record dropped along the way.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from floodvuln import harmonize, taxonomy  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "..", "data", "raw", "nfip_claims.csv")
RAW0 = os.path.join(HERE, "..", "data", "raw", "nfip_claims_zero.csv")
OUT = os.path.join(HERE, "..", "data", "processed", "calibration.parquet")
QA = os.path.join(HERE, "..", "reports", "qa_ingestion.csv")

KEEP = ["id", "yearOfLoss", "state", "countyCode", "floodEvent", "causeOfDamage",
        "depth_m", "depth_source", "depth_unit_inferred", "depth_ambiguous",
        "depth_at_floor_code", "damage_ratio", "damage_basis",
        "damage_exceeds_value", "damage_denominator", "at_policy_limit",
        "occupancyType", "numberOfFloorsInTheInsuredBuilding", "foundationType",
        "basementEnclosureCrawlspaceType", "elevatedBuildingIndicator",
        "floodproofedIndicator", "postFIRMConstructionIndicator",
        "floodWaterDuration", "latitude", "longitude", "ratedFloodZone",
        "archetype_id", "group_key", "sector", "occupancy", "storeys",
        "foundation", "resilience", "assumed_levels"]


def add_taxonomy(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorised crosswalk: unique attribute combinations, then map back."""
    cols = ["occupancyType", "numberOfFloorsInTheInsuredBuilding", "foundationType",
            "basementEnclosureCrawlspaceType", "elevatedBuildingIndicator",
            "floodproofedIndicator", "postFIRMConstructionIndicator"]
    for c in cols:
        if c not in df:
            df[c] = np.nan
    combos = df[cols].drop_duplicates()
    recs = []
    for row in combos.itertuples(index=False):
        a = taxonomy.from_nfip(row[0], row[1], row[2], row[3], row[4], row[5], row[6])
        recs.append({**{c: v for c, v in zip(cols, row)},
                     "archetype_id": a.id, "group_key": a.group_key,
                     "sector": a.sector, "occupancy": a.occupancy,
                     "storeys": a.storeys, "foundation": a.foundation,
                     "resilience": a.resilience,
                     "assumed_levels": ";".join(sorted(a.assumed))})
    lut = pd.DataFrame(recs)
    return df.merge(lut, on=cols, how="left")


def main() -> None:
    frames = []
    for path, label in [(RAW, "damage>0"), (RAW0, "damage==0")]:
        if not os.path.exists(path) or os.path.getsize(path) < 1024:
            print(f"  ({os.path.basename(path)} missing or still downloading, skipped)")
            continue
        d = pd.read_csv(path, low_memory=False)
        d["pull"] = label
        frames.append(d)
        print(f"  {label}: {len(d):,} rows")
    df = pd.concat(frames, ignore_index=True)
    print(f"total raw: {len(df):,}")

    out = harmonize.harmonise(df)
    qa = harmonize.qa_summary(out)
    os.makedirs(os.path.dirname(QA), exist_ok=True)
    qa.to_csv(QA, index=False)
    print("\n=== ingestion QA ===")
    print(qa.to_string(index=False))

    keep = out[out["admissible"]].copy()
    keep = add_taxonomy(keep)
    keep = keep[[c for c in KEEP if c in keep.columns]]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    try:
        keep.to_parquet(OUT, index=False)
        print(f"\nwrote {len(keep):,} admissible observations -> {OUT}")
    except Exception as exc:  # noqa: BLE001 - parquet engine may be absent
        alt = OUT.replace(".parquet", ".csv")
        keep.to_csv(alt, index=False)
        print(f"\nparquet unavailable ({exc}); wrote CSV -> {alt}")

    print("\n=== damage ratio by depth, single-family one-storey slab ===")
    m = (keep["group_key"] == "RES.SF.1.SLAB")
    s = keep[m]
    b = pd.cut(s["depth_m"], [-2, -0.5, 0.01, 0.35, 0.7, 1.1, 1.6, 2.2, 3.1, 8])
    print(s.groupby(b, observed=True)["damage_ratio"]
          .agg(["count", "mean", "median",
                lambda x: (x <= 1e-4).mean(), lambda x: (x >= 0.9999).mean()])
          .rename(columns={"<lambda_0>": "P(D=0)", "<lambda_1>": "P(D=1)"})
          .round(3).to_string())

    print("\n=== top archetype groups ===")
    print(keep["group_key"].value_counts().head(15).to_string())
    print("\n=== top events ===")
    print(keep["floodEvent"].value_counts().head(12).to_string())
    print("\n=== top states ===")
    print(keep["state"].value_counts().head(12).to_string())


if __name__ == "__main__":
    main()
