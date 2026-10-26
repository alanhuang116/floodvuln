(function(){
"use strict";
const M = window.__FV_MATH, $ = M.$, clamp = M.clamp, T = M.T, REDRAW = M.REDRAW;
const FV = window.__FV_MODEL;

const svg = $("#cmpChart"); if (!svg) return;
const rows = ((FV.validation || {}).event || []).slice();
if (!rows.length) return;

const NICE = {
  JRC_NA_residential_published: "JRC published global curve",
  naive_constant_mean: "Constant mean (naive)",
  single_curve_fitted_on_train: "Single fitted depth curve",
  FloodVuln_G0_global_fit: "FloodVuln global fit",
  FloodVuln_G1_archetype: "FloodVuln archetype",
  FloodVuln_G4_local: "FloodVuln region calibrated"
};
const D = rows.map(function(r){
  return {n: NICE[r.model] || r.model, v: r.bias, hi: r.model.indexOf("FloodVuln") === 0};
}).sort(function(a, b){ return a.v - b.v; });

const W = 560, H = 250, L = 186, R = 40, TOP = 14, B = 40;
const PW = W - L - R, PH = H - TOP - B;
const MX = Math.max.apply(null, D.map(function(d){ return Math.abs(d.v); })) * 1.25;
const zx = L + PW / 2;
const bw = (PH - D.length * 8) / D.length;
const tipBox = $("#cmpBox"), tipEl = $("#cmpTip");

function draw(){
  const t = T(), o = [];
  const ticks = [-MX, -MX/2, 0, MX/2, MX];
  ticks.forEach(function(v){
    const x = zx + (v / MX) * (PW / 2);
    o.push(`<line x1="${x.toFixed(1)}" y1="${TOP}" x2="${x.toFixed(1)}" y2="${TOP+PH}" stroke="${v===0?t.rule2:t.grid}" stroke-width="1"/>`);
    o.push(`<text x="${x.toFixed(1)}" y="${(TOP+PH+16).toFixed(1)}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="9.5" fill="${t.ink3}">${v>0?"+":""}${v.toFixed(2)}</text>`);
  });
  D.forEach(function(d, i){
    const y = TOP + i * (bw + 8);
    const x = Math.min(zx, zx + (d.v / MX) * (PW / 2));
    const w = Math.abs((d.v / MX) * (PW / 2));
    const c = d.hi ? t.acc : t.ink3;
    o.push(`<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${Math.max(2,w).toFixed(1)}" height="${bw.toFixed(1)}" rx="3" fill="${c}" opacity="${d.hi?"1":".55"}"/>`);
    o.push(`<text x="${L-12}" y="${(y+bw/2+4).toFixed(1)}" text-anchor="end" font-family="IBM Plex Mono, monospace" font-size="10" fill="${d.hi?t.ink:t.ink2}" font-weight="${d.hi?"600":"400"}">${d.n}</text>`);
    const lx = d.v > 0 ? zx + w + 7 : zx - w - 7;
    o.push(`<text x="${lx.toFixed(1)}" y="${(y+bw/2+4).toFixed(1)}" text-anchor="${d.v>0?"start":"end"}" font-family="IBM Plex Mono, monospace" font-size="10" font-weight="600" fill="${d.hi?t.acc:t.ink2}">${d.v>0?"+":""}${d.v.toFixed(3)}</text>`);
  });
  o.push(`<text x="${zx}" y="${H-6}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="9" fill="${t.ink3}" letter-spacing="1">MEAN BIAS IN DAMAGE RATIO, 11 WITHHELD EVENTS</text>`);
  svg.innerHTML = o.join("");
}
draw(); REDRAW.push(draw);

svg.addEventListener("mousemove", function(ev){
  const rc = svg.getBoundingClientRect(), sy = (ev.clientY - rc.top) * (H / rc.height);
  const i = Math.floor((sy - TOP) / (bw + 8));
  if (i < 0 || i >= D.length){ tipEl.classList.remove("on"); return; }
  const d = D[i];
  tipEl.innerHTML = `<b>${d.n}</b><br>mean bias ${d.v > 0 ? "+" : ""}${d.v.toFixed(4)}<br>` +
    `<span style="opacity:.75">${d.v > 0 ? "over" : "under"}-predicts damage</span>`;
  tipEl.classList.add("on");
  const tw = tipEl.offsetWidth;
  tipEl.style.left = clamp(tipBox.clientWidth / 2 - tw / 2, 4, Math.max(4, tipBox.clientWidth - tw - 4)) + "px";
  tipEl.style.top = "6px";
});
svg.addEventListener("mouseleave", function(){ tipEl.classList.remove("on"); });
})();
