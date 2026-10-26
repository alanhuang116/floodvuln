# FloodVuln calibration and validation summary

- observations: **1,861,852**
- archetype groups: **142**, regions: **58**
- depth range used: -2.00 to 7.92 m
- share exactly 0 damage: 0.4%, exactly total: 2.6%

## Leave-one-event-out (mean over folds)

| model                        |    MAE |   RMSE |    bias |   CRPS |   coverage_80 |   PIT_KS |   calibration_slope |   sharpness_p10_p90 |
|:-----------------------------|-------:|-------:|--------:|-------:|--------------:|---------:|--------------------:|--------------------:|
| FloodVuln_G1_archetype       | 0.2169 | 0.2695 | -0.046  | 0.1489 |        0.7859 |   0.146  |              1.0647 |              0.5926 |
| FloodVuln_G4_local           | 0.2193 | 0.2775 | -0.0599 | 0.154  |        0.7528 |   0.1604 |              1.0515 |              0.5527 |
| FloodVuln_G0_global_fit      | 0.2324 | 0.2827 | -0.0487 | 0.1583 |        0.789  |   0.1458 |              0.8262 |              0.6248 |
| single_curve_fitted_on_train | 0.2305 | 0.2859 | -0.0727 | 0.2305 |      nan      | nan      |              0.8289 |              0      |
| naive_constant_mean          | 0.2469 | 0.2986 | -0.0712 | 0.2469 |      nan      | nan      |            nan      |              0      |
| JRC_NA_residential_published | 0.2493 | 0.3031 |  0.091  | 0.2493 |      nan      | nan      |              0.3603 |              0      |

## Leave-one-region-out, zero local evidence in the held-out region

| model                        |    MAE |   RMSE |   bias |   CRPS |   coverage_80 |   PIT_KS |   calibration_slope |   sharpness_p10_p90 |
|:-----------------------------|-------:|-------:|-------:|-------:|--------------:|---------:|--------------------:|--------------------:|
| FloodVuln_G1_archetype       | 0.1912 | 0.2439 | 0.0164 | 0.1237 |        0.8362 |   0.1023 |              0.8808 |              0.5681 |
| FloodVuln_G0_global_fit      | 0.2111 | 0.2584 | 0.0353 | 0.1332 |        0.8398 |   0.1437 |              0.7595 |              0.6273 |
| single_curve_fitted_on_train | 0.2028 | 0.256  | 0.0108 | 0.2028 |      nan      | nan      |              0.7637 |              0      |
| naive_constant_mean          | 0.2141 | 0.2618 | 0.0134 | 0.2141 |      nan      | nan      |            nan      |              0      |
| JRC_NA_residential_published | 0.2695 | 0.3239 | 0.1657 | 0.2695 |      nan      | nan      |              0.3388 |              0      |

## Sparse-data learning curve (LA, RES.SF.1.UNK)

|   n_local |   ('MAE', 'hierarchical') |   ('MAE', 'local_only') |   ('CRPS', 'hierarchical') |   ('CRPS', 'local_only') |
|----------:|--------------------------:|------------------------:|---------------------------:|-------------------------:|
|         0 |                    0.2745 |                nan      |                     0.1888 |                 nan      |
|         5 |                    0.2714 |                  0.2598 |                     0.1811 |                   0.2185 |
|        10 |                    0.2718 |                  0.2483 |                     0.1831 |                   0.1792 |
|        25 |                    0.2697 |                  0.2324 |                     0.1765 |                   0.1551 |
|        50 |                    0.2679 |                  0.2303 |                     0.1738 |                   0.1526 |
|       100 |                    0.2666 |                  0.2272 |                     0.1681 |                   0.1485 |
|       250 |                    0.2666 |                  0.2244 |                     0.1648 |                   0.1462 |
|       500 |                    0.2674 |                  0.2274 |                     0.1641 |                   0.1456 |
|      1000 |                    0.2674 |                  0.2276 |                     0.164  |                   0.1456 |
|      2500 |                    0.2673 |                  0.2281 |                     0.1636 |                   0.1454 |

