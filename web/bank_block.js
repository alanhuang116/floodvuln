(function(){
"use strict";
const M = window.__FV_MATH, E = window.__FV_ENGINE, $ = M.$, $$ = M.$$, clamp = M.clamp,
      T = M.T, REDRAW = M.REDRAW;
const FF = "IBM Plex Mono, monospace";

/* Book assumptions are illustrative; the damage ratio at every depth is the
   fitted model, so the vulnerability link in the chain is real even though the
   portfolio around it is a worked example. */
const RP = [20, 50, 100, 200, 500];
const BASED = [0.14, 0.40, 0.66, 0.95, 1.35];
const SCEN = [{lab:"Current climate", s:0.05},
              {lab:"+1.5°C · 2050", s:0.34},
              {lab:"+3.0°C · 2050", s:0.74}];
const EXPOSED = 0.18, EAD = 18.4e9, PD = 0.011, STRUCT = 0.58;
const ARCH_KEY = "RES.SF.1.SLAB";
const st = {scen:0, adapt:false};

function depthAt(i, scen, year){ return BASED[i] * (1 + SCEN[scen].s * (year - 2025) / 30); }
function drAt(d, adapt){
  const base = E.distFor(ARCH_KEY, d, null).mean;
  if (!adapt) return base;
  const lifted = E.distFor(ARCH_KEY, Math.max(-0.6, d - 0.35), null).mean;
  return 0.45 * lifted + 0.55 * base;
}
function aalBps(scen, year, adapt){
  let a = 0;
  for (let i = 0; i < RP.length; i++){
    const w = (1/RP[i]) - (i + 1 < RP.length ? 1/RP[i+1] : 0);
    a += w * drAt(depthAt(i, scen, year), adapt);
  }
  return a * EXPOSED * 10000;
}

const svg = $("#bankChart");
const W = 620, H = 320, L = 52, R = 76, TOP = 18, B = 46;
const PW = W - L - R, PH = H - TOP - B;
const YEARS = [2025, 2030, 2035, 2040, 2045, 2050, 2055];
const tipBox = $("#bankBox"), tipEl = $("#bankTip");
function xy(yr){ return L + ((yr - 2025) / 30) * PW; }

function drawBank(){
  const t = T(), o = [];
  const ramp = [t.d2, t.d3, t.d4];
  let ymax = 0;
  const series = SCEN.map(function(s, si){
    return YEARS.map(function(y){ const v = aalBps(si, y, st.adapt); if (v > ymax) ymax = v; return v; });
  });
  const ghost = st.adapt ? SCEN.map(function(s, si){
    return YEARS.map(function(y){ const v = aalBps(si, y, false); if (v > ymax) ymax = v; return v; });
  }) : null;
  ymax = Math.max(1, Math.ceil(ymax * 1.15));
  const yv = function(v){ return TOP + PH - (v / ymax) * PH; };

  for (let g = 0; g <= 4; g++){
    const v = (g/4) * ymax, y = yv(v);
    o.push(`<line x1="${L}" y1="${y.toFixed(1)}" x2="${W-R}" y2="${y.toFixed(1)}" stroke="${t.grid}" stroke-width="1"/>`);
    o.push(`<text x="${L-9}" y="${(y+4).toFixed(1)}" text-anchor="end" font-family="${FF}" font-size="9.5" fill="${t.ink3}">${v.toFixed(1)}</text>`);
  }
  YEARS.forEach(function(y){
    o.push(`<text x="${xy(y).toFixed(1)}" y="${(TOP+PH+16).toFixed(1)}" text-anchor="middle" font-family="${FF}" font-size="9.5" fill="${t.ink3}">${y}</text>`);
  });
  o.push(`<text transform="translate(11,${TOP+130}) rotate(-90)" font-family="${FF}" font-size="9.5" fill="${t.ink3}" letter-spacing="1">BPS OF EXPOSURE</text>`);

  if (ghost){
    ghost.forEach(function(vals, si){
      let p = "";
      vals.forEach(function(v, i){ p += (i ? " L" : "M") + xy(YEARS[i]).toFixed(1) + " " + yv(v).toFixed(1); });
      o.push(`<path d="${p}" fill="none" stroke="${ramp[si]}" stroke-width="1.4" stroke-dasharray="3 4" opacity=".5"/>`);
    });
  }
  series.forEach(function(vals, si){
    let p = "";
    vals.forEach(function(v, i){ p += (i ? " L" : "M") + xy(YEARS[i]).toFixed(1) + " " + yv(v).toFixed(1); });
    const on = si === st.scen;
    o.push(`<path d="${p}" fill="none" stroke="${ramp[si]}" stroke-width="${on?3.2:2}" stroke-linecap="round" opacity="${on?1:.55}"/>`);
    o.push(`<circle cx="${xy(2055).toFixed(1)}" cy="${yv(vals[6]).toFixed(1)}" r="${on?5:3.6}" fill="${ramp[si]}" stroke="${t.surf}" stroke-width="2"/>`);
    o.push(`<text x="${(W-R+8)}" y="${(yv(vals[6])+4).toFixed(1)}" font-family="${FF}" font-size="9.5" font-weight="${on?"600":"400"}" fill="${ramp[si]}" opacity="${on?1:.7}">${vals[6].toFixed(1)} bps</text>`);
  });
  svg.innerHTML = o.join("");

  $("#bankLegend").innerHTML = SCEN.map(function(s, si){
    return `<span><i style="background:${ramp[si]}"></i>${s.lab}</span>`;
  }).join("") + (st.adapt ? `<span><i style="background:${t.ink3}; height:2px"></i>Dashed: without adaptation</span>` : "");
}

if (svg) svg.addEventListener("mousemove", function(ev){
  const rc = svg.getBoundingClientRect(), sx = (ev.clientX - rc.left) * (W / rc.width);
  let by = YEARS[0], bd = 1e9;
  YEARS.forEach(function(y){ const d = Math.abs(xy(y) - sx); if (d < bd){ bd = d; by = y; } });
  if (bd > 36){ tipEl.classList.remove("on"); return; }
  const lines = SCEN.map(function(s, si){ return `${s.lab}: <b>${aalBps(si, by, st.adapt).toFixed(2)} bps</b>`; }).join("<br>");
  tipEl.innerHTML = `<b>${by}</b><br>${lines}`;
  tipEl.classList.add("on");
  const bw = tipBox.clientWidth, tw = tipEl.offsetWidth;
  tipEl.style.left = clamp((xy(by)/W)*bw - tw/2, 4, Math.max(4, bw-tw-4)) + "px";
  tipEl.style.top = "8px";
});
if (svg) svg.addEventListener("mouseleave", function(){ tipEl.classList.remove("on"); });

function drawChain(){
  const t = T();
  const d100 = depthAt(2, st.scen, 2050);
  const r = E.distFor(ARCH_KEY, d100, null);
  const dr = drAt(d100, st.adapt);
  const haircut = dr * STRUCT;
  const ltvShare = clamp(0.061 + haircut * 0.55, 0, 0.6);
  const lgdUp = haircut * 0.42 * 100;
  const eclUp = lgdUp * PD * 100;
  const steps = [
    ["Hazard", "1-in-100 inundation depth, 2050", d100.toFixed(2) + " m", t.sl, false],
    ["Vulnerability", "Mean damage ratio, fitted (P10&ndash;P90 " + r.p10.toFixed(2) + "&ndash;" + r.p90.toFixed(2) + ")", dr.toFixed(3), t.acc, true],
    ["Collateral", "Forward-looking value haircut", (haircut*100).toFixed(1) + "%", t.acc, false],
    ["LTV migration", "Exposed book above 80% LTV", (ltvShare*100).toFixed(1) + "%", t.amb, false],
    ["LGD", "Uplift on loss given default", "+" + lgdUp.toFixed(1) + " pp", t.amb, false],
    ["ECL", "Uplift on expected credit loss", "+" + eclUp.toFixed(1) + " bps", t.al, false]
  ];
  $("#chain").innerHTML = steps.map(function(s, i){
    const mark = s[4] ? `<span class="tag" style="margin-left:8px">fitted layer</span>` : "";
    return `<div style="display:grid; grid-template-columns:1fr auto; gap:12px; align-items:center; padding:11px 13px;` +
      ` border:1px solid ${s[4]?s[3]:"var(--rule)"}; border-left:3px solid ${s[3]}; border-radius:3px;` +
      ` background:${s[4]?"var(--accent-wash)":"transparent"}">` +
      `<div><div style="font-family:var(--f-display); font-weight:600; font-size:13px">${s[0]}${mark}</div>` +
      `<div class="cap" style="margin-top:3px">${s[1]}</div></div>` +
      `<div class="num" style="font-family:var(--f-display); font-weight:700; font-size:19px; letter-spacing:-.02em; color:${s[3]}">${s[2]}</div>` +
      `</div>` +
      (i < steps.length-1 ? `<div style="height:9px; width:1px; background:var(--rule-2); margin-left:22px"></div>` : "");
  }).join("");
}

function drawTiles(){
  const bps2050 = aalBps(st.scen, 2050, st.adapt);
  const bpsNow = aalBps(0, 2025, false);
  const d100 = depthAt(2, st.scen, 2050);
  const loss100 = drAt(d100, st.adapt) * EAD * EXPOSED;
  const lgdUp = drAt(d100, st.adapt) * STRUCT * 0.42 * 100;
  const ecl = lgdUp * PD * 100;
  const tiles = [
    ["Exposure at default", "$18.4bn", "42,000 residential loans; 18% in flood-exposed locations."],
    ["Annual collateral damage 2050", bps2050.toFixed(1) + " bps", "Against " + bpsNow.toFixed(1) + " bps in the current climate."],
    ["1-in-100 collateral loss", "$" + (loss100/1e6).toFixed(0) + "m", "Ground-up damage on exposed collateral at that return period."],
    ["ECL uplift", "+" + ecl.toFixed(1) + " bps", "Transmitted through the haircut, LTV migration and LGD."]
  ];
  $("#bankTiles").innerHTML = tiles.map(function(t){
    return `<div class="tile"><span class="k">${t[0]}</span><span class="v">${t[1]}</span><span class="d">${t[2]}</span></div>`;
  }).join("");
}

function renderBank(){ if (svg) drawBank(); drawChain(); drawTiles(); }

$$("#scenChips .chip").forEach(function(c){
  c.addEventListener("click", function(){
    st.scen = parseInt(c.getAttribute("data-scen"), 10);
    $$("#scenChips .chip").forEach(function(o){ o.setAttribute("aria-pressed", o === c ? "true" : "false"); });
    renderBank();
  });
});
const ad = $("#adaptBtn");
if (ad) ad.addEventListener("click", function(){
  st.adapt = !st.adapt;
  ad.setAttribute("aria-pressed", st.adapt ? "true" : "false");
  renderBank();
});
renderBank();
REDRAW.push(renderBank);
})();
