"""Global-to-local calibration: hierarchical partial pooling over the ZOIB core.

Three nested levels, each a shift of the four linear predictors:

    global          fitted on all admissible evidence
      archetype     sector . occupancy . storeys . foundation
        local       archetype x region (US state here)

A level's offset is fitted under a Gaussian prior N(0, tau^2) whose scale is
estimated across the units at that level by moment matching (empirical Bayes).
The result is the behaviour the specification requires: a handful of local
records barely move the answer, a few hundred move it most of the way, and the
global prior is never discarded, so a region with no evidence still returns a
documented number.

The shrinkage is not imposed as a formula; it falls out of maximising

    log L_local(delta) - 0.5 * || delta / tau ||^2

which for small local samples is dominated by the prior and for large samples by
the likelihood.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import numpy as np

from . import model as M


# --------------------------------------------------------------------------
def numerical_hessian(f, x: np.ndarray, eps: float = 1e-4) -> np.ndarray:
    n = len(x)
    H = np.zeros((n, n))
    f0 = f(x)
    for i in range(n):
        for j in range(i, n):
            xi = x.copy(); xi[i] += eps; xi[j] += eps
            xj = x.copy(); xj[i] += eps; xj[j] -= eps
            xk = x.copy(); xk[i] -= eps; xk[j] += eps
            xl = x.copy(); xl[i] -= eps; xl[j] -= eps
            H[i, j] = H[j, i] = (f(xi) - f(xj) - f(xk) + f(xl)) / (4 * eps * eps)
    return H


def safe_cov(H: np.ndarray, ridge: float = 1e-6) -> np.ndarray:
    """Invert a Hessian into a covariance, projecting to positive definiteness."""
    H = 0.5 * (H + H.T)
    w, V = np.linalg.eigh(H)
    w = np.maximum(w, ridge)
    return (V / w) @ V.T


@dataclass
class Level:
    """One fitted unit at one level of the hierarchy."""

    key: str
    offsets: np.ndarray
    n_obs: float
    cov: np.ndarray | None = None


@dataclass
class HierarchicalVulnerability:
    theta: np.ndarray
    archetypes: dict[str, Level] = field(default_factory=dict)
    locals_: dict[str, Level] = field(default_factory=dict)
    tau_arch: np.ndarray = field(default_factory=lambda: np.full(4, 0.25))
    tau_local: np.ndarray = field(default_factory=lambda: np.full(4, 0.20))
    theta_cov: np.ndarray | None = None
    meta: dict = field(default_factory=dict)

    # ---------------- fitting ----------------
    @staticmethod
    def fit(depth, dr, archetype_key, local_key=None, *,
            min_arch_n: int = 400, min_local_n: int = 150,
            bin_width: float = 0.10, verbose: bool = True,
            tau_arch=None, tau_local=None,
            with_theta_cov: bool = True) -> "HierarchicalVulnerability":
        """Fit the hierarchy.

        `tau_arch` / `tau_local` may be supplied to reuse variance components
        estimated on the full dataset. Inside a cross-validation fold this is
        both faster and more stable: the between-group scale is a property of
        the population, and re-estimating it from a fold that is missing one
        event or one state adds noise without adding information. It is not a
        leakage path, because tau carries no information about the held-out
        records' damage ratios beyond the spread of group means.
        """
        depth = np.asarray(depth, float)
        dr = np.asarray(dr, float)
        akeys = np.asarray(archetype_key)
        lkeys = None if local_key is None else np.asarray(local_key)

        # ---- global ----
        cells_all = M.make_cells(depth, dr, bin_width=bin_width)
        g = M.fit_global(cells_all)
        theta = g["theta"]
        if verbose:
            print(f"[global] n={g['n_obs']:,.0f} cells={len(cells_all)} nll={g['nll']:,.1f}")

        theta_cov = None
        if with_theta_cov:
            obj = lambda t: M.neg_loglik(t, cells_all, None, 0.0)  # noqa: E731
            theta_cov = safe_cov(numerical_hessian(obj, theta, eps=2e-4))

        mv = HierarchicalVulnerability(theta=theta, theta_cov=theta_cov)
        mv.meta = {"n_global": float(g["n_obs"]), "nll_global": g["nll"],
                   "bin_width": bin_width}

        # ---- archetype level ----
        counts: dict[str, float] = {}
        for k in np.unique(akeys):
            counts[k] = float((akeys == k).sum())

        if tau_arch is not None:
            mv.tau_arch = np.asarray(tau_arch, dtype=float)
        else:
            raw: dict[str, np.ndarray] = {}
            var_hat: dict[str, np.ndarray] = {}
            for k in np.unique(akeys):
                m = akeys == k
                c = M.make_cells(depth[m], dr[m], bin_width=bin_width)
                if float(c.n.sum()) < min_arch_n:
                    continue
                d = M.fit_offsets(c, theta, tau=None)
                raw[k] = d
                f = lambda o: M.neg_loglik(theta, c, o, 0.0)  # noqa: E731
                var_hat[k] = np.clip(
                    np.diag(safe_cov(numerical_hessian(f, d, eps=1e-3))), 1e-8, 25.0)
            mv.tau_arch = _moment_tau(raw, var_hat)
        if verbose:
            print(f"[archetype] units={len(counts)}  tau={np.round(mv.tau_arch, 3)}"
                  f"{'  (reused)' if tau_arch is not None else ''}")

        for k in np.unique(akeys):
            m = akeys == k
            c = M.make_cells(depth[m], dr[m], bin_width=bin_width)
            d = M.fit_offsets(c, theta, tau=mv.tau_arch)
            mv.archetypes[k] = Level(k, d, counts.get(k, 0.0))

        # ---- local level ----
        if lkeys is not None:
            combo = np.char.add(np.char.add(akeys.astype(str), "@"), lkeys.astype(str))
            cnt_l = {k: float((combo == k).sum()) for k in np.unique(combo)}

            if tau_local is not None:
                mv.tau_local = np.asarray(tau_local, dtype=float)
            else:
                raw_l, var_l = {}, {}
                from scipy.optimize import minimize
                for k in np.unique(combo):
                    m = combo == k
                    if cnt_l[k] < min_local_n:
                        continue
                    a = k.split("@")[0]
                    base = mv.archetypes[a].offsets if a in mv.archetypes else np.zeros(4)
                    c = M.make_cells(depth[m], dr[m], bin_width=bin_width)
                    f_un = lambda o: M.neg_loglik(theta, c, base + o, 0.0)  # noqa: E731
                    r = minimize(f_un, np.zeros(4), method="L-BFGS-B",
                                 options={"maxiter": 300, "ftol": 1e-11})
                    raw_l[k] = r.x
                    var_l[k] = np.clip(
                        np.diag(safe_cov(numerical_hessian(f_un, r.x, eps=1e-3))), 1e-8, 25.0)
                mv.tau_local = _moment_tau(raw_l, var_l)
            if verbose:
                print(f"[local] units={len(cnt_l)}  tau={np.round(mv.tau_local, 3)}"
                      f"{'  (reused)' if tau_local is not None else ''}")

            for k in np.unique(combo):
                m = combo == k
                a = k.split("@")[0]
                base = mv.archetypes[a].offsets if a in mv.archetypes else np.zeros(4)
                c = M.make_cells(depth[m], dr[m], bin_width=bin_width)
                d = _fit_shifted(theta, c, base, mv.tau_local)
                mv.locals_[k] = Level(k, d, cnt_l.get(k, float(m.sum())))
        return mv

    # ---------------- prediction ----------------
    def offsets_for(self, archetype_key: str | None, local_key: str | None = None,
                    level: str = "auto") -> np.ndarray:
        """Resolve the offset stack for a request.

        level: 'global' | 'archetype' | 'local' | 'auto'
        """
        o = np.zeros(4)
        if level == "global":
            return o
        if archetype_key and archetype_key in self.archetypes:
            o = o + self.archetypes[archetype_key].offsets
        if level in ("local", "auto") and archetype_key and local_key:
            k = f"{archetype_key}@{local_key}"
            if k in self.locals_:
                o = o + self.locals_[k].offsets
        return o

    def params(self, depth, archetype_key=None, local_key=None, level="auto"):
        o = self.offsets_for(archetype_key, local_key, level)
        return M.predict_params(self.theta, np.atleast_1d(depth), o)

    def update_local(self, depth, dr, archetype_key: str, bin_width: float = 0.10):
        """Partial-pooling update from a client's own records.

        This is the G3/G4/G5 path: the returned offset is shrunk toward the
        archetype prior by exactly the weight the sample size earns.
        """
        base = (self.archetypes[archetype_key].offsets
                if archetype_key in self.archetypes else np.zeros(4))
        c = M.make_cells(np.asarray(depth, float), np.asarray(dr, float), bin_width=bin_width)
        return _fit_shifted(self.theta, c, base, self.tau_local)

    # ---------------- io ----------------
    def to_dict(self) -> dict:
        return {
            "theta": self.theta.tolist(),
            "tau_arch": self.tau_arch.tolist(),
            "tau_local": self.tau_local.tolist(),
            "knots": M.KNOTS.tolist(),
            "width": M.WIDTH,
            "archetypes": {k: {"offsets": v.offsets.tolist(), "n": v.n_obs}
                           for k, v in self.archetypes.items()},
            "locals": {k: {"offsets": v.offsets.tolist(), "n": v.n_obs}
                       for k, v in self.locals_.items()},
            "meta": self.meta,
        }

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=1)

    @staticmethod
    def load(path: str) -> "HierarchicalVulnerability":
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
        mv = HierarchicalVulnerability(theta=np.array(d["theta"]))
        mv.tau_arch = np.array(d["tau_arch"])
        mv.tau_local = np.array(d["tau_local"])
        mv.archetypes = {k: Level(k, np.array(v["offsets"]), v["n"])
                         for k, v in d["archetypes"].items()}
        mv.locals_ = {k: Level(k, np.array(v["offsets"]), v["n"])
                      for k, v in d["locals"].items()}
        mv.meta = d.get("meta", {})
        return mv


def _fit_shifted(theta, cells, base, tau):
    from scipy.optimize import minimize

    def obj(o):
        v = M.neg_loglik(theta, cells, base + o, 0.0)
        return v + 0.5 * float(np.sum((o / np.maximum(tau, 1e-6)) ** 2))

    r = minimize(obj, np.zeros(4), method="L-BFGS-B",
                 options={"maxiter": 300, "ftol": 1e-11})
    return r.x


# Ceiling on the between-unit scale, per linear predictor
# [p0, p1, mu, log phi].
#
# The zero and one components are near the boundary of the parameter space in
# claims data: NFIP records carry P(D=0) of only 0.1-2%, because a building that
# was inundated and suffered no damage generally never becomes a claim at all.
# Their logit offsets are therefore weakly identified, and an unconstrained
# moment estimator returns tau of 3-7, which is not evidence of real
# between-group variation but of an unidentified parameter wandering. Left
# uncapped it would switch shrinkage off exactly where shrinkage is most needed.
# The ceiling keeps those components pooled toward the global value while
# leaving the well-identified mean and precision components free.
TAU_CEILING = np.array([0.60, 0.60, 0.50, 0.40])


def _moment_tau(raw: dict, var_hat: dict, floor: float = 0.02) -> np.ndarray:
    """Method-of-moments between-unit scale: Var(estimates) - mean(sampling var)."""
    if not raw:
        return np.full(4, 0.2)
    D = np.vstack([raw[k] for k in raw])
    S = np.vstack([var_hat[k] for k in raw])
    between = D.var(axis=0, ddof=1) if len(D) > 1 else np.full(4, 0.04)
    within = S.mean(axis=0)
    tau2 = np.maximum(between - within, floor ** 2)
    return np.minimum(np.sqrt(tau2), TAU_CEILING)
