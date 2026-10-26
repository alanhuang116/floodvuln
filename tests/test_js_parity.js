/* Cross-implementation check: the JavaScript engine shipped in the website must
   reproduce the Python engine it was exported from. A divergence here means the
   page is showing numbers the validation run never scored. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..");
const SITE = process.argv[2];
if (!SITE) { console.error("usage: node test_js_parity.js <site.html>"); process.exit(2); }

const html = fs.readFileSync(SITE, "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);

/* minimal DOM so the utility block can install window.__FV_MATH */
function el() {
  const e = {
    style: {}, dataset: {}, classList: { add() {}, remove() {} }, children: [],
    value: "70", textContent: "", innerHTML: "", clientWidth: 600, clientHeight: 300,
    offsetWidth: 100, offsetHeight: 40, disabled: false,
    addEventListener() {}, appendChild() {}, setAttribute() {}, getAttribute() { return "0"; },
    getBoundingClientRect() { return { left: 0, top: 0, width: 600, height: 300 }; },
    querySelector: () => el(), querySelectorAll: () => [], getContext: () => ctx(),
    focus() {}, click() {}
  };
  return e;
}
const ctx = () => new Proxy({}, {
  get: (t, k) => (k === "createLinearGradient" ? () => ({ addColorStop() {} }) : () => {}),
  set: () => true
});

const sandbox = {
  console,
  document: {
    documentElement: { getAttribute: () => null, setAttribute() {}, style: {} },
    body: { scrollHeight: 5000 },
    createElement: () => el(), getElementById: () => el(),
    querySelector: () => el(), querySelectorAll: () => []
  },
  window: {
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    addEventListener() {}, innerHeight: 900, scrollY: 0, devicePixelRatio: 1,
    requestAnimationFrame() {}, performance: { now: () => 0 }
  },
  requestAnimationFrame() {}, performance: { now: () => 0 },
  getComputedStyle: () => ({ getPropertyValue: () => "#008C7D" }),
  IntersectionObserver: function () { return { observe() {}, unobserve() {}, disconnect() {} }; }
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

/* run only the blocks we need: utilities, the model, the fitted engine */
let ran = 0;
for (const s of scripts) {
  if (s.includes("__FV_MATH") && s.includes("ibetaInv") ||
      s.includes("window.__FV_MODEL =") ||
      s.includes("window.__FV_ENGINE =") && s.includes("FITTED MODEL")) {
    try { vm.runInContext(s, sandbox); ran++; } catch (e) { /* DOM-dependent tails are fine */ }
  }
}

const E = sandbox.window.__FV_ENGINE;
if (!E) { console.error("FAIL: engine did not install"); process.exit(1); }
console.log(`ran ${ran} script blocks, engine installed`);

const expected = JSON.parse(fs.readFileSync(path.join(ROOT, "web", "parity_expected.json"), "utf8"));
let worst = 0, worstCase = "";
let fails = 0;
for (const c of expected) {
  const r = E.engine(c.arch_idx, c.depth, c.level_idx, c.region);
  for (const [k, v] of Object.entries(c.expect)) {
    const got = r[k];
    if (!isFinite(v) && !isFinite(got)) continue;
    const d = Math.abs(got - v);
    if (d > worst) { worst = d; worstCase = `${c.name}.${k} js=${got} py=${v}`; }
    if (d > 2e-3) { console.log(`FAIL ${c.name}.${k}: js=${got} py=${v}`); fails++; }
  }
}
console.log(`worst absolute divergence: ${worst.toExponential(2)}  (${worstCase})`);
if (fails) { console.log(`${fails} mismatches`); process.exit(1); }
console.log("PASS: JavaScript engine matches the Python engine");
