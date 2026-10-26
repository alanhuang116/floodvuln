"""Universal building and asset taxonomy, and crosswalks from national schemes.

The taxonomy is the vocabulary that lets evidence collected under one national
classification inform a prediction under another, without asserting that unlike
assets are equivalent. Six levels, coarse to fine:

    L1 sector        RES COM IND PUB AGR INF
    L2 occupancy     SF MF2_4 MF5P UNIT MOBILE RETAIL OFFICE WAREHOUSE ...
    L3 construction  WOOD MASONRY RC STEEL EARTH MIXED UNK
    L4 configuration storeys x foundation
    L5 resilience    CONV ELEV FLOODPROOF ELEV_FLOODPROOF
    L6 local         code era, CRS class, regional cost regime

An archetype id is the dot-joined path, e.g.

    US.RES.SF.WOOD.1.SLAB.CONV

Every crosswalk records whether a level was *observed* in the source data or
*assumed*, because an assumed level must widen uncertainty rather than silently
pass as knowledge.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# --------------------------------------------------------------------------
# controlled vocabularies
# --------------------------------------------------------------------------
SECTORS = ("RES", "COM", "IND", "PUB", "AGR", "INF")

OCCUPANCY = {
    "RES": ("SF", "MF2_4", "MF5P", "UNIT", "MOBILE"),
    "COM": ("RETAIL", "OFFICE", "HOTEL", "MIXED"),
    "IND": ("WAREHOUSE", "MANUFACTURING"),
    "PUB": ("SCHOOL", "HOSPITAL", "CIVIC"),
    "AGR": ("CROP", "FARM_BUILDING"),
    "INF": ("ROAD", "RAIL", "UTILITY"),
}

CONSTRUCTION = ("WOOD", "MASONRY", "RC", "STEEL", "EARTH", "MIXED", "UNK")

STOREYS = ("1", "2", "3P", "SPLIT", "MH")          # MH = manufactured home
FOUNDATION = ("SLAB", "BASEMENT", "CRAWL", "ELEV_OPEN", "ELEV_ENCL", "UNK")
RESILIENCE = ("CONV", "ELEV", "FLOODPROOF", "ELEV_FLOODPROOF")
CODE_ERA = ("PRE_FIRM", "POST_FIRM", "UNK")


@dataclass(frozen=True)
class Archetype:
    """A point in the taxonomy, plus a record of what was observed vs assumed."""

    region: str = "GLB"
    sector: str = "RES"
    occupancy: str = "SF"
    construction: str = "UNK"
    storeys: str = "1"
    foundation: str = "UNK"
    resilience: str = "CONV"
    code_era: str = "UNK"
    assumed: frozenset = field(default_factory=frozenset)

    @property
    def id(self) -> str:
        return ".".join([self.region, self.sector, self.occupancy, self.construction,
                         self.storeys, self.foundation, self.resilience])

    @property
    def group_key(self) -> str:
        """Key used for hierarchical pooling: the levels that carry damage signal."""
        return ".".join([self.sector, self.occupancy, self.storeys, self.foundation])

    def parents(self) -> list[str]:
        """Backoff path from most to least specific, used when evidence is thin."""
        return [
            self.group_key,
            ".".join([self.sector, self.occupancy, self.storeys]),
            ".".join([self.sector, self.occupancy]),
            self.sector,
        ]

    def __str__(self) -> str:  # pragma: no cover - display only
        return self.id


# --------------------------------------------------------------------------
# NFIP crosswalk
# --------------------------------------------------------------------------
# occupancyType -> (sector, occupancy).  Codes 1-6 are legacy, 11-19 Risk Rating 2.0.
NFIP_OCCUPANCY = {
    1: ("RES", "SF"), 2: ("RES", "MF2_4"), 3: ("RES", "MF5P"),
    4: ("COM", "MIXED"), 6: ("COM", "RETAIL"),
    11: ("RES", "SF"), 12: ("RES", "MF2_4"), 13: ("RES", "MF5P"),
    14: ("RES", "MOBILE"), 15: ("RES", "MF5P"), 16: ("RES", "UNIT"),
    17: ("COM", "MIXED"), 18: ("COM", "MIXED"), 19: ("COM", "MIXED"),
}

# numberOfFloorsInTheInsuredBuilding -> storeys
NFIP_STOREYS = {1: "1", 2: "2", 3: "3P", 4: "SPLIT", 5: "MH", 6: "3P"}

# foundationType -> foundation.  Code 0 appears on 80% of records and is NOT in
# the published dictionary (which lists 1-6); it is a not-reported code and is
# deliberately absent here so that it falls through to UNK and is flagged.
NFIP_FOUNDATION = {
    1: "SLAB", 2: "BASEMENT", 3: "CRAWL",
    4: "ELEV_OPEN", 5: "ELEV_ENCL", 6: "ELEV_ENCL",
}

# basementEnclosureCrawlspaceType, used only when foundationType is absent
NFIP_BASEMENT = {0: "SLAB", 1: "BASEMENT", 2: "BASEMENT", 3: "CRAWL", 4: "CRAWL"}


def from_nfip(occupancy_type, floors, foundation_type, basement_type,
              elevated, floodproofed, post_firm, state=None) -> Archetype:
    """Map one NFIP claim record onto the universal taxonomy.

    Construction material is *not recorded* by the NFIP. US single-family
    residential stock is overwhelmingly light-frame timber, so WOOD is assigned
    for that occupancy and recorded in `assumed`; everything else stays UNK
    rather than being guessed.
    """
    assumed: set[str] = set()

    sector, occ = NFIP_OCCUPANCY.get(_as_int(occupancy_type), ("RES", "SF"))
    if _as_int(occupancy_type) is None:
        assumed.add("occupancy")

    storeys = NFIP_STOREYS.get(_as_int(floors), "1")
    if _as_int(floors) is None:
        assumed.add("storeys")

    fnd = NFIP_FOUNDATION.get(_as_int(foundation_type))
    if fnd is None:
        fnd = NFIP_BASEMENT.get(_as_int(basement_type), "UNK")
        if fnd != "UNK":
            assumed.add("foundation_from_basement_code")
        else:
            assumed.add("foundation")

    if sector == "RES" and occ in ("SF", "MF2_4", "MOBILE"):
        construction = "WOOD"
        assumed.add("construction")
    else:
        construction = "UNK"
        assumed.add("construction")

    if _as_bool(floodproofed) and _as_bool(elevated):
        res = "ELEV_FLOODPROOF"
    elif _as_bool(floodproofed):
        res = "FLOODPROOF"
    elif _as_bool(elevated):
        res = "ELEV"
    else:
        res = "CONV"

    era = "POST_FIRM" if _as_bool(post_firm) else ("PRE_FIRM" if post_firm is not None else "UNK")

    return Archetype(region=f"US.{state}" if state else "US", sector=sector,
                     occupancy=occ, construction=construction, storeys=storeys,
                     foundation=fnd, resilience=res, code_era=era,
                     assumed=frozenset(assumed))


# --------------------------------------------------------------------------
# JRC crosswalk: the global prior speaks in six coarse damage classes only
# --------------------------------------------------------------------------
JRC_CLASS_FOR_SECTOR = {
    "RES": "Residential buildings",
    "COM": "Commercial buildings",
    "IND": "Industrial buildings",
    "INF": "Infrastructure - roads",
    "AGR": "Agriculture",
    "PUB": "Commercial buildings",   # JRC has no public class; commercial is the closest
}

JRC_CONTINENT_FOR_REGION = {
    "US": "North AMERICA", "CA": "North AMERICA", "MX": "Centr&South AMERICA",
    "GB": "EUROPE", "DE": "EUROPE", "NL": "EUROPE", "IT": "EUROPE", "FR": "EUROPE",
    "JP": "ASIA", "VN": "ASIA", "TH": "ASIA", "IN": "ASIA", "CN": "ASIA",
    "AU": "OCEANIA", "NZ": "OCEANIA",
    "ZA": "AFRICA", "NG": "AFRICA", "MZ": "AFRICA",
    "BR": "Centr&South AMERICA", "AR": "Centr&South AMERICA",
}


def jrc_lookup(archetype: Archetype) -> tuple[str, str]:
    """Return (damage class, continent) for the JRC global prior."""
    country = archetype.region.split(".")[0]
    return (JRC_CLASS_FOR_SECTOR.get(archetype.sector, "Residential buildings"),
            JRC_CONTINENT_FOR_REGION.get(country, "GLOBAL"))


# --------------------------------------------------------------------------
def _as_int(v):
    try:
        if v is None or v != v:      # NaN
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _as_bool(v):
    if v is None or v != v:
        return False
    if isinstance(v, str):
        return v.strip().lower() in ("true", "t", "1", "y", "yes")
    return bool(v)


def enumerate_group_keys(archetypes: Iterable[Archetype]) -> list[str]:
    return sorted({a.group_key for a in archetypes})
