"""Second pull: claims with a reported depth but ZERO assessed building damage.

The primary pull filters `buildingDamageAmount gt 0`, which silently removes the
entire zero point mass. Without these records P(D = 0) is unidentifiable and the
zero-inflation component of the ZOIB would be fitted to a truncated sample.

Important limitation, carried into the report: this recovers
P(D = 0 | a claim was filed), not P(D = 0 | the building was inundated).
Buildings that were flooded and never claimed are absent from the NFIP file
altogether, so the fitted zero probability is a *lower bound* on the true
probability of no damage given inundation.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_nfip as base  # noqa: E402

base.OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                        "data", "raw", "nfip_claims_zero.csv")
base.FILTER = ("waterDepth ne null and buildingDamageAmount eq 0 "
               "and (buildingPropertyValue gt 0 or buildingReplacementCost gt 0)")

if __name__ == "__main__":
    base.main()
