/* Execute every script block in the published page against a DOM stub and fail
   on any exception. Syntax checks and id checks both pass on a page whose
   sections silently throw at runtime, which is exactly the failure this catches:
   a changed engine signature leaves the markup intact and the content empty. */
const fs = require("fs");
const vm = require("vm");

const SITE = process.argv[2];
if (!SITE) { console.error("usage: node test_site_runtime.js <site.html>"); process.exit(2); }
const html = fs.readFileSync(SITE, "utf8");
const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);

const ids = new Set([...html.matchAll(/\sid="([^"]+)"/g)].map(m => m[1]));
const written = {};           // id -> last innerHTML written, to detect empty renders

function el(id) {
  const e = {
    _id: id, style: {}, dataset: {}, children: [],
    classList: { add() {}, remove() {}, contains: () => false },
    value: "70", textContent: "", disabled: false,
    clientWidth: 620, clientHeight: 330, offsetWidth: 120, offsetHeight: 40,
    get innerHTML() { return this._html || ""; },
    set innerHTML(v) { this._html = v; if (id) written[id] = v; },
    addEventListener() {},
    appendChild(c) { this.children.push(c); if (id) written[id] = (written[id] || "") + (c._html || c.textContent || "<el>"); },
    setAttribute() {}, removeAttribute() {},
    getAttribute() { return "0"; }, focus() {}, click() {},
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 620, height: 330 }),
    querySelector: () => el(), querySelectorAll: () => [],
    getContext: () => ctx(), toFixed: undefined,
  };
  return e;
}
const ctx = () => new Proxy({}, {
  get: (t, k) => (k === "createLinearGradient" ? () => ({ addColorStop() {} }) : () => {}),
  set: () => true,
});

const cache = {};
const byId = (id) => (cache[id] = cache[id] || el(id));

const errors = [];
const sandbox = {
  console: { log() {}, warn() {}, error(...a) { errors.push("console.error: " + a.join(" ")); } },
  document: {
    documentElement: { getAttribute: () => null, setAttribute() {}, style: {} },
    body: { scrollHeight: 5000 },
    createElement: () => el(),
    getElementById: (id) => byId(id),
    querySelector: (s) => (s.startsWith("#") ? byId(s.slice(1)) : el()),
    querySelectorAll: () => [],
  },
  window: {
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    addEventListener() {}, innerHeight: 900, scrollY: 0, devicePixelRatio: 1,
    requestAnimationFrame() {}, performance: { now: () => 0 },
  },
  requestAnimationFrame() {}, performance: { now: () => 0 },
  getComputedStyle: () => ({ getPropertyValue: () => "#008C7D" }),
  IntersectionObserver: function () { return { observe() {}, unobserve() {}, disconnect() {} }; },
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

scripts.forEach((s, i) => {
  try {
    vm.runInContext(s, sandbox, { timeout: 20000 });
  } catch (e) {
    errors.push(`script #${i + 1} threw: ${e.message}`);
  }
});

/* Containers the page fills from JS. If one is still empty, its section is blank
   on the live page even though the markup and the ids are present. */
const MUST_RENDER = [
  "densChart", "cloudChart", "quantTable", "apiOut", "evidenceBadges", "whyList",
  "archChips", "ladder", "engRegion", "learnChart", "cmpChart", "portTable",
  "grades", "modGrid", "bankChart", "chain", "bankTiles", "uwTable", "prTiles",
];
const empty = MUST_RENDER.filter(id => ids.has(id) && !(written[id] && written[id].length > 1));

console.log(`script blocks executed: ${scripts.length}`);
console.log(`containers checked:     ${MUST_RENDER.filter(id => ids.has(id)).length}`);
if (errors.length) {
  console.log(`\n${errors.length} RUNTIME ERROR(S):`);
  errors.forEach(e => console.log("  - " + e));
}
if (empty.length) {
  console.log(`\n${empty.length} CONTAINER(S) RENDERED EMPTY:`);
  empty.forEach(e => console.log("  - #" + e));
}
if (!errors.length && !empty.length) {
  console.log("\nPASS: every script ran and every dynamic container rendered content");
  process.exit(0);
}
process.exit(1);
