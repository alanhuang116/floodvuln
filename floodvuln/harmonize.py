"""Harmonisation layer: messy source records -> canonical vulnerability observations.

Every transformation here is reversible in principle and recorded in a QA flag,
because a harmonisation that cannot be audited is indistinguishable from an
error. Three problems dominate the NFIP source:

1. **Units.** `waterDepth` is documented as inches but is dominantly feet. The
   rule below is derived in `scripts/depth_units.py` from a ratio test against
   `interiorWaterDepth`, a digit-preference test and a damage-response test.

2. **Datum.** `waterDepth` is adjuster practice relative to the lowest floor;
   `interiorWaterDepth` is relative to the lowest adjacent grade. Mixing them
   without correction shifts the whole curve by the floor-above-grade height.

3. **Damage basis.** `buildingDamageAmount` is an *actual cash value* figure,
   while `buildingReplacementCost` is a replacement cost. Dividing one by the
   other mixes bases and biases the damage ratio low. The ACV-consistent
   denominator `buildingPropertyValue` is preferred; the replacement-cost
   denominator is retained with an estimated conversion and a flag.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FT_TO_M = 0.3048
IN_TO_M = 0.0254

# Boundary between the feet-entry and inches-entry populations, from the
# ratio test: bands 1-11 read as feet, bands >=12 read as inches.
FEET_MAX = 11
AMBIGUOUS_VALUE = 12

MAX_DEPTH_M = 8.0        # beyond this, building damage ratio is not informative
MIN_DENOMINATOR = 5000.0  # dollars; below this the ratio is numerically unstable

# Undocumented sentinels found in the data rather than the dictionary.
# 99 carries n=8,817 with mean damage ratio 0.205, against 0.539 / 0.602 / 0.712
# at its immediate neighbours 96 / 108 / 120 (= 8, 9, 10 ft). A genuine 99 inch
# flood cannot be less damaging than a 96 inch one; the value is a not-reported
# code. 999 and 9999 follow the same pattern at lower volume.
DEPTH_SENTINELS = (99, 999, 9999, -99, -999)
MAX_PLAUSIBLE_FT = 30.0


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    """Always return a numeric Series, even when the column is absent.

    `DataFrame.get` returns a scalar NaN for a missing column, which silently
    turns downstream Series operations into numpy scalar errors. Sources differ
    in which optional fields they carry, so absence has to be a first-class case.
    """
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce")
    return pd.Series(np.nan, index=df.index, dtype=float)


def resolve_depth(df: pd.DataFrame) -> pd.DataFrame:
    """Add `depth_m` (metres above lowest floor) and the flags that justify it."""
    out = pd.DataFrame(index=df.index)
    wd = _col(df, "waterDepth")

    sentinel = wd.isin(DEPTH_SENTINELS)
    wd = wd.mask(sentinel)

    feet_reading = wd.abs() <= FEET_MAX
    depth_ft = np.where(feet_reading, wd, wd / 12.0)
    depth_ft = np.where(np.abs(depth_ft) > MAX_PLAUSIBLE_FT, np.nan, depth_ft)

    out["depth_sentinel"] = sentinel
    out["depth_m"] = depth_ft * FT_TO_M
    out["depth_source"] = "waterDepth"
    out["depth_unit_inferred"] = True
    out["depth_unit_reading"] = np.where(feet_reading, "feet", "inches")
    out["depth_ambiguous"] = wd.abs() == AMBIGUOUS_VALUE
    out["depth_at_floor_code"] = wd == 0

    # Where an unambiguous interior reading exists, prefer it and correct the datum
    # from lowest adjacent grade to lowest floor.
    iw = _col(df, "interiorWaterDepth")
    lag = _col(df, "lowestAdjacentGrade")
    lfe = _col(df, "lowestFloorElevation")
    floor_above_grade_ft = (lfe - lag)
    usable = iw.notna() & (iw > 0) & floor_above_grade_ft.between(0, 12)
    corrected_m = (iw * IN_TO_M) - (floor_above_grade_ft * FT_TO_M)

    out.loc[usable, "depth_m"] = corrected_m[usable]
    out.loc[usable, "depth_source"] = "interiorWaterDepth+datum"
    out.loc[usable, "depth_unit_inferred"] = False
    out.loc[usable, "depth_ambiguous"] = False
    return out


def resolve_damage(df: pd.DataFrame, acv_to_rc: float | None = None) -> pd.DataFrame:
    """Add `damage_ratio` on a consistent actual-cash-value basis, plus flags."""
    out = pd.DataFrame(index=df.index)
    dmg = _col(df, "buildingDamageAmount")
    acv = _col(df, "buildingPropertyValue")
    rc = _col(df, "buildingReplacementCost")

    acv_ok = acv.notna() & (acv >= MIN_DENOMINATOR)
    rc_ok = rc.notna() & (rc >= MIN_DENOMINATOR)

    if acv_to_rc is None:
        both = acv_ok & rc_ok
        acv_to_rc = float((acv[both] / rc[both]).median()) if both.sum() > 500 else 0.85

    denom = pd.Series(np.nan, index=df.index)
    basis = pd.Series("none", index=df.index)
    denom[rc_ok] = rc[rc_ok] * acv_to_rc
    basis[rc_ok] = "replacement_cost_converted"
    denom[acv_ok] = acv[acv_ok]
    basis[acv_ok] = "actual_cash_value"

    raw = dmg / denom
    out["damage_ratio"] = raw.clip(lower=0.0, upper=1.0)
    out["damage_basis"] = basis
    out["damage_exceeds_value"] = raw > 1.0
    out["damage_denominator"] = denom
    out["acv_to_rc_factor"] = acv_to_rc
    return out


def screen(df: pd.DataFrame, *, drop_ambiguous_depth: bool = True,
           drop_zero_depth_code: bool = False) -> pd.Series:
    """Boolean mask of records admissible to primary calibration, with reasons."""
    ok = df["damage_ratio"].notna() & df["depth_m"].notna()
    ok &= df["depth_m"].between(-2.0, MAX_DEPTH_M)
    ok &= df["damage_denominator"] >= MIN_DENOMINATOR
    if drop_ambiguous_depth:
        ok &= ~df["depth_ambiguous"].fillna(False)
    if drop_zero_depth_code:
        ok &= ~df["depth_at_floor_code"].fillna(False)
    if "agricultureStructureIndicator" in df:
        ok &= ~df["agricultureStructureIndicator"].fillna(False).astype(bool)
    return ok


def contract_terms_present(df: pd.DataFrame) -> pd.Series:
    """Flag claims where the payout is capped by the policy limit.

    These are retained for the *damage* model, because `buildingDamageAmount` is
    the adjuster's assessed damage rather than the payout, but the flag lets the
    validation step confirm that no contract signal has leaked into the fit.
    """
    paid = _col(df, "amountPaidOnBuildingClaim")
    cover = _col(df, "totalBuildingInsuranceCoverage")
    return (paid.notna() & cover.notna() & (cover > 0) & (paid >= cover * 0.995))


def harmonise(df: pd.DataFrame, **screen_kw) -> pd.DataFrame:
    """Full pipeline: raw NFIP frame -> canonical observations with QA flags."""
    parts = [df, resolve_depth(df), resolve_damage(df)]
    out = pd.concat(parts, axis=1)
    out["at_policy_limit"] = contract_terms_present(df)
    out["admissible"] = screen(out, **screen_kw)
    return out


def qa_summary(out: pd.DataFrame) -> pd.DataFrame:
    """Counts behind every screening decision, for the governance pack."""
    n = len(out)
    rows = [
        ("records ingested", n),
        ("depth resolved", int(out["depth_m"].notna().sum())),
        ("  of which unit inferred", int(out["depth_unit_inferred"].fillna(False).sum())),
        ("  of which datum corrected", int((out["depth_source"] != "waterDepth").sum())),
        ("  ambiguous depth value (12)", int(out["depth_ambiguous"].fillna(False).sum())),
        ("  undocumented sentinel depth (99/999)", int(out["depth_sentinel"].fillna(False).sum())),
        ("  depth reported as 0 (water at floor)", int(out["depth_at_floor_code"].fillna(False).sum())),
        ("damage ratio computed", int(out["damage_ratio"].notna().sum())),
        ("  on actual cash value basis", int((out["damage_basis"] == "actual_cash_value").sum())),
        ("  on converted replacement cost", int((out["damage_basis"] == "replacement_cost_converted").sum())),
        ("  damage exceeded value (clipped to 1)", int(out["damage_exceeds_value"].fillna(False).sum())),
        ("claims settled at the policy limit", int(out["at_policy_limit"].fillna(False).sum())),
        ("admissible to primary calibration", int(out["admissible"].sum())),
    ]
    d = pd.DataFrame(rows, columns=["step", "records"])
    d["share_of_ingested"] = (d["records"] / n).round(4)
    return d
