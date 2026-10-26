"""Property tests for the parts of the engine that must never silently break."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from floodvuln import harmonize, model as M, taxonomy  # noqa: E402

FAIL = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  -- ' + detail) if detail and not ok else ''}")
    if not ok:
        FAIL.append(name)


# --------------------------------------------------------------------------
def test_monotone_mean():
    rng = np.random.default_rng(0)
    d = np.linspace(-2, 8, 500)
    worst = 0.0
    for _ in range(60):
        th = M.init_theta() + rng.normal(0, 1.2, M.N_PARAM)
        p0, p1c, mu, phi = M.predict_params(th, d)
        mean, _ = M.moments(p0, p1c, mu, phi)
        worst = min(worst, float(np.min(np.diff(mean))))
    check("expected damage is non-decreasing in depth for any parameters",
          worst >= -1e-10, f"worst decrement {worst:.2e}")


def test_p0_decreasing_p1_increasing():
    rng = np.random.default_rng(1)
    d = np.linspace(-2, 8, 400)
    ok = True
    for _ in range(40):
        th = M.init_theta() + rng.normal(0, 1.2, M.N_PARAM)
        p0, p1c, _, _ = M.predict_params(th, d)
        ok &= bool(np.all(np.diff(p0) <= 1e-12)) and bool(np.all(np.diff(p1c) >= -1e-12))
    check("P(no damage) falls and P(total loss | damage) rises with depth", ok)


def test_cdf_and_quantile_consistent():
    rng = np.random.default_rng(2)
    th = M.init_theta()
    d = rng.uniform(-1, 5, 200)
    p0, p1c, mu, phi = M.predict_params(th, d)
    qs = np.array([0.05, 0.25, 0.5, 0.75, 0.95])
    worst = 0.0
    for q in qs:
        x = M.quantile(np.full(len(d), q), p0, p1c, mu, phi)
        interior = (x > 1e-6) & (x < 1 - 1e-6)
        if interior.sum():
            back = M.cdf(x[interior], p0[interior], p1c[interior], mu[interior], phi[interior])
            worst = max(worst, float(np.max(np.abs(back - q))))
    check("quantile inverts the CDF on the interior", worst < 1e-6, f"max err {worst:.2e}")


def test_moments_match_simulation():
    rng = np.random.default_rng(3)
    th = M.init_theta()
    d = np.array([0.0, 0.5, 1.5, 3.0])
    p0, p1c, mu, phi = M.predict_params(th, d)
    mean, var = M.moments(p0, p1c, mu, phi)
    n = 400000
    worst_m = worst_v = 0.0
    for i in range(len(d)):
        u = rng.random(n)
        y = np.where(u < p0[i], 0.0, np.nan)
        u2 = rng.random(n)
        y = np.where(np.isnan(y) & (u2 < p1c[i]), 1.0, y)
        need = np.isnan(y)
        y[need] = rng.beta(mu[i] * phi[i], (1 - mu[i]) * phi[i], need.sum())
        worst_m = max(worst_m, abs(y.mean() - mean[i]))
        worst_v = max(worst_v, abs(y.var() - var[i]))
    check("closed-form mean matches simulation", worst_m < 3e-3, f"{worst_m:.4f}")
    check("closed-form variance matches simulation", worst_v < 3e-3, f"{worst_v:.4f}")


def test_crps_degenerate_equals_abs_error():
    """A point forecast scored by CRPS must reduce to the absolute error."""
    y = np.array([0.2, 0.6, 0.9])
    grid = np.linspace(0, 1, 4001)
    for target in (0.35, 0.7):
        F = (grid >= target).astype(float)
        crps = M._trapz((F[None, :] - (grid[None, :] >= y[:, None]).astype(float)) ** 2,
                            grid, axis=1)
        check(f"CRPS of a point forecast at {target} equals |error|",
              float(np.max(np.abs(crps - np.abs(y - target)))) < 1e-3)


def test_cells_are_sufficient():
    """Cell aggregation must give the same likelihood as the raw observations."""
    rng = np.random.default_rng(4)
    n = 40000
    d = rng.uniform(-1, 4, n)
    th = M.init_theta()
    p0, p1c, mu, phi = M.predict_params(th, d)
    u = rng.random(n)
    y = np.where(u < p0, 0.0, np.nan)
    y = np.where(np.isnan(y) & (rng.random(n) < p1c), 1.0, y)
    need = np.isnan(y)
    y[need] = rng.beta(mu[need] * phi[need], (1 - mu[need]) * phi[need])

    coarse = M.neg_loglik(th, M.make_cells(d, y, bin_width=0.50))
    fine = M.neg_loglik(th, M.make_cells(d, y, bin_width=0.02))
    rel = abs(coarse - fine) / abs(fine)
    check("binned likelihood is stable across bin widths", rel < 5e-3, f"rel diff {rel:.2e}")


def test_depth_harmonisation():
    df = pd.DataFrame({
        "waterDepth": [1, 3, 12, 24, 36, 99, 0, -2, 500],
        "buildingDamageAmount": [1000] * 9,
        "buildingPropertyValue": [100000] * 9,
        "buildingReplacementCost": [120000] * 9,
    })
    r = harmonize.resolve_depth(df)
    got = r["depth_m"].to_numpy()
    check("1 ft reads as feet", abs(got[0] - 0.3048) < 1e-9)
    check("3 ft reads as feet", abs(got[1] - 3 * 0.3048) < 1e-9)
    check("24 reads as inches -> 2 ft", abs(got[3] - 2 * 0.3048) < 1e-9)
    check("36 reads as inches -> 3 ft", abs(got[4] - 3 * 0.3048) < 1e-9)
    check("sentinel 99 is dropped", np.isnan(got[5]))
    check("implausible 500 is dropped", np.isnan(got[8]))
    check("12 is flagged ambiguous", bool(r["depth_ambiguous"].iloc[2]))


def test_damage_basis():
    df = pd.DataFrame({
        "buildingDamageAmount": [50000, 50000, 200000],
        "buildingPropertyValue": [100000, np.nan, 100000],
        "buildingReplacementCost": [np.nan, 100000, 100000],
    })
    r = harmonize.resolve_damage(df, acv_to_rc=0.8)
    check("ACV denominator preferred", abs(r["damage_ratio"].iloc[0] - 0.5) < 1e-9)
    check("replacement cost converted when ACV absent",
          abs(r["damage_ratio"].iloc[1] - 50000 / 80000) < 1e-9)
    check("damage above value clips to 1 and flags",
          r["damage_ratio"].iloc[2] == 1.0 and bool(r["damage_exceeds_value"].iloc[2]))


def test_taxonomy_records_assumptions():
    a = taxonomy.from_nfip(1, 1, 1, None, False, False, True, state="TX")
    check("archetype id built", a.id == "US.TX.RES.SF.WOOD.1.SLAB.CONV", a.id)
    check("construction is recorded as assumed", "construction" in a.assumed)
    b = taxonomy.from_nfip(1, 1, 0, None, False, False, None)
    check("undocumented foundation code 0 becomes UNK and is flagged",
          b.foundation == "UNK" and "foundation" in b.assumed)
    check("backoff path is ordered most to least specific",
          a.parents() == ["RES.SF.1.SLAB", "RES.SF.1", "RES.SF", "RES"])


if __name__ == "__main__":
    for fn in [test_monotone_mean, test_p0_decreasing_p1_increasing,
               test_cdf_and_quantile_consistent, test_moments_match_simulation,
               test_crps_degenerate_equals_abs_error, test_cells_are_sufficient,
               test_depth_harmonisation, test_damage_basis,
               test_taxonomy_records_assumptions]:
        fn()
    print()
    if FAIL:
        print(f"{len(FAIL)} FAILED: {FAIL}")
        sys.exit(1)
    print("all checks passed")
