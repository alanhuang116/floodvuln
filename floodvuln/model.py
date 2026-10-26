"""Core vulnerability model: a monotone zero-and-one-inflated beta regression.

    D | depth, archetype  ~  ZOIB(p0, p1, mu, phi)

    P(D = 0)            = p0
    P(D = 1)            = (1 - p0) * p1c
    D | 0 < D < 1       ~ Beta(mu * phi, (1 - mu) * phi)

Three design commitments follow the product specification:

*Physical plausibility.* Expected damage must not fall as inundation deepens.
Each linear predictor is an intercept plus a non-negatively weighted sum of
logistic ramps in depth, so monotonicity holds by construction rather than by
inspection: `mu` and `p1c` increase in depth, `p0` decreases.

*Exact aggregation.* The ZOIB log-likelihood separates into a categorical part
over {0, (0,1), 1} and a beta part over the interior. The beta density depends
on the data only through n, sum(log x) and sum(log(1-x)), so binning by depth
gives *sufficient statistics*, not an approximation, up to the variation of
`mu` inside a bin. Fitting 1.3 million claims therefore costs the same as
fitting a few thousand cells.

*Separated uncertainty.* Aleatory spread is the ZOIB itself. Epistemic spread
comes from a Laplace approximation at the mode, sampled and mixed, so the two
can be reported apart as the specification requires.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize
from scipy.special import betaln, expit, gammaln, logit  # noqa: F401
from scipy.stats import beta as beta_dist

# numpy renamed trapz -> trapezoid in 2.0; support both without pinning a version
_trapz = getattr(np, "trapezoid", None) or np.trapz

# Depth knots for the monotone ramps, metres above the lowest floor.
KNOTS = np.array([-0.60, -0.15, 0.15, 0.45, 0.80, 1.25, 1.90, 2.80, 4.20])
WIDTH = 0.42
N_RAMP = len(KNOTS)


def ramps(depth: np.ndarray) -> np.ndarray:
    """Monotone increasing basis, shape (n, N_RAMP), each column in (0, 1)."""
    d = np.asarray(depth, dtype=float).reshape(-1, 1)
    return expit((d - KNOTS.reshape(1, -1)) / WIDTH)


def _softplus(x: np.ndarray) -> np.ndarray:
    return np.logaddexp(0.0, x)


# parameter block layout ----------------------------------------------------
# [ a_p0, w_p0(N) , a_p1, w_p1(N) , a_mu, w_mu(N) , log_phi0, phi_slope ]
P_BLOCK = 1 + N_RAMP
N_PARAM = 3 * P_BLOCK + 2


def unpack(theta: np.ndarray):
    i = 0
    a_p0, w_p0 = theta[i], theta[i + 1:i + 1 + N_RAMP]; i += P_BLOCK
    a_p1, w_p1 = theta[i], theta[i + 1:i + 1 + N_RAMP]; i += P_BLOCK
    a_mu, w_mu = theta[i], theta[i + 1:i + 1 + N_RAMP]; i += P_BLOCK
    log_phi0, phi_slope = theta[i], theta[i + 1]
    return a_p0, w_p0, a_p1, w_p1, a_mu, w_mu, log_phi0, phi_slope


def predict_params(theta: np.ndarray, depth: np.ndarray,
                   offsets: np.ndarray | None = None):
    """Return (p0, p1c, mu, phi) at the given depths.

    `offsets` is [d_p0, d_p1, d_mu, d_logphi] added to the linear predictors:
    this is where a group's partial-pooling shift enters.

    An optional fifth element is a *shape* offset: it scales the depth response
    of the mean by exp(o[4]), so a region whose damage rises faster with depth
    than the national average can be represented. Validation showed that regional
    variation is substantially in the slope of the response rather than its
    level, and a level-only offset cannot express that: it compromises by
    over-predicting in shallow water and under-predicting in deep. Because the
    multiplier is strictly positive and the ramp weights remain non-negative,
    monotonicity is preserved exactly as before. A length-4 offset behaves as
    it always did.
    """
    a_p0, w_p0, a_p1, w_p1, a_mu, w_mu, log_phi0, phi_slope = unpack(theta)
    B = ramps(depth)
    o = np.zeros(5) if offsets is None else np.asarray(offsets, dtype=float)
    if len(o) < 5:
        o = np.concatenate([o, np.zeros(5 - len(o))])
    shape = np.exp(np.clip(o[4], -1.5, 1.5))

    eta_p0 = a_p0 - B @ _softplus(w_p0) + o[0]        # decreasing in depth
    eta_p1 = a_p1 + B @ _softplus(w_p1) + o[1]        # increasing
    eta_mu = a_mu + shape * (B @ _softplus(w_mu)) + o[2]   # increasing
    log_phi = log_phi0 + phi_slope * np.clip(depth, -2, 8) + o[3]

    p0 = np.clip(expit(eta_p0), 1e-6, 1 - 1e-6)
    p1c = np.clip(expit(eta_p1), 1e-6, 1 - 1e-6)
    mu = np.clip(expit(eta_mu), 1e-4, 1 - 1e-4)
    phi = np.clip(np.exp(log_phi), 0.6, 400.0)
    return p0, p1c, mu, phi


@dataclass
class Cells:
    """Sufficient statistics for one (group, depth-bin) cell."""

    depth: np.ndarray        # mean depth in the cell, metres
    n0: np.ndarray           # count of D == 0
    n1: np.ndarray           # count of D == 1
    nmid: np.ndarray         # count of 0 < D < 1
    slog: np.ndarray         # sum log(D) over interior points
    slog1m: np.ndarray       # sum log(1 - D) over interior points
    group: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=int))

    def __len__(self) -> int:
        return len(self.depth)

    @property
    def n(self) -> np.ndarray:
        return self.n0 + self.n1 + self.nmid

    def subset(self, mask) -> "Cells":
        return Cells(self.depth[mask], self.n0[mask], self.n1[mask], self.nmid[mask],
                     self.slog[mask], self.slog1m[mask],
                     self.group[mask] if len(self.group) else self.group)


EPS = 1e-9


def make_cells(depth: np.ndarray, dr: np.ndarray, group: np.ndarray | None = None,
               bin_width: float = 0.10, lo: float = -2.0, hi: float = 8.0,
               eps: float = 1e-4) -> Cells:
    """Aggregate observations into sufficient statistics.

    Damage ratios are snapped: values <= eps count as exact zeros and values
    >= 1 - eps as exact ones. Interior values are kept away from the boundary
    so that log(x) and log(1-x) remain finite.
    """
    depth = np.asarray(depth, dtype=float)
    dr = np.asarray(dr, dtype=float)
    ok = np.isfinite(depth) & np.isfinite(dr) & (depth >= lo) & (depth <= hi)
    depth, dr = depth[ok], np.clip(dr[ok], 0.0, 1.0)
    g = (np.zeros(len(depth), dtype=int) if group is None
         else np.asarray(group)[ok].astype(int))

    idx = np.clip(((depth - lo) / bin_width).astype(int), 0, int((hi - lo) / bin_width) - 1)
    key = g.astype(np.int64) * 10_000 + idx
    uniq, inv = np.unique(key, return_inverse=True)
    m = len(uniq)

    is0 = dr <= eps
    is1 = dr >= 1 - eps
    ismid = ~is0 & ~is1
    xi = np.clip(dr, eps, 1 - eps)

    def agg(v):
        return np.bincount(inv, weights=v, minlength=m)

    n0 = agg(is0.astype(float))
    n1 = agg(is1.astype(float))
    nmid = agg(ismid.astype(float))
    slog = agg(np.where(ismid, np.log(xi), 0.0))
    slog1m = agg(np.where(ismid, np.log1p(-xi), 0.0))
    dmean = agg(depth) / np.maximum(agg(np.ones_like(depth)), EPS)
    gg = (uniq // 10_000).astype(int)
    return Cells(dmean, n0, n1, nmid, slog, slog1m, gg)


def neg_loglik(theta: np.ndarray, cells: Cells, offsets: np.ndarray | None = None,
               ridge: float = 1e-4) -> float:
    p0, p1c, mu, phi = predict_params(theta, cells.depth, offsets)
    npos = cells.n1 + cells.nmid

    ll = cells.n0 * np.log(p0) + npos * np.log1p(-p0)
    ll += cells.n1 * np.log(p1c) + cells.nmid * np.log1p(-p1c)

    a = mu * phi
    b = (1.0 - mu) * phi
    ll += (a - 1.0) * cells.slog + (b - 1.0) * cells.slog1m - cells.nmid * betaln(a, b)

    val = -float(np.sum(ll)) + ridge * float(np.sum(theta ** 2))
    return val if np.isfinite(val) else 1e18


def init_theta() -> np.ndarray:
    t = np.zeros(N_PARAM)
    a_p0 = 0.0
    t[0] = a_p0
    t[1:1 + N_RAMP] = -1.0                       # softplus(-1) ~ 0.31 per ramp
    t[P_BLOCK] = -3.0                            # p1c low at shallow depth
    t[P_BLOCK + 1:P_BLOCK + 1 + N_RAMP] = -2.0
    t[2 * P_BLOCK] = -1.8                        # mu low at shallow depth
    t[2 * P_BLOCK + 1:2 * P_BLOCK + 1 + N_RAMP] = -1.5
    t[3 * P_BLOCK] = np.log(4.0)
    t[3 * P_BLOCK + 1] = 0.0
    return t


def fit_global(cells: Cells, theta0: np.ndarray | None = None,
               ridge: float = 1e-4, maxiter: int = 2000) -> dict:
    theta0 = init_theta() if theta0 is None else theta0
    res = minimize(neg_loglik, theta0, args=(cells, None, ridge),
                   method="L-BFGS-B",
                   options={"maxiter": maxiter, "maxfun": 200_000, "ftol": 1e-12})
    return {"theta": res.x, "nll": float(res.fun), "success": bool(res.success),
            "message": str(res.message), "n_obs": float(cells.n.sum())}


def fit_offsets(cells: Cells, theta: np.ndarray, tau: np.ndarray | None = None,
                maxiter: int = 400) -> np.ndarray:
    """Fit the 4 group offsets with a Gaussian shrinkage prior of scale `tau`.

    tau = None means an unpenalised fit (used once, to estimate tau itself).
    """
    tau = None if tau is None else np.asarray(tau, dtype=float)

    def obj(o):
        v = neg_loglik(theta, cells, o, ridge=0.0)
        if tau is not None:
            v += 0.5 * float(np.sum((o / np.maximum(tau, 1e-6)) ** 2))
        return v

    res = minimize(obj, np.zeros(4), method="L-BFGS-B",
                   options={"maxiter": maxiter, "ftol": 1e-11})
    return res.x


# --------------------------------------------------------------------------
# predictive distribution
# --------------------------------------------------------------------------
GRID = np.linspace(0.0, 1.0, 501)


def cdf(x, p0, p1c, mu, phi):
    """CDF of the ZOIB at x in [0, 1]."""
    x = np.asarray(x, dtype=float)
    p1 = (1.0 - p0) * p1c
    mid = (1.0 - p0) * (1.0 - p1c)
    inner = beta_dist.cdf(np.clip(x, 0.0, 1.0), mu * phi, (1.0 - mu) * phi)
    out = p0 + mid * inner
    out = np.where(x >= 1.0, 1.0, out)
    out = np.where(x < 0.0, 0.0, out)
    return np.clip(out, 0.0, 1.0)


def quantile(q, p0, p1c, mu, phi):
    p1 = (1.0 - p0) * p1c
    mid = (1.0 - p0) * (1.0 - p1c)
    q = np.asarray(q, dtype=float)
    out = np.where(q <= p0, 0.0, np.nan)
    upper = 1.0 - p1
    out = np.where(q >= upper, 1.0, out)
    inner_q = np.clip((q - p0) / np.maximum(mid, 1e-12), 0.0, 1.0)
    inner = beta_dist.ppf(inner_q, mu * phi, (1.0 - mu) * phi)
    return np.where(np.isnan(out), inner, out)


def moments(p0, p1c, mu, phi):
    p1 = (1.0 - p0) * p1c
    mid = (1.0 - p0) * (1.0 - p1c)
    mean = p1 + mid * mu
    var_beta = mu * (1 - mu) / (phi + 1.0)
    ex2 = p1 + mid * (var_beta + mu ** 2)
    return mean, np.maximum(ex2 - mean ** 2, 0.0)


def prob_exceed(t, p0, p1c, mu, phi):
    return 1.0 - cdf(t, p0, p1c, mu, phi)


def crps(y, p0, p1c, mu, phi, grid: np.ndarray = GRID) -> np.ndarray:
    """Continuous ranked probability score, integrated on [0, 1].

    Vectorised over observations: y is (n,), the parameters are (n,).
    """
    y = np.asarray(y, dtype=float).reshape(-1, 1)
    g = grid.reshape(1, -1)
    F = cdf(np.broadcast_to(g, (len(y), len(grid))),
            np.asarray(p0).reshape(-1, 1), np.asarray(p1c).reshape(-1, 1),
            np.asarray(mu).reshape(-1, 1), np.asarray(phi).reshape(-1, 1))
    H = (g >= y).astype(float)
    return _trapz((F - H) ** 2, grid, axis=1)


def pit(y, p0, p1c, mu, phi, rng: np.random.Generator | None = None) -> np.ndarray:
    """Randomised PIT, which is uniform under a correctly calibrated forecast.

    Randomisation is required because the ZOIB has atoms at 0 and 1; without it
    the PIT histogram is spuriously spiked at both ends.
    """
    rng = np.random.default_rng(0) if rng is None else rng
    y = np.asarray(y, dtype=float)
    lo = cdf(y - 1e-12, p0, p1c, mu, phi)
    hi = cdf(y, p0, p1c, mu, phi)
    lo = np.where(y <= 0.0, 0.0, lo)
    hi = np.where(y >= 1.0, 1.0, hi)
    return lo + rng.random(len(y)) * np.maximum(hi - lo, 0.0)
