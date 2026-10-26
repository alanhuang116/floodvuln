/* =================== FITTED MODEL =================== */
/* Parameters below are fitted to 1,861,852 NFIP claims. Nothing here is
   illustrative: theta is the maximum-likelihood monotone ZOIB parameter
   vector, the offsets are hierarchical partial-pooling shifts, and the
   covariances are Laplace posteriors under the shrinkage prior. */
const FV = window.__FV_MODEL;
const NK = FV.knots.length, PB = NK + 1;

function expit(x){ return 1 / (1 + Math.exp(-x)); }
function softplus(x){ return x > 30 ? x : Math.log1p(Math.exp(x)); }

function ramps(d){
  const B = new Array(NK);
  for (let k = 0; k < NK; k++) B[k] = expit((d - FV.knots[k]) / FV.width);
  return B;
}

/* (p0, p1c, mu, phi) at one depth, given a 4-vector offset */
function paramsAt(d, off){
  const t = FV.theta, B = ramps(d);
  let s0 = 0, s1 = 0, sm = 0;
  for (let k = 0; k < NK; k++){
    s0 += B[k] * softplus(t[1 + k]);
    s1 += B[k] * softplus(t[PB + 1 + k]);
    sm += B[k] * softplus(t[2 * PB + 1 + k]);
  }
  const dc = Math.max(-2, Math.min(8, d));
  return {
    p0:  clamp(expit(t[0]        - s0 + off[0]), 1e-6, 1 - 1e-6),
    p1c: clamp(expit(t[PB]       + s1 + off[1]), 1e-6, 1 - 1e-6),
    mu:  clamp(expit(t[2 * PB]   + sm + off[2]), 1e-4, 1 - 1e-4),
    phi: clamp(Math.exp(t[3 * PB] + t[3 * PB + 1] * dc + off[3]), 0.6, 400)
  };
}

function distAt(d, off){
  const P = paramsAt(d, off);
  const p1 = (1 - P.p0) * P.p1c, rest = (1 - P.p0) * (1 - P.p1c);
  const a = P.mu * P.phi, b = (1 - P.mu) * P.phi;
  const q = function(p){
    if (p <= P.p0) return 0;
    if (p >= 1 - p1) return 1;
    return M.ibetaInv((p - P.p0) / rest, a, b);
  };
  const mean = p1 + rest * P.mu;
  const varAleatory = p1 + rest * (P.mu * (1 - P.mu) / (P.phi + 1) + P.mu * P.mu) - mean * mean;
  return {
    p0: P.p0, p1c: P.p1c, p1: p1, rest: rest, m: P.mu, phi: P.phi, a: a, b: b,
    mean: mean, med: q(0.5), p10: q(0.1), p90: q(0.9),
    pgt50: p1 + rest * (1 - M.ibeta(0.5, a, b)),
    sdAleatory: Math.sqrt(Math.max(varAleatory, 0)), q: q
  };
}

/* Epistemic sd of the predicted mean, delta method through the offset posterior.
   This is the component that local evidence actually reduces. */
function epistemicSd(d, off, cov){
  if (!cov) return 0;
  const h = 1e-3, base = distAt(d, off).mean, g = [0, 0, 0, 0];
  for (let i = 0; i < 4; i++){
    const o2 = off.slice(); o2[i] += h;
    g[i] = (distAt(d, o2).mean - base) / h;
  }
  let v = 0;
  for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) v += g[i] * cov[i][j] * g[j];
  return Math.sqrt(Math.max(v, 0));
}

/* =================== ARCHETYPES AND LADDER =================== */
const ARCH = FV.archetypes;
const REGIONS = (function(){
  const set = {};
  Object.keys(FV.locals).forEach(function(k){
    const st = k.split("@")[1];
    set[st] = (set[st] || 0) + FV.locals[k].n;
  });
  return Object.keys(set).sort(function(a, b){ return set[b] - set[a]; });
})();

const LVL = [
  {g:"G0", t:"Published global prior", n:"JRC continental curve", mode:"jrc"},
  {g:"G1", t:"Archetype prior",        n:"US claims, region unseen", mode:"arch"},
  {g:"G4", t:"Region calibrated",      n:"local claims for this region", mode:"local"}
];

function jrcCurve(d){
  const pts = FV.jrc["Residential buildings"]["North AMERICA"];
  if (d <= pts[0][0]) return pts[0][1];
  for (let i = 1; i < pts.length; i++){
    if (d <= pts[i][0]){
      const f = (d - pts[i-1][0]) / (pts[i][0] - pts[i-1][0]);
      return pts[i-1][1] + f * (pts[i][1] - pts[i-1][1]);
    }
  }
  return pts[pts.length - 1][1];
}

/* between-continent spread of the published curves: a citable measure of how
   little a global prior pins down, used instead of inventing a distribution */
function jrcSpread(d){
  const byC = FV.jrc["Residential buildings"], vals = [];
  Object.keys(byC).forEach(function(c){
    const pts = byC[c];
    let v = pts[pts.length-1][1];
    if (d <= pts[0][0]) v = pts[0][1];
    else for (let i = 1; i < pts.length; i++){
      if (d <= pts[i][0]){
        const f = (d - pts[i-1][0]) / (pts[i][0] - pts[i-1][0]);
        v = pts[i-1][1] + f * (pts[i][1] - pts[i-1][1]); break;
      }
    }
    vals.push(v);
  });
  const m = vals.reduce(function(s,v){return s+v;},0) / vals.length;
  return Math.sqrt(vals.reduce(function(s,v){return s+(v-m)*(v-m);},0) / vals.length);
}

/* The engine. Returns the same shape the page already consumes, plus the
   uncertainty decomposition and the real evidence counts. */
function engine(archIdx, depth, levelIdx, region){
  const A = ARCH[archIdx], L = LVL[levelIdx];
  const notes = [], warnings = [];
  const domain = depth < -1.5 || depth > 5.0;

  if (L.mode === "jrc"){
    const mean = clamp(jrcCurve(depth), 0, 1), sd = jrcSpread(depth);
    notes.push("The published curve is a single expected value. It carries no distribution, so the band shown is the spread <em>between continents</em> of the published curves &mdash; a measure of how little a global prior pins down.");
    notes.push("Fitted against 1.86m US claims this curve runs high: see the evidence section.");
    return {jrc:true, mean:mean, med:mean, p10:Math.max(0,mean-1.2816*sd), p90:Math.min(1,mean+1.2816*sd),
      sdEpistemic:sd, sdAleatory:NaN, pgt50:NaN, p0:NaN, p1:NaN, rest:NaN,
      grade:"D", conf:13, nLocal:0, nArch:0, lvl:L, arch:A, notes:notes,
      warnings:["global_prior_only_no_local_evidence","published_curve_has_no_distribution"], domain:domain};
  }

  let off = A.offsets.slice(), cov = A.cov_unseen, nLocal = 0;
  if (L.mode === "local"){
    const key = A.key + "@" + region;
    const lo = FV.locals[key];
    if (lo){
      off = [off[0]+lo.offsets[0], off[1]+lo.offsets[1], off[2]+lo.offsets[2], off[3]+lo.offsets[3]];
      cov = lo.cov; nLocal = lo.n;
    } else {
      notes.push("No local evidence for this archetype in " + region + "; the answer falls back to the archetype prior.");
    }
  }

  const r = distAt(depth, off);
  r.sdEpistemic = epistemicSd(depth, off, cov);
  r.sdTotal = Math.sqrt(r.sdAleatory*r.sdAleatory + r.sdEpistemic*r.sdEpistemic);
  r.nLocal = nLocal; r.nArch = A.n; r.arch = A; r.lvl = L; r.jrc = false;
  r.domain = domain;

  let conf = 100 * Math.exp(-r.sdEpistemic / FV.conf_scale);
  if (domain) conf -= 15;
  conf -= 6;                                  // construction level is assumed
  r.conf = Math.max(5, Math.min(98, Math.round(conf)));

  if (L.mode === "arch") r.grade = A.n >= 5000 ? "C" : "D";
  else if (nLocal >= 1000) r.grade = "A";
  else if (nLocal >= 100) r.grade = "B";
  else r.grade = "C";
  if (domain && r.grade === "A") r.grade = "B";
  r.lvlShown = (L.mode === "local") ? (nLocal >= 1000 ? "G4" : "G3") : L.g;

  notes.push("Aleatory spread is <b>" + r.sdAleatory.toFixed(3) + "</b> and does not fall with more evidence: it is genuine building-to-building variability at this depth.");
  const ratio = r.sdEpistemic > 1e-9 ? (jrcSpread(depth) / r.sdEpistemic) : null;
  notes.push("Epistemic spread is <b>" + r.sdEpistemic.toFixed(4) + "</b>: the part local evidence buys down"
    + (ratio && ratio > 1.5 ? ", about <b>" + Math.round(ratio) + "&times;</b> narrower than the published global prior at this depth" : "") + ".");
  if (nLocal > 0) notes.push("Partial pooling on <b>" + nLocal.toLocaleString() + "</b> local claims; the shift is shrunk toward the archetype in proportion to that count.");
  if (L.mode === "arch") notes.push("The region is unseen, so the offset that would apply to it is unknown with the full between-region prior variance.");
  if (domain) notes.push("Depth is outside the calibrated domain of &minus;1.5 to 5.0 m; uncertainty widened and confidence cut.");
  notes.push("P(no damage) is conditional on a claim being filed &mdash; see the limitation in the evidence section.");
  r.notes = notes;
  r.warnings = warnings;
  if (domain) r.warnings.push("out_of_domain_depth");
  r.warnings.push("p_zero_damage_conditional_on_claim_filed");
  if (nLocal === 0 && L.mode === "local") r.warnings.push("no_local_evidence_for_this_archetype_in_region");
  return r;
}

/* Convenience for the workflow sections: resolve by taxonomy key, apply the
   region offset if one exists, and return the full distribution. */
function byKey(key){
  for (let i = 0; i < ARCH.length; i++) if (ARCH[i].key === key) return ARCH[i];
  return ARCH[0];
}
function distFor(key, depth, region){
  const A = byKey(key);
  let off = A.offsets.slice();
  const lo = region ? FV.locals[key + "@" + region] : null;
  if (lo) off = [off[0]+lo.offsets[0], off[1]+lo.offsets[1], off[2]+lo.offsets[2], off[3]+lo.offsets[3]];
  const r = distAt(depth, off);
  r.nLocal = lo ? lo.n : 0;
  r.grade = r.nLocal >= 1000 ? "A" : (r.nLocal >= 100 ? "B" : "C");
  return r;
}

window.__FV_ENGINE = {ARCH:ARCH, LVL:LVL, REGIONS:REGIONS, engine:engine,
                      distAt:distAt, paramsAt:paramsAt, jrcCurve:jrcCurve,
                      byKey:byKey, distFor:distFor};
