(function(){
"use strict";
const M = window.__FV_MATH, E = window.__FV_ENGINE, $ = M.$, clamp = M.clamp,
      T = M.T, REDRAW = M.REDRAW;
const FV = window.__FV_MODEL;

const svg = $("#cloudChart"); if (!svg) return;
const W = 900, H = 380, L = 62, R = 150, TOP = 18, B = 46;
const PW = W - L - R, PH = H - TOP - B;
const DMAX = 3.2;
const px = function(d){ return L + (d / DMAX) * PW; };
const py = function(v){ return TOP + (1 - v) * PH; };

/* Observed bins for the largest archetype, straight from the calibration run. */
const A = FV.archetypes.filter(function(a){ return a.key === "RES.SF.1.SLAB"; })[0]
       || FV.archetypes[0];
const OBS = A.empirical.filter(function(e){ return e.d >= -0.1 && e.d <= DMAX; });

const tipBox = $("#cloudBox"), tipEl = $("#cloudTip");

function draw(){
  const t = T(), o = [];

  for (let g = 0; g <= 5; g++){
    const v = g/5, y = py(v);
    o.push(`<line x1="${L}" y1="${y.toFixed(1)}" x2="${L+PW}" y2="${y.toFixed(1)}" stroke="${t.grid}" stroke-width="1"/>`);
    o.push(`<text x="${L-10}" y="${(y+4).toFixed(1)}" text-anchor="end" font-family="IBM Plex Mono, monospace" font-size="10.5" fill="${t.ink3}">${v.toFixed(1)}</text>`);
  }
  for (let d = 0; d <= DMAX; d += 0.5){
    o.push(`<text x="${px(d).toFixed(1)}" y="${H-22}" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-size="10.5" fill="${t.ink3}">${d.toFixed(1)}</text>`);
  }
  o.push(`<text x="${L}" y="${H-4}" font-family="IBM Plex Mono, monospace" font-size="10" fill="${t.ink3}" letter-spacing="1">DEPTH ABOVE LOWEST FLOOR (m)</text>`);
  o.push(`<text transform="translate(16,${TOP+118}) rotate(-90)" font-family="IBM Plex Mono, monospace" font-size="10" fill="${t.ink3}" letter-spacing="1">DAMAGE RATIO</text>`);

  /* observed P10-P90 whiskers: the actual spread in the claims */
  OBS.forEach(function(e){
    const x = px(e.d);
    o.push(`<line x1="${x.toFixed(1)}" y1="${py(e.p10).toFixed(1)}" x2="${x.toFixed(1)}" y2="${py(e.p90).toFixed(1)}" stroke="${t.ink3}" stroke-width="9" stroke-linecap="round" opacity=".28"/>`);
  });

  /* fitted mean */
  let fp = "";
  const off = A.offsets;
  for (let i = 0; i <= 80; i++){
    const d = (i/80)*DMAX;
    fp += (i ? " L" : "M") + px(d).toFixed(1) + " " + py(E.distAt(d, off).mean).toFixed(1);
  }
  o.push(`<path d="${fp}" fill="none" stroke="${t.acc}" stroke-width="2.8" stroke-linecap="round"/>`);

  /* published JRC North America residential */
  let jp = "";
  for (let i = 0; i <= 80; i++){
    const d = (i/80)*DMAX;
    jp += (i ? " L" : "M") + px(d).toFixed(1) + " " + py(E.jrcCurve(d)).toFixed(1);
  }
  o.push(`<path d="${jp}" fill="none" stroke="${t.al}" stroke-width="2.4" stroke-dasharray="7 5" stroke-linecap="round"/>`);

  /* observed means */
  OBS.forEach(function(e){
    o.push(`<circle cx="${px(e.d).toFixed(1)}" cy="${py(e.mean).toFixed(1)}" r="5" fill="${t.ink}" stroke="${t.surf}" stroke-width="1.8"/>`);
  });

  const last = OBS[OBS.length-1] || {d:2.5};
  o.push(`<text x="${(L+PW+10)}" y="${py(E.jrcCurve(DMAX)).toFixed(1)}" font-family="IBM Plex Mono, monospace" font-size="10.5" fill="${t.al}">JRC published</text>`);
  o.push(`<text x="${(L+PW+10)}" y="${(py(E.distAt(DMAX, off).mean)+4).toFixed(1)}" font-family="IBM Plex Mono, monospace" font-size="10.5" font-weight="600" fill="${t.acc}">FloodVuln fitted</text>`);
  o.push(`<g id="cloudHover"></g>`);
  svg.innerHTML = o.join("");
}
draw(); REDRAW.push(draw);

svg.addEventListener("mousemove", function(ev){
  const rc = svg.getBoundingClientRect(), sx = (ev.clientX - rc.left) * (W / rc.width);
  let best = null, bd = 1e9;
  OBS.forEach(function(e){ const dd = Math.abs(px(e.d) - sx); if (dd < bd){ bd = dd; best = e; } });
  if (!best || bd > 46){ tipEl.classList.remove("on"); return; }
  const t = T();
  const g = svg.querySelector("#cloudHover");
  const fit = E.distAt(best.d, A.offsets).mean, jrc = E.jrcCurve(best.d);
  if (g) g.innerHTML =
    `<line x1="${px(best.d)}" y1="${TOP}" x2="${px(best.d)}" y2="${TOP+PH}" stroke="${t.ink2}" stroke-width="1" stroke-dasharray="3 3"/>`;
  tipEl.innerHTML = `<b>${best.d.toFixed(2)} m</b> &nbsp;n = ${best.n.toLocaleString()}<br>` +
    `observed mean <b>${best.mean.toFixed(3)}</b><br>` +
    `observed P10&ndash;P90 ${best.p10.toFixed(2)} &ndash; ${best.p90.toFixed(2)}<br>` +
    `fitted ${fit.toFixed(3)} &nbsp;&middot;&nbsp; JRC ${jrc.toFixed(3)}`;
  tipEl.classList.add("on");
  const bw = tipBox.clientWidth, tw = tipEl.offsetWidth;
  tipEl.style.left = clamp((px(best.d)/W)*bw - tw/2, 4, Math.max(4, bw-tw-4)) + "px";
  tipEl.style.top = "10px";
});
svg.addEventListener("mouseleave", function(){
  tipEl.classList.remove("on");
  const g = svg.querySelector("#cloudHover"); if (g) g.innerHTML = "";
});
})();
