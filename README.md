# FloodVuln Global

A working implementation of the FloodVuln Global flood vulnerability platform,
calibrated against real public data and validated by the benchmark programme
its product specification sets out. A product of [Entanglix](https://entanglix.tech/).

**Site:** https://alanhuang116.github.io/floodvuln/ — rebuilt into `docs/` from the fitted model by `scripts/update_site.py`.
**Report:** `reports/floodvuln_report.html` — findings, methods, limitations.

## What it is calibrated on

| Source | Licence | Status |
|---|---|---|
| OpenFEMA NFIP Redacted Claims v3 | Open | **Ingested** — 1,927,948 pulled, 1,861,852 admissible |
| JRC global depth–damage functions (Huizinga et al. 2017) | Open | **Ingested** — 270 curve points, 6 classes × 6 continents |
| FEMA Hazus / USACE NACCS | Open | Not obtained — document endpoints return HTTP 403 to automated retrieval |
| HOWAS21 | Reference only | Not obtained — registration and data agreement required |
| Multi-Coloured Manual (UK) | Licensed | Not obtained — commercial licence required, deliberately not scraped |

Calibration is therefore **US residential and small commercial only**. No claim
is made about other markets.

## Headline results (out of sample)

| Test | Baseline | FloodVuln | Change |
|---|---|---|---|
| 11 withheld events, CRPS | JRC published 0.2493 | archetype 0.1489 | **−40.2%** |
| 11 withheld events, CRPS | best fitted single curve 0.2305 | archetype 0.1489 | **−35.4%** |
| 9 withheld states (no local data), CRPS | JRC published 0.2695 | archetype 0.1237 | **−54.1%** |
| 9 withheld states, MAE | JRC published 0.2695 | archetype 0.1912 | **−29.1%** |

Interval coverage on withheld states is 0.836 against a nominal 0.80.

## Findings that contradicted the concept

1. **Local calibration relocates the distribution; it does not sharpen it.** The
   P10–P90 width is unchanged by local evidence — that width is irreducible
   building-to-building variability. The *epistemic* component falls ~100×.
2. **Region calibration did not generalise to a new event** and slightly hurt
   (CRPS 0.154 vs 0.149 for the archetype model).
3. **The zero point mass is unobservable in claims data.** P(D=0) here is
   conditional on a claim being filed and is a lower bound.
4. **The missing dimension is the event, not the building.** An oracle
   event-level offset is worth ~23% CRPS; the only extra NFIP hazard variable is
   worth 0.0%.
5. **Partial pooling under-performed an unpooled refit — diagnosed and fixed.**
   Regional variation is in the *slope* of the depth response, which a level-only
   offset cannot express. A shape offset gives ~4.2% CRPS and restores the
   pooling advantage below ~50 local records.

## Layout

```
floodvuln/           taxonomy, harmonisation, evidence register, model,
                     calibration, prediction, validation
scripts/             data acquisition, dataset build, figures, exports
experiments/         calibration run, covariate test, shape-offset test
tests/               property tests (Python) and JS/Python parity check
reports/             benchmark CSVs, QA tables, the report
figures/             all figures, generated
web/                 model bundle and the JS blocks spliced into the site
```

## Reproducing

```
python scripts/fetch_nfip.py              # ~16 min, 1.9m records
python scripts/fetch_nfip_zero.py
python scripts/depth_units.py             # the unit-resolution evidence
python scripts/build_dataset.py
python experiments/run_calibration.py     # ~90 min, 20 folds
python experiments/run_covariates.py
python experiments/run_shape_offset.py
python scripts/add_covariances.py
python scripts/make_figures.py
python scripts/export_to_web.py && python scripts/update_site.py
python scripts/make_report.py
python tests/test_core.py
node tests/test_js_parity.js <site.html>
```

`FV_REFIT=1` forces a refit of the shipped model rather than reusing
`data/processed/model_global.json`.

Requires numpy, scipy, pandas, matplotlib, openpyxl. No network access is needed
after the two fetch steps.
