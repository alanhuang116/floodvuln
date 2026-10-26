(function(){
"use strict";
const M = window.__FV_MATH, E = window.__FV_ENGINE, $ = M.$, $$ = M.$$, clamp = M.clamp,
      T = M.T, REDRAW = M.REDRAW;
const ARCH = E.ARCH, LVL = E.LVL, engine = E.engine, FV = window.__FV_MODEL;

const state = {ai:0, depth:0.61, lvl:2, region:"TX", value:310000};

/* ---------- archetype chips ---------- */
const chipWrap = $("#archChips");
ARCH.forEach(function(a, i){
  const b = document.createElement("button");
  b.className = "chip"; b.type = "button";
  b.innerHTML = a.label + ' <span style="opacity:.65">n=' + (a.n/1000).toFixed(0) + 'k</span>';
  b.setAttribute("aria-pressed", i === 0 ? "true" : "false");
  b.addEventListener("click", function(){
    state.ai = i;
    $$(".chip", chipWrap).forEach(function(c, j){
      c.setAttribute("aria-pressed", j === i ? "true" : "false"); });
    render();
  });
  chipWrap.appendChild(b);
});

/* ---------- region select and asset value ---------- */
const regSel = $("#engRegion");
E.REGIONS.forEach(function(st){
  const o = document.createElement("option");
  o.value = st; o.textContent = st;
  regSel.appendChild(o);
});
regSel.value = "TX";
regSel.addEventListener("change", function(){ state.region = regSel.value; render(); });

const valIn = $("#engValue");
valIn.addEventListener("input", function(){
  const v = parseFloat(valIn.value.replace(/[^0-9.]/g, ""));
  state.value = isFinite(v) && v > 0 ? v : 310000;
  render();
});

/* ---------- ladder ---------- */
const ladder = $("#ladder");
LVL.forEach(function(l, i){
  const b = document.createElement("button");
  b.className = "rung"; b.type = "button";
  b.setAttribute("aria-pressed", i === 2 ? "true" : "false");
  b.innerHTML = '<span class="g">' + l.g + '</span><span class="t">' + l.t +
                '</span><span class="n">' + l.n + '</span>';
  b.addEventListener("click", function(){
    state.lvl = i;
    $$(".rung", ladder).forEach(function(c, j){
      c.setAttribute("aria-pressed", j === i ? "true" : "false"); });
    render();
  });
  ladder.appendChild(b);
});

const dep = $("#engDepth"), depOut = $("#engDepthOut");
dep.addEventListener("input", function(){
  state.depth = parseInt(dep.value, 10) / 100; render();
});

/* ---------- density chart ---------- */
const svg = $("#densChart");
const W = 620, H = 348, L = 48, R = 16, TOP = 22, B = 62;
const PW = W - L - R, PH = H - TOP - B;
const NB = 20, SLOT = PW / (NB + 2.6);
const tipBox = $("#densBox"), tipEl = $("#densTip");
let lastBars = [];

function showTip(html, cx, cy){
  tipEl.innerHTML = html; tipEl.classList.add("on");
  const bw = tipBox.clientWidth, tw = tipEl.offsetWidth;
  tipEl.style.left = clamp(cx - tw/2, 4, Math.max(4, bw - tw - 4)) + "px";
  tipEl.style.top = Math.max(4, cy - tipEl.offsetHeight - 12) + "px";
}

function drawEmptyJrc(r){
  const t = T(), o = [];
  o.push(`<rect x="${L}" y="${TOP}" width="${PW}" height="${PH}" fill="${t.grid}" opacity=".35" rx="3"/>`);
  const cx = L + PW/2, cy = TOP + PH/2;
  o.push(`<text x="${cx}" y="${cy - 26}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="12" fill="${t.ink2}" letter-spacing="1">NO DISTRIBUTION PUBLISHED</text>`);
  o.push(`<text x="${cx}" y="${cy - 4}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="10.5" fill="${t.ink3}">The JRC global product publishes one expected value per depth.</text>`);
  const x = L + r.mean * PW;
  o.push(`<line x1="${x.toFixed(1)}" y1="${TOP}" x2="${x.toFixed(1)}" y2="${TOP+PH}" stroke="${t.alarm||t.amb}" stroke-width="2.4"/>`);
  o.push(`<text x="${clamp(x, L+46, W-R-46).toFixed(1)}" y="${TOP-7}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="10" font-weight="600" fill="${t.amb}">published ${r.mean.toFixed(3)}</text>`);
  const x10 = L + r.p10 * PW, x90 = L + r.p90 * PW;
  o.push(`<rect x="${x10.toFixed(1)}" y="${TOP}" width="${Math.max(1.5,x90-x10).toFixed(1)}" height="${PH}" fill="${t.amb}" opacity=".14"/>`);
  o.push(`<text x="${((x10+x90)/2).toFixed(1)}" y="${TOP+PH+22}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="9.5" fill="${t.ink3}">between-continent spread of the published curves</text>`);
  [0,0.25,0.5,0.75,1].forEach(function(v){
    o.push(`<text x="${(L+v*PW).toFixed(1)}" y="${(TOP+PH+15).toFixed(1)}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="9.5" fill="${t.ink3}">${v.toFixed(2)}</text>`);
  });
  o.push(`<text x="${(L+PW/2).toFixed(1)}" y="${H-10}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="9.5" fill="${t.ink3}" letter-spacing="1">DAMAGE RATIO</text>`);
  svg.innerHTML = o.join("");
  lastBars = [];
}

function drawDensity(r){
  if (r.jrc) return drawEmptyJrc(r);
  const t = T(), o = [];
  const bins = [];
  for (let i = 0; i < NB; i++){
    bins.push(r.rest * (M.ibeta((i+1)/NB, r.a, r.b) - M.ibeta(i/NB, r.a, r.b)));
  }
  const ymax = Math.max(r.p0, r.p1, Math.max.apply(null, bins)) * 1.18;
  const yy = function(v){ return TOP + PH - (v/ymax)*PH; };
  const xBins = L + SLOT*1.5, xSpike0 = L + SLOT*0.12, xSpike1 = xBins + NB*SLOT + SLOT*0.35;

  for (let g = 0; g <= 4; g++){
    const v = (g/4)*ymax, y = yy(v);
    o.push(`<line x1="${L}" y1="${y.toFixed(1)}" x2="${W-R}" y2="${y.toFixed(1)}" stroke="${t.grid}" stroke-width="1"/>`);
    o.push(`<text x="${L-8}" y="${(y+4).toFixed(1)}" text-anchor="end" font-family="IBM Plex Mono, monospace" font-size="9.5" fill="${t.ink3}">${(v*100).toFixed(0)}%</text>`);
  }
  const x10 = xBins + r.p10*NB*SLOT, x90 = xBins + r.p90*NB*SLOT;
  o.push(`<rect x="${x10.toFixed(1)}" y="${TOP}" width="${Math.max(1.5,x90-x10).toFixed(1)}" height="${PH}" fill="${t.acc}" opacity=".13"/>`);

  lastBars = [];
  const bw = SLOT - 2;
  bins.forEach(function(p, i){
    const x = xBins + i*SLOT, y = yy(p), h = Math.max(0, TOP+PH-y);
    o.push(`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="${Math.min(4,h/2).toFixed(1)}" fill="${t.acc}" opacity=".92"/>`);
    lastBars.push({x:x, w:bw, p:p, lo:i/NB, hi:(i+1)/NB, kind:"bin"});
  });
  function spike(x, p, lab, kind){
    const y = yy(p), h = Math.max(0, TOP+PH-y), sw = SLOT*1.05;
    o.push(`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${sw.toFixed(1)}" height="${h.toFixed(1)}" rx="3" fill="${t.ink3}"/>`);
    o.push(`<text x="${(x+sw/2).toFixed(1)}" y="${(y-7).toFixed(1)}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="10" font-weight="600" fill="${t.ink2}">${(p*100).toFixed(1)}%</text>`);
    o.push(`<text x="${(x+sw/2).toFixed(1)}" y="${(TOP+PH+15).toFixed(1)}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="9.5" fill="${t.ink3}">${lab}</text>`);
    lastBars.push({x:x, w:sw, p:p, kind:kind});
  }
  spike(xSpike0, r.p0, "D = 0", "zero");
  spike(xSpike1, r.p1, "D = 1", "total");

  o.push(`<line x1="${L}" y1="${TOP+PH}" x2="${W-R}" y2="${TOP+PH}" stroke="${t.rule2}" stroke-width="1"/>`);
  [0,0.25,0.5,0.75,1].forEach(function(v){
    o.push(`<text x="${(xBins+v*NB*SLOT).toFixed(1)}" y="${(TOP+PH+15).toFixed(1)}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="9.5" fill="${t.ink3}">${v.toFixed(2)}</text>`);
  });
  o.push(`<text x="${(xBins+NB*SLOT/2).toFixed(1)}" y="${H-10}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="9.5" fill="${t.ink3}" letter-spacing="1">DAMAGE RATIO</text>`);
  o.push(`<text transform="translate(12,${TOP+96}) rotate(-90)" font-family="IBM Plex Mono, monospace" font-size="9.5" fill="${t.ink3}" letter-spacing="1">PROBABILITY</text>`);

  const by = TOP + PH + 30;
  o.push(`<line x1="${x10.toFixed(1)}" y1="${by}" x2="${x90.toFixed(1)}" y2="${by}" stroke="${t.acc}" stroke-width="2" stroke-linecap="round"/>`);
  o.push(`<text x="${((x10+x90)/2).toFixed(1)}" y="${by+13}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="9.5" fill="${t.acc}">P10 &#8211; P90 (aleatory)</text>`);

  const xm = xBins + r.mean*NB*SLOT;
  const xe = (r.sdEpistemic/1) * NB * SLOT;
  o.push(`<rect x="${(xm-xe*1.96).toFixed(1)}" y="${TOP}" width="${Math.max(1.2,2*1.96*xe).toFixed(1)}" height="${PH}" fill="${t.amb}" opacity=".30"/>`);
  o.push(`<line x1="${xm.toFixed(1)}" y1="${TOP}" x2="${xm.toFixed(1)}" y2="${(TOP+PH).toFixed(1)}" stroke="${t.amb}" stroke-width="2"/>`);
  o.push(`<text x="${clamp(xm, L+52, W-R-52).toFixed(1)}" y="${(TOP-7).toFixed(1)}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="10" font-weight="600" fill="${t.amb}">mean ${r.mean.toFixed(3)} &#177; ${r.sdEpistemic.toFixed(3)}</text>`);
  svg.innerHTML = o.join("");
}

svg.addEventListener("mousemove", function(ev){
  const rc = svg.getBoundingClientRect(), sx = (ev.clientX - rc.left) * (W / rc.width);
  let hit = null;
  lastBars.forEach(function(b){ if (sx >= b.x-1 && sx <= b.x+b.w+1) hit = b; });
  if (!hit){ tipEl.classList.remove("on"); return; }
  let label;
  if (hit.kind === "zero") label = `<b>No assessed damage</b><br>P(D = 0) = ${(hit.p*100).toFixed(2)}%<br><span style="opacity:.7">given a claim was filed</span>`;
  else if (hit.kind === "total") label = `<b>Effective total loss</b><br>P(D = 1) = ${(hit.p*100).toFixed(2)}%`;
  else label = `<b>DR ${hit.lo.toFixed(2)} &#8211; ${hit.hi.toFixed(2)}</b><br>P = ${(hit.p*100).toFixed(1)}%`;
  showTip(label, ((hit.x+hit.w/2)/W)*tipBox.clientWidth, tipBox.clientHeight*0.42);
});
svg.addEventListener("mouseleave", function(){ tipEl.classList.remove("on"); });

/* ---------- summary table ---------- */
function renderTable(r){
  const na = '<span style="opacity:.5">not published</span>';
  const f = function(v, d){ return isFinite(v) ? v.toFixed(d === undefined ? 3 : d) : na; };
  const pc = function(v){ return isFinite(v) ? (v*100).toFixed(1) + "%" : na; };
  const rows = [
    ["Mean damage ratio", f(r.mean), "Technical pricing and expected loss"],
    ["Median damage ratio", f(r.med), "Central outcome, less tail-sensitive"],
    ["P10 / P90", f(r.p10) + " / " + f(r.p90), "Outcome range at this depth"],
    ["P(damage &gt; 50%)", pc(r.pgt50), "Severity screening in underwriting"],
    ["P(effective total loss)", pc(r.p1), "Tail modelling and claims planning"],
    ["P(no damage | claim filed)", pc(r.p0), "Lower bound only &mdash; see limitations"],
    ["SD aleatory", f(r.sdAleatory), "Irreducible: evidence does not shrink this"],
    ["SD epistemic", f(r.sdEpistemic, 4), "What local evidence buys down"]
  ];
  $("#quantTable").innerHTML =
    `<caption class="cap" style="text-align:left; padding-bottom:8px">Distribution summary &#8212; fitted to 1,861,852 NFIP claims</caption><tbody>` +
    rows.map(function(x){
      return `<tr><td>${x[0]}</td><td class="n"><b>${x[1]}</b></td><td class="small" style="font-size:12.5px">${x[2]}</td></tr>`;
    }).join("") + `</tbody>`;
}

/* ---------- api panel ---------- */
function renderApi(r){
  const A = r.arch;
  const f = function(v, d){ return isFinite(v) ? v.toFixed(d === undefined ? 3 : d) : "null"; };
  const loss = isFinite(r.mean) ? Math.round(r.mean * state.value) : 0;
  const rows = [
    ["asset_archetype", `<span class="ss">US.${A.key}</span>`],
    ["region", `<span class="ss">${r.lvl.mode === "local" ? state.region : "unseen"}</span>`],
    ["effective_depth_m", `<span class="vv">${state.depth.toFixed(2)}</span>`],
    ["mean_damage_ratio", `<span class="vv">${f(r.mean)}</span>`],
    ["p10", `<span class="vv">${f(r.p10)}</span>`],
    ["p90", `<span class="vv">${f(r.p90)}</span>`],
    ["p_damage_gt_50pct", `<span class="vv">${f(r.pgt50)}</span>`],
    ["sd_aleatory", `<span class="vv">${f(r.sdAleatory)}</span>`],
    ["sd_epistemic", `<span class="vv">${f(r.sdEpistemic, 4)}</span>`],
    ["expected_ground_up_loss", `<span class="vv">${loss}</span> <span class="ss">USD</span>`],
    ["evidence_grade", `<span class="ss">${r.grade}</span>`],
    ["confidence_score", `<span class="vv">${r.conf}</span>`],
    ["calibration_level", `<span class="ss">${r.lvlShown || r.lvl.g}</span>`],
    ["local_sample_size", `<span class="vv">${r.nLocal}</span>`],
    ["archetype_sample_size", `<span class="vv">${r.nArch}</span>`],
    ["model_version", `<span class="ss">1.0.0</span>`],
    ["evidence_snapshot", `<span class="ss">${FV.evidence_snapshot}</span>`]
  ];
  (r.warnings || []).forEach(function(w){
    rows.push(["warning", `<span class="ss">${w}</span>`]);
  });
  $("#apiOut").innerHTML = rows.map(function(x){
    return `<span class="kk">${x[0]}</span>: ${x[1]}`; }).join("<br>");

  const gradeCls = {A:"", B:"", C:"amber", D:"alarm"}[r.grade];
  $("#evidenceBadges").innerHTML =
    `<span class="tag ${gradeCls}">Evidence grade ${r.grade}</span>` +
    `<span class="tag plain">Confidence ${r.conf} / 100</span>` +
    `<span class="tag amber">${r.lvlShown || r.lvl.g} &#183; ${r.lvl.t}</span>` +
    (r.domain ? `<span class="tag alarm">Out of domain</span>` : "");
  $("#whyList").innerHTML = (r.notes || []).map(function(n){
    return `<li>${n}</li>`; }).join("");
}

function render(){
  const r = engine(state.ai, state.depth, state.lvl, state.region);
  depOut.textContent = state.depth.toFixed(2) + " m";
  $("#archId").textContent = "US." + ARCH[state.ai].key;
  regSel.disabled = (LVL[state.lvl].mode !== "local");
  drawDensity(r); renderTable(r); renderApi(r);
}
render();
REDRAW.push(render);
})();
