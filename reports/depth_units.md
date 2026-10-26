# NFIP `waterDepth` unit resolution

Records analysed: **830,000**

## A. Ratio test against `interiorWaterDepth` (documented inches)

Claims with both depths positive: **66,117**

| ratio interior/waterDepth | share |
|---|---|
| 0 - 0.5 | 5.2% |
| 0.5 - 1.5 | 12.3% |
| 1.5 - 3 | 2.3% |
| 3 - 6 | 6.1% |
| 6 - 9 | 16.2% |
| 9 - 15 | 49.8% |
| 15 - 30 | 7.2% |
| 30 - 1e+09 | 0.9% |

Mass consistent with **inches** (ratio ~1): 12.3%  
Mass consistent with **feet** (ratio ~12, widened for the datum offset): 73.2%

Ratio by magnitude of the reported `waterDepth` value:

| waterDepth band | n | median interior (in) | median ratio | reading |
|---|---|---|---|---|
| 1-3 | 50,680 | 12 | 10.0 | feet |
| 4-6 | 7,276 | 48 | 11.2 | feet |
| 7-11 | 2,542 | 81 | 11.2 | feet |
| 12-12 | 234 | 12 | 1.0 | inches |
| 13-24 | 1,068 | 18 | 1.0 | inches |
| 25-48 | 899 | 36 | 1.0 | inches |
| 49-400 | 3,416 | 3 | 0.0 | inches |

## C. Digit preference in the raw values

- share of positive values in 1-10 (whole feet entry): **85.5%**
- share that are exact multiples of 12 (inches entry of whole feet): **4.7%**
- share that are exact multiples of 6: **9.2%**
- share > 12 (only plausible as inches for a habitable floor): **12.1%**

## B. Damage response under each unit hypothesis

Single-family, one storey, usable damage ratio: **372,253** claims

| reported waterDepth | n | mean DR | median DR | depth if FEET | depth if INCHES |
|---|---|---|---|---|---|
| 0 | 111,430 | 0.196 | 0.090 | 0.00 m | 0.000 m |
| 1 | 112,145 | 0.247 | 0.165 | 0.30 m | 0.025 m |
| 2 | 39,395 | 0.348 | 0.317 | 0.61 m | 0.051 m |
| 3 | 21,144 | 0.395 | 0.369 | 0.91 m | 0.076 m |
| 4 | 14,329 | 0.463 | 0.437 | 1.22 m | 0.102 m |
| 5 | 8,545 | 0.539 | 0.546 | 1.52 m | 0.127 m |
| 6 | 7,391 | 0.508 | 0.474 | 1.83 m | 0.152 m |
| 8 | 5,484 | 0.596 | 0.640 | 2.44 m | 0.203 m |
| 10 | 5,050 | 0.718 | 0.888 | 3.05 m | 0.254 m |
| 12 | 3,978 | 0.494 | 0.438 | 3.66 m | 0.305 m |
| 24 | 1,296 | 0.389 | 0.380 | 7.32 m | 0.610 m |
| 36 | 881 | 0.441 | 0.423 | 10.97 m | 0.914 m |
| 48 | 717 | 0.509 | 0.533 | 14.63 m | 1.219 m |

- Spearman-free linear correlation of DR with depth in metres, FEET reading, 0-6 m window: **r = 0.369** on n=350,375
- Spearman-free linear correlation of DR with depth in metres, INCHES reading, 0-6 m window: **r = 0.216** on n=371,756

## Verdict

The three tests agree: the dominant reading of `waterDepth` is **feet relative to the lowest floor**, not inches. Records above ~12 are a mixed population, and the unit for an individual record is not recoverable with certainty.

Harmonisation rule adopted (implemented in `floodvuln.harmonize`):

1. Treat `waterDepth` as **feet** when |value| <= 12.
2. Treat values > 12 as **inches** and divide by 12, which maps 24 -> 2 ft, 36 -> 3 ft, consistent with the observed spikes at multiples of 12.
3. Flag every record whose unit was inferred rather than observed (`depth_unit_inferred = True`) and carry the flag into the evidence grade.
4. Where `interiorWaterDepth` is present, prefer it, converting inches to metres and correcting the datum from lowest adjacent grade to lowest floor.

