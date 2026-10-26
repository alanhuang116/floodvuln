"""Attach Laplace covariances to every fitted unit in the hierarchy.

Epistemic uncertainty at a location is dominated not by uncertainty in the
global parameter vector -- with 1.86 million records that is negligible -- but
by uncertainty in the *group offset*, which is exactly where evidence is thin.
The posterior covariance of an offset under the shrinkage prior is

    Cov = ( H_local + diag(1 / tau^2) ) ^ -1

so a unit with one observation inherits the prior variance tau^2 and a unit
with tens of thousands collapses to the likelihood. This is what makes the
confidence score and the epistemic band respond to evidence rather than decorate
the response.
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from floodvuln import model as M                       # noqa: E402
from floodvuln.calibrate import HierarchicalVulnerability, numerical_hessian, safe_cov  # noqa: E402

PROC = os.path.join(HERE, "..", "data", "processed")


def offset_cov(theta, cells, base, offset, tau):
    f = lambda o: M.neg_loglik(theta, cells, base + o, 0.0)  # noqa: E731
    H = numerical_hessian(f, offset, eps=1.5e-3)
    H = H + np.diag(1.0 / np.maximum(np.asarray(tau, float), 1e-6) ** 2)
    return safe_cov(H)


def main() -> None:
    df = pd.read_csv(os.path.join(PROC, "calibration.csv"), low_memory=False,
                     usecols=["group_key", "state", "depth_m", "damage_ratio"])
    hv = HierarchicalVulnerability.load(os.path.join(PROC, "model_global.json"))
    print(f"units: {len(hv.archetypes)} archetypes, {len(hv.locals_)} locals")

    depth = df["depth_m"].to_numpy()
    dr = df["damage_ratio"].to_numpy()
    gk = df["group_key"].to_numpy().astype(str)
    st = df["state"].to_numpy().astype(str)
    combo = np.char.add(np.char.add(gk, "@"), st)

    t0 = time.time()
    out = {"archetypes": {}, "locals": {}}
    for k, lv in hv.archetypes.items():
        m = gk == k
        if m.sum() == 0:
            continue
        c = M.make_cells(depth[m], dr[m])
        out["archetypes"][k] = offset_cov(hv.theta, c, np.zeros(4), lv.offsets, hv.tau_arch)
    print(f"archetype covariances in {time.time() - t0:.0f}s")

    t0 = time.time()
    for i, (k, lv) in enumerate(hv.locals_.items()):
        m = combo == k
        if m.sum() == 0:
            continue
        a = k.split("@")[0]
        base = hv.archetypes[a].offsets if a in hv.archetypes else np.zeros(4)
        c = M.make_cells(depth[m], dr[m])
        out["locals"][k] = offset_cov(hv.theta, c, base, lv.offsets, hv.tau_local)
        if (i + 1) % 1000 == 0:
            print(f"  {i + 1}/{len(hv.locals_)}  ({time.time() - t0:.0f}s)", flush=True)
    print(f"local covariances in {time.time() - t0:.0f}s")

    np.savez_compressed(
        os.path.join(PROC, "offset_cov.npz"),
        arch_keys=np.array(list(out["archetypes"])),
        arch_cov=np.array([out["archetypes"][k] for k in out["archetypes"]]),
        local_keys=np.array(list(out["locals"])),
        local_cov=np.array([out["locals"][k] for k in out["locals"]]),
    )

    # sanity: the epistemic sd of the predicted mean must fall as n rises
    print("\n=== epistemic sd of the mean at 0.61 m, by local sample size ===")
    rows = []
    for k, lv in hv.locals_.items():
        if k not in out["locals"] or not k.startswith("RES.SF.1.SLAB@"):
            continue
        a = k.split("@")[0]
        base = hv.archetypes[a].offsets
        cov = out["locals"][k]
        L = np.linalg.cholesky(cov + 1e-12 * np.eye(4))
        z = np.random.default_rng(0).standard_normal((400, 4))
        offs = (base + lv.offsets)[None, :] + z @ L.T
        means = []
        for o in offs:
            p = M.predict_params(hv.theta, np.array([0.61]), o)
            means.append(float(M.moments(*p)[0][0]))
        rows.append((k.split("@")[1], lv.n_obs, float(np.std(means))))
    rows.sort(key=lambda r: -r[1])
    for r in rows[:4] + rows[-4:]:
        print(f"  {r[0]:>4}  n={r[1]:>8.0f}   epistemic sd = {r[2]:.4f}")


if __name__ == "__main__":
    main()
