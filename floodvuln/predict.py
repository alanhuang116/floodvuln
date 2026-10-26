"""The engine: a request in, a documented damage distribution out.

Implements the calibration ladder G0-G5 over the fitted hierarchy plus the JRC
published prior, and returns the response fields the product specification
defines.

Two things here are deliberately not decorative.

**Epistemic uncertainty is the offset posterior, not the parameter vector.**
With 1.86 million records the global parameter vector is pinned down and its
contribution is under 0.001 in damage-ratio units. What is genuinely uncertain
is the *group offset*, and for a region with no local evidence at all the honest
statement is the shrinkage prior itself: the offset is unknown with variance
tau^2. So an unseen region inherits diag(tau_local^2) rather than pretending the
national curve applies exactly. This is what makes the ladder mean something.

**Confidence is a published function of that epistemic spread**, not a rating.
It answers "how well pinned down is this answer", never "how likely is this
outcome" -- the outcome spread is the aleatory part, and local evidence does not
reduce it.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from . import model as M
from . import evidence as EV
from .taxonomy import Archetype, jrc_lookup

# Depth range over which the calibration data actually supports the curve.
DEFAULT_DOMAIN = (-1.5, 5.0)

LEVELS = ("G0", "G1", "G2", "G3", "G4", "G5")

# Epistemic sd, in damage-ratio units, at which confidence falls to 1/e.
CONF_SCALE = 0.055


@dataclass
class Prediction:
    asset_archetype: str
    effective_depth_m: float
    calibration_level: str
    mean_damage_ratio: float
    median_damage_ratio: float
    p10: float
    p90: float
    p_damage_gt_50pct: float
    p_zero_damage: float
    p_total_loss: float
    sd_total: float
    sd_aleatory: float
    sd_epistemic: float
    evidence_grade: str
    confidence_score: int
    local_sample_size: float
    archetype_sample_size: float
    source_family_count: int
    model_version: str
    evidence_snapshot: str
    warnings: list
    assumed_levels: list

    def to_dict(self) -> dict:
        return asdict(self)


class FloodVulnEngine:
    MODEL_VERSION = "1.0.0"

    def __init__(self, hv, curves=None, snapshot: str = "", domain=DEFAULT_DOMAIN,
                 n_epistemic: int = 240, seed: int = 5, offset_cov: dict | None = None):
        self.hv = hv
        self.curves = EV.load_curves() if curves is None else curves
        self.snapshot = snapshot
        self.domain = domain
        self.rng = np.random.default_rng(seed)
        self.n_epistemic = n_epistemic
        self.offset_cov = offset_cov or {}

    # ---------------- offset resolution ----------------
    def _stack(self, archetype: Archetype, level: str, local_key, local_offsets,
               expert_offsets):
        """Return (offset, offset_cov, n_local, n_arch, n_sources)."""
        gk = archetype.group_key
        arch_lv = self.hv.archetypes.get(gk)
        arch_off = arch_lv.offsets if arch_lv else np.zeros(4)
        n_arch = float(arch_lv.n_obs) if arch_lv else 0.0
        arch_cov = self.offset_cov.get(("arch", gk))
        if arch_cov is None:
            arch_cov = np.diag(np.asarray(self.hv.tau_arch, float) ** 2)

        tau_l2 = np.diag(np.asarray(self.hv.tau_local, float) ** 2)

        if level in ("G1", "G2"):
            # Archetype evidence only. The region is unseen, so the offset that
            # would apply to it is unknown with the between-region prior variance.
            off = arch_off.copy()
            if level == "G2" and expert_offsets is not None:
                off = off + np.asarray(expert_offsets, float)
            cov = arch_cov + tau_l2
            return off, cov, 0.0, n_arch, (3 if level == "G2" else 2)

        # G3-G5: local evidence
        if local_offsets is not None:
            return arch_off + np.asarray(local_offsets, float), arch_cov, 0.0, n_arch, 4
        key = f"{gk}@{local_key}"
        lv = self.hv.locals_.get(key)
        if lv is None:
            return arch_off, arch_cov + tau_l2, 0.0, n_arch, 2
        cov = self.offset_cov.get(("local", key))
        if cov is None:
            cov = tau_l2
        return arch_off + lv.offsets, arch_cov * 0.0 + cov, float(lv.n_obs), n_arch, 4

    # ---------------- main entry ----------------
    def predict(self, depth_m: float, archetype: Archetype, *, level: str = "auto",
                local_key: str | None = None, local_offsets=None,
                expert_offsets=None) -> Prediction:
        warnings: list[str] = []
        d = float(depth_m)
        if level == "auto":
            level = self._auto_level(archetype, local_key)
        if level == "G0":
            return self._jrc_prediction(d, archetype, warnings)

        off, cov, n_loc, n_arch, n_src = self._stack(
            archetype, level, local_key, local_offsets, expert_offsets)

        draws = self._draw_offsets(off, cov, self.n_epistemic)
        means, vars_, comps = [], [], []
        dd = np.array([d])
        for o in draws:
            p0, p1c, mu, phi = M.predict_params(self.hv.theta, dd, o)
            m_, v_ = M.moments(p0, p1c, mu, phi)
            means.append(float(m_[0])); vars_.append(float(v_[0]))
            comps.append((float(p0[0]), float(p1c[0]), float(mu[0]), float(phi[0])))
        means = np.array(means)

        aleatory_var = float(np.mean(vars_))
        epistemic_var = float(np.var(means))
        mean = float(np.mean(means))

        grid = np.linspace(0, 1, 1001)
        F = np.zeros_like(grid)
        for (p0, p1c, mu, phi) in comps:
            F += M.cdf(grid, p0, p1c, mu, phi)
        F /= len(comps)
        med = float(np.interp(0.5, F, grid))
        p10 = float(np.interp(0.10, F, grid))
        p90 = float(np.interp(0.90, F, grid))
        p_gt50 = float(1.0 - np.interp(0.5, grid, F))
        p_zero = float(np.mean([c[0] for c in comps]))
        p_total = float(np.mean([(1 - c[0]) * c[1] for c in comps]))

        if not (self.domain[0] <= d <= self.domain[1]):
            warnings.append("out_of_domain_depth")
        if archetype.assumed:
            warnings.append("assumed_taxonomy_levels")
        warnings.append("p_zero_damage_conditional_on_claim_filed")

        sd_e = float(np.sqrt(epistemic_var))
        grade = self._grade(level, n_loc, n_arch, warnings)
        conf = self._conf(sd_e, warnings)

        return Prediction(
            asset_archetype=archetype.id, effective_depth_m=round(d, 3),
            calibration_level=level,
            mean_damage_ratio=round(mean, 4), median_damage_ratio=round(med, 4),
            p10=round(p10, 4), p90=round(p90, 4),
            p_damage_gt_50pct=round(p_gt50, 4),
            p_zero_damage=round(p_zero, 4), p_total_loss=round(p_total, 4),
            sd_total=round(float(np.sqrt(aleatory_var + epistemic_var)), 4),
            sd_aleatory=round(float(np.sqrt(aleatory_var)), 4),
            sd_epistemic=round(sd_e, 4),
            evidence_grade=grade, confidence_score=conf,
            local_sample_size=n_loc, archetype_sample_size=n_arch,
            source_family_count=n_src,
            model_version=self.MODEL_VERSION, evidence_snapshot=self.snapshot,
            warnings=warnings, assumed_levels=sorted(archetype.assumed))

    def _draw_offsets(self, off, cov, n):
        cov = np.asarray(cov, float)
        try:
            L = np.linalg.cholesky(cov + 1e-12 * np.eye(4))
        except np.linalg.LinAlgError:
            w, V = np.linalg.eigh(cov)
            L = V @ np.diag(np.sqrt(np.maximum(w, 0)))
        z = self.rng.standard_normal((n, 4))
        return off.reshape(1, -1) + z @ L.T

    # ---------------- G0: published global prior ----------------
    def _jrc_prediction(self, d, archetype, warnings):
        cls, cont = jrc_lookup(archetype)
        try:
            f = EV.curve_interpolator(self.curves, cls, cont)
        except KeyError:
            f = EV.curve_interpolator(self.curves, cls, "GLOBAL")
            warnings.append("continent_curve_unavailable_used_global")
        mean = float(np.clip(f(d), 0, 1))
        # The JRC product publishes a mean curve and no distribution. Rather than
        # invent one, the G0 spread is the between-continent spread of the
        # published curves at that depth: a real, citable measure of how little a
        # global prior pins down.
        sel = self.curves[self.curves.damage_class == cls]
        vals = [float(np.interp(d, g.depth_m, g.damage_factor))
                for _, g in sel.groupby("continent") if len(g) > 2]
        sd = float(np.std(vals)) if len(vals) > 2 else 0.25
        warnings.append("global_prior_only_no_local_evidence")
        warnings.append("published_curve_has_no_distribution")
        return Prediction(
            asset_archetype=archetype.id, effective_depth_m=round(float(d), 3),
            calibration_level="G0", mean_damage_ratio=round(mean, 4),
            median_damage_ratio=round(mean, 4),
            p10=round(max(0.0, mean - 1.2816 * sd), 4),
            p90=round(min(1.0, mean + 1.2816 * sd), 4),
            p_damage_gt_50pct=float("nan"), p_zero_damage=float("nan"),
            p_total_loss=float("nan"), sd_total=round(sd, 4),
            sd_aleatory=float("nan"), sd_epistemic=round(sd, 4),
            evidence_grade="D", confidence_score=self._conf(sd, warnings),
            local_sample_size=0.0, archetype_sample_size=0.0, source_family_count=1,
            model_version=self.MODEL_VERSION, evidence_snapshot=self.snapshot,
            warnings=warnings, assumed_levels=sorted(archetype.assumed))

    # ---------------- grading ----------------
    def _auto_level(self, archetype: Archetype, local_key) -> str:
        gk = archetype.group_key
        if local_key and f"{gk}@{local_key}" in self.hv.locals_:
            n = self.hv.locals_[f"{gk}@{local_key}"].n_obs
            return "G4" if n >= 1000 else "G3"
        if gk in self.hv.archetypes:
            return "G1"
        return "G0"

    def _conf(self, sd_epistemic: float, warnings: list) -> int:
        """conf = 100 * exp(-sd_epistemic / 0.055), debited for known weaknesses.

        Tied to a measured quantity so a model-risk function can reproduce it.
        It is a statement about how well the answer is pinned down, not about how
        likely any particular outcome is.
        """
        if not np.isfinite(sd_epistemic):
            return 10
        base = 100.0 * float(np.exp(-sd_epistemic / CONF_SCALE))
        if "out_of_domain_depth" in warnings:
            base -= 15
        if "assumed_taxonomy_levels" in warnings:
            base -= 6
        if "global_prior_only_no_local_evidence" in warnings:
            base = min(base, 30.0)
        return int(np.clip(round(base), 5, 98))

    def _grade(self, level: str, n_local: float, n_arch: float,
               warnings: list) -> str:
        if level == "G0":
            return "D"
        if level in ("G1", "G2"):
            grade = "C" if n_arch >= 5000 else "D"
        elif n_local >= 1000:
            grade = "A"
        elif n_local >= 100:
            grade = "B"
        else:
            grade = "C"
        if "out_of_domain_depth" in warnings and grade == "A":
            grade = "B"
        return grade


def load_offset_cov(path: str) -> dict:
    """Load the covariance archive written by scripts/add_covariances.py."""
    import os
    if not os.path.exists(path):
        return {}
    z = np.load(path, allow_pickle=False)
    out: dict = {}
    for k, c in zip(z["arch_keys"], z["arch_cov"]):
        out[("arch", str(k))] = c
    for k, c in zip(z["local_keys"], z["local_cov"]):
        out[("local", str(k))] = c
    return out
