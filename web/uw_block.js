(function(){
"use strict";
const M = window.__FV_MATH, E = window.__FV_ENGINE, $ = M.$, T = M.T, REDRAW = M.REDRAW;

/* Underwriting comparison at a fixed depth. Both rows come from the fitted
   model, so the contrast is measured rather than asserted. */
const D = 0.90, REGION = "TX";
const ROWS = [
  {tag:"A", key:"RES.SF.1.ELEV_ENCL", label:"Elevated, enclosure below"},
  {tag:"B", key:"RES.SF.MH.UNK",      label:"Manufactured home"}
];

function drawUw(){
  const t = T(), tb = $("#uwTable"); if (!tb) return;
  const res = ROWS.map(function(r){ return {r:r, x:E.distFor(r.key, D, REGION)}; });
  let html = res.map(function(o){
    const g = {A:t.good, B:t.good, C:t.amb, D:t.al}[o.x.grade] || t.ink3;
    return `<tr><td><b>${o.r.tag}</b> &nbsp;<span class="small" style="font-size:12px">${o.r.label}</span></td>` +
      `<td class="mono" style="font-size:11px">${o.r.key}</td>` +
      `<td class="n">${o.x.mean.toFixed(3)}</td>` +
      `<td class="n">${o.x.p90.toFixed(2)}</td>` +
      `<td class="n">${(o.x.pgt50*100).toFixed(1)}%</td>` +
      `<td><span class="sev"><i style="background:${g}"></i>${o.x.grade}</span></td></tr>`;
  }).join("");
  const avg = (res[0].x.mean + res[1].x.mean) / 2;
  html += `<tr style="opacity:.75"><td colspan="2" class="small" style="font-size:12.5px">` +
    `<i>A depth-only curve, which cannot tell them apart</i></td>` +
    `<td class="n">${avg.toFixed(3)}</td><td class="n">&#8212;</td><td class="n">&#8212;</td>` +
    `<td><span class="sev"><i style="background:${t.ink3}"></i>n/a</span></td></tr>`;
  tb.innerHTML = html;

  const ratio = res[1].x.mean / res[0].x.mean;
  const cap = $("#uwCaption");
  if (cap) cap.innerHTML = `Depth ${D.toFixed(2)}&nbsp;m above the lowest floor, region ${REGION}. ` +
    `Fitted output: the manufactured home takes <b>${ratio.toFixed(1)}&times;</b> the proportional ` +
    `damage of the elevated dwelling at the same depth.`;
}

/* Pricing: the deductible is applied by integrating the fitted distribution,
   not by subtracting it from the mean. */
function drawPricing(){
  const el = $("#prTiles"); if (!el) return;
  const v = 310000, K = 25000, d = 0.55;
  const r = E.distFor("RES.SF.1.SLAB", d, REGION);
  const t0 = K / v;
  const gu = r.mean * v;
  const tail = r.p90 * v;
  // E[(vD - K)+] = p1(v-K) + rest*( v*mu*(1 - I_t(a+1,b)) - K*(1 - I_t(a,b)) )
  const net = r.p1 * (v - K) + r.rest * (v * r.m * (1 - M.ibeta(t0, r.a + 1, r.b))
                                         - K * (1 - M.ibeta(t0, r.a, r.b)));
  const noClaim = r.p0 + r.rest * M.ibeta(t0, r.a, r.b);
  const money = function(x){ return x >= 1e6 ? "$" + (x/1e6).toFixed(2) + "m" : "$" + (x/1000).toFixed(1) + "k"; };
  const tiles = [
    ["Expected ground-up", money(gu), "Mean DR " + r.mean.toFixed(3) + " on a $310k replacement value."],
    ["Tail load basis", money(tail), "P90 ground-up loss &#8212; the number a flat regional factor misses."],
    ["Net of $25k deductible", money(Math.max(0, net)), "Integrated over the whole distribution, not applied to the mean."],
    ["No payable claim", (noClaim*100).toFixed(0) + "%", "Probability the loss never reaches the deductible."]
  ];
  el.innerHTML = tiles.map(function(x){
    return `<div class="tile"><span class="k">${x[0]}</span><span class="v">${x[1]}</span><span class="d">${x[2]}</span></div>`;
  }).join("");
}

drawUw(); drawPricing();
REDRAW.push(function(){ drawUw(); drawPricing(); });
})();
