"""Download the OpenFEMA NFIP redacted claims subset used for FloodVuln calibration.

Uses keyset pagination on `id` (OpenFEMA's recommended approach for large pulls)
so the download is resumable and never silently truncates at a $skip ceiling.

Only claims that can support a ground-up damage ratio are requested:
a reported water depth, a positive assessed building damage amount, and at
least one usable denominator (pre-event actual cash value or replacement cost).

Source: FEMA OpenFEMA, dataset `NfipClaims` v3 (NFIP Redacted Claims).
Public domain / open data. No authentication required.
"""
from __future__ import annotations

import csv
import io
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://www.fema.gov/api/open/v3/NfipClaims"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "nfip_claims.csv")
PAGE = 10000

FIELDS = [
    # identity / geography / event
    "id", "yearOfLoss", "dateOfLoss", "state", "countyCode", "censusGeoid",
    "latitude", "longitude", "floodEvent", "causeOfDamage",
    # hazard: three depth measures on two different datums, plus elevations
    "waterDepth", "interiorWaterDepth", "exteriorWaterDepth",
    "lowestAdjacentGrade", "lowestFloorElevation", "baseFloodElevation",
    "elevationDifference", "floodWaterDuration",
    # damage and value (ACV damage; ACV and replacement-cost denominators)
    "buildingDamageAmount", "buildingPropertyValue", "buildingReplacementCost",
    "contentsDamageAmount", "contentsPropertyValue", "contentsReplacementCost",
    "replacementCostBasis",
    # building attributes -> universal taxonomy L1-L6
    "occupancyType", "buildingDescriptionCode",
    "numberOfFloorsInTheInsuredBuilding", "foundationType",
    "basementEnclosureCrawlspaceType", "elevatedBuildingIndicator",
    "floodproofedIndicator", "obstructionType", "numberOfUnits",
    "originalConstructionDate", "postFIRMConstructionIndicator",
    "preFirmIndicator", "ratedFloodZone", "crsClassCode",
    # financial terms - retained ONLY to exclude contract effects, never to fit
    "totalBuildingInsuranceCoverage", "amountPaidOnBuildingClaim",
    "buildingDeductibleCode",
    # screening flags
    "agricultureStructureIndicator", "primaryResidenceIndicator",
]

FILTER = ("waterDepth ne null and buildingDamageAmount gt 0 "
          "and (buildingPropertyValue gt 0 or buildingReplacementCost gt 0)")


def build_url(last_id: int) -> str:
    params = {
        "$top": PAGE,
        "$orderby": "id",
        "$select": ",".join(FIELDS),
        "$filter": f"{FILTER} and id gt {last_id}",
        "$format": "csv",
        "$metadata": "off",
    }
    return BASE + "?" + urllib.parse.urlencode(params)


def fetch(url: str, tries: int = 6) -> str:
    delay = 3.0
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "floodvuln-research/1.0 (calibration study)"}
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - network layer, retry everything
            if attempt == tries - 1:
                raise
            sys.stderr.write(f"  retry {attempt + 1}/{tries} after {exc}\n")
            sys.stderr.flush()
            time.sleep(delay)
            delay = min(delay * 1.8, 60)
    raise RuntimeError("unreachable")


def resume_point(path: str) -> int:
    """Largest id already written, so an interrupted run continues cleanly."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return 0
    last = 0
    with open(path, "r", encoding="utf-8", newline="") as fh:
        rdr = csv.DictReader(fh)
        for row in rdr:
            try:
                last = max(last, int(row["id"]))
            except (KeyError, TypeError, ValueError):
                continue
    return last


def main() -> None:
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    last_id = resume_point(OUT)
    mode = "a" if last_id else "w"
    total = 0 if mode == "w" else -1
    sys.stderr.write(f"resuming from id {last_id}\n")

    t0 = time.time()
    with open(OUT, mode, encoding="utf-8", newline="") as out:
        page = 0
        while True:
            text = fetch(build_url(last_id))
            rows = list(csv.reader(io.StringIO(text)))
            if not rows:
                break
            header, body = rows[0], rows[1:]
            if not body:
                break
            if mode == "w" and page == 0:
                out.write(",".join(header) + "\n")
            w = csv.writer(out, lineterminator="\n")
            w.writerows(body)
            out.flush()

            idx = header.index("id")
            last_id = max(int(r[idx]) for r in body)
            total = (total if total > 0 else 0) + len(body)
            page += 1
            rate = total / max(1e-9, time.time() - t0)
            sys.stderr.write(
                f"page {page:4d}  rows {len(body):6d}  cumulative {total:9d}  "
                f"last_id {last_id:9d}  {rate:7.0f} rows/s\n"
            )
            sys.stderr.flush()
            if len(body) < PAGE:
                break

    sys.stderr.write(f"done: {total} rows in {time.time() - t0:.0f}s -> {OUT}\n")


if __name__ == "__main__":
    main()
