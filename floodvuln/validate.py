"""Validation harness: the benchmark programme the specification promises.

Deterministic and probabilistic forecasts are scored on the same footing.
A deterministic curve is treated as a degenerate forecast, for which the CRPS
collapses to the absolute error, so the comparison is fair rather than rigged
in favour of the probabilistic model.

Protocols implemented:

    hold_out_event    exclude a named flood event, predict its claims
    leave_region_out  train on all other states, predict a held-out state
    learning_curve    n = 0, 5, 10, ... local records in the held-out region
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import model as M


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------
def point_metrics(y: np.ndarray, yhat: np.ndarray) -> dict:
    e = yhat - y
    return {
        "n": int(len(y)),
        "MAE": float(np.mean(np.abs(e))),
        "RMSE": float(np.sqrt(np.mean(e ** 2))),
        "bias": float(np.mean(e)),
        "mean_obs": float(np.mean(y)),
        "mean_pred": float(np.mean(yhat)),
    }


def calibration_slope(y: np.ndarray, yhat: np.ndarray, bins: int = 20) -> float:
    """Slope of observed on predicted across prediction bins. 1.0 is perfect."""
    q = np.quantile(yhat, np.linspace(0, 1, bins + 1))
    q[-1] += 1e-9
    idx = np.clip(np.searchsorted(q, yhat, side="right") - 1, 0, bins - 1)
    px, py = [], []
    for b in range(bins):
        m = idx == b
        if m.sum() >= 30:
            px.append(yhat[m].mean())
            py.append(y[m].mean())
    if len(px) < 3:
        return float("nan")
    px, py = np.array(px), np.array(py)
    A = np.vstack([np.ones_like(px), px]).T
    coef, *_ = np.linalg.lstsq(A, py, rcond=None)
    return float(coef[1])


def prob_metrics(y, p0, p1c, mu, phi, chunk: int = 20000) -> dict:
    """CRPS, PIT uniformity and interval coverage for a ZOIB forecast."""
    y = np.asarray(y, float)
    n = len(y)
    crps_sum = 0.0
    pits = np.empty(n)
    rng = np.random.default_rng(11)
    for s in range(0, n, chunk):
        e = slice(s, min(s + chunk, n))
        crps_sum += float(np.sum(M.crps(y[e], p0[e], p1c[e], mu[e], phi[e])))
        pits[e] = M.pit(y[e], p0[e], p1c[e], mu[e], phi[e], rng)

    lo = M.quantile(np.full(n, 0.10), p0, p1c, mu, phi)
    hi = M.quantile(np.full(n, 0.90), p0, p1c, mu, phi)
    cov = float(np.mean((y >= lo - 1e-12) & (y <= hi + 1e-12)))

    grid = np.linspace(0, 1, 101)
    emp = np.searchsorted(np.sort(pits), grid) / n
    ks = float(np.max(np.abs(emp - grid)))

    mean, _ = M.moments(p0, p1c, mu, phi)
    return {
        "CRPS": crps_sum / n,
        "PIT_KS": ks,
        "coverage_80": cov,
        "sharpness_p10_p90": float(np.mean(hi - lo)),
        "calibration_slope": calibration_slope(y, mean),
    }


# --------------------------------------------------------------------------
# forecast wrappers so every candidate is scored identically
# --------------------------------------------------------------------------
@dataclass
class Forecast:
    name: str
    kind: str            # 'deterministic' | 'probabilistic'
    mean: np.ndarray
    params: tuple | None = None

    def score(self, y: np.ndarray) -> dict:
        out = {"model": self.name, "kind": self.kind}
        out.update(point_metrics(y, self.mean))
        if self.kind == "probabilistic" and self.params is not None:
            out.update(prob_metrics(y, *self.params))
        else:
            out["CRPS"] = float(np.mean(np.abs(self.mean - y)))
            out["PIT_KS"] = float("nan")
            out["coverage_80"] = float("nan")
            out["sharpness_p10_p90"] = 0.0
            out["calibration_slope"] = calibration_slope(y, self.mean)
        return out


def deterministic_from_curve(f, depth: np.ndarray, name: str) -> Forecast:
    return Forecast(name, "deterministic", np.clip(f(depth), 0.0, 1.0))


def probabilistic(hv, depth, archetype_key=None, local_key=None,
                  level="auto", name="FloodVuln", offsets=None) -> Forecast:
    if offsets is None:
        o = hv.offsets_for(archetype_key, local_key, level)
    else:
        o = offsets
    p0, p1c, mu, phi = M.predict_params(hv.theta, depth, o)
    mean, _ = M.moments(p0, p1c, mu, phi)
    return Forecast(name, "probabilistic", mean, (p0, p1c, mu, phi))


def probabilistic_by_group(hv, depth, akeys, lkeys=None, level="auto",
                           name="FloodVuln") -> Forecast:
    """Vectorised prediction where each row carries its own archetype/region."""
    depth = np.asarray(depth, float)
    p0 = np.empty_like(depth); p1c = np.empty_like(depth)
    mu = np.empty_like(depth); phi = np.empty_like(depth)
    akeys = np.asarray(akeys)
    lk = None if lkeys is None else np.asarray(lkeys)
    combo = akeys if lk is None else np.char.add(np.char.add(akeys.astype(str), "|"),
                                                 lk.astype(str))
    for k in np.unique(combo):
        m = combo == k
        a = k.split("|")[0] if lk is not None else k
        l = k.split("|")[1] if lk is not None else None
        o = hv.offsets_for(a, l, level)
        a0, a1, a2, a3 = M.predict_params(hv.theta, depth[m], o)
        p0[m], p1c[m], mu[m], phi[m] = a0, a1, a2, a3
    mean, _ = M.moments(p0, p1c, mu, phi)
    return Forecast(name, "probabilistic", mean, (p0, p1c, mu, phi))


def fit_deterministic_curve(depth: np.ndarray, dr: np.ndarray, bin_width: float = 0.10):
    """Conventional practice baseline: one monotone mean curve, no distribution.

    Fitted by least squares on binned means, which is what a depth-damage curve
    derived from claims data conventionally is.
    """
    lo, hi = -2.0, 8.0
    idx = np.clip(((depth - lo) / bin_width).astype(int), 0,
                  int((hi - lo) / bin_width) - 1)
    n = np.bincount(idx, minlength=int((hi - lo) / bin_width))
    s = np.bincount(idx, weights=dr, minlength=len(n))
    centres = lo + (np.arange(len(n)) + 0.5) * bin_width
    ok = n >= 30
    x, y, w = centres[ok], (s[ok] / n[ok]), n[ok]

    # monotone least squares on the same ramp basis, so the comparison isolates
    # the distributional assumption rather than the functional form
    from scipy.optimize import minimize
    B = M.ramps(x)

    def obj(p):
        pred = np.clip(p[0] + B @ np.logaddexp(0.0, p[1:]), 0.0, 1.0)
        return float(np.sum(w * (pred - y) ** 2))

    r = minimize(obj, np.concatenate([[0.05], np.full(M.N_RAMP, -2.0)]),
                 method="L-BFGS-B", options={"maxiter": 800})
    p = r.x

    def f(d):
        Bd = M.ramps(np.asarray(d, float))
        return np.clip(p[0] + Bd @ np.logaddexp(0.0, p[1:]), 0.0, 1.0)

    return f


# --------------------------------------------------------------------------
# learning curve
# --------------------------------------------------------------------------
def learning_curve(hv, train_local: pd.DataFrame, test: pd.DataFrame,
                   archetype_key: str, sizes=(0, 5, 10, 25, 50, 100, 250, 500, 1000, 2500),
                   repeats: int = 12, seed: int = 3, local_only: bool = True) -> pd.DataFrame:
    """Error against the number of local records used to update the prior.

    At each size the local sample is redrawn `repeats` times, so the curve
    carries a spread rather than a single lucky draw. `local_only` additionally
    fits an unpooled local curve on the same sample, which is the comparison
    that shows why pooling is needed at small n.
    """
    rng = np.random.default_rng(seed)
    yt = test["damage_ratio"].to_numpy()
    dt = test["depth_m"].to_numpy()
    rows = []

    base = hv.archetypes[archetype_key].offsets if archetype_key in hv.archetypes else np.zeros(4)

    for n in sizes:
        for rep in range(repeats if n > 0 else 1):
            if n == 0:
                off = base
            else:
                take = rng.choice(len(train_local), size=min(n, len(train_local)), replace=False)
                s = train_local.iloc[take]
                off = base + hv.update_local(s["depth_m"].to_numpy(),
                                             s["damage_ratio"].to_numpy(),
                                             archetype_key)
            f = probabilistic(hv, dt, offsets=off, name=f"pooled_n{n}")
            r = f.score(yt); r.update({"n_local": n, "rep": rep, "method": "hierarchical"})
            rows.append(r)

            if local_only and n >= 5:
                take = rng.choice(len(train_local), size=min(n, len(train_local)), replace=False)
                s = train_local.iloc[take]
                try:
                    cells = M.make_cells(s["depth_m"].to_numpy(), s["damage_ratio"].to_numpy())
                    g = M.fit_global(cells, maxiter=300)
                    p = M.predict_params(g["theta"], dt)
                    mean, _ = M.moments(*p)
                    fo = Forecast(f"local_only_n{n}", "probabilistic", mean, p)
                    r2 = fo.score(yt)
                    r2.update({"n_local": n, "rep": rep, "method": "local_only"})
                    rows.append(r2)
                except Exception:  # noqa: BLE001 - unpooled fits genuinely fail at small n
                    rows.append({"model": f"local_only_n{n}", "kind": "probabilistic",
                                 "n_local": n, "rep": rep, "method": "local_only",
                                 "MAE": np.nan, "CRPS": np.nan})
    return pd.DataFrame(rows)
