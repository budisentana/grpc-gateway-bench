"""Build a self-contained HTML results page from summarize.py output.

Usage: python3 analysis/make_report.py SUMMARY_DIR OUT.html [--title T] [--note TEXT] [--crosscheck FILE]

The page embeds results.json and draws its charts in plain JS/SVG, so it can
be opened locally or published as-is.
"""
import argparse
import html
import json
import os

TEMPLATE = r"""<title>__TITLE__</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: a single lab-report column, 960px max; tables and charts scroll inside their own frames on phones. */
:root {
  --bg: #f6f7f9; --panel: #ffffff; --fg: #17202b; --muted: #5b6776; --line: #d9dee5; --soft: #eef1f5;
  --accent: #0f6e8c; --warn-bg: #fff4dd; --warn-fg: #7a4b00; --ok: #1d7a46; --bad: #b3261e;
  --c0: #5b6776; --c1: #0f8a8a; --c2: #c2620a; --c3: #6a4bc4;
  --sans: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #11161c; --panel: #171e26; --fg: #e4e9ef; --muted: #98a3b1; --line: #2b3541; --soft: #1e2731;
  --accent: #4fb3d1; --warn-bg: #3a2c10; --warn-fg: #f5c97a; --ok: #5cc98b; --bad: #f08a80;
  --c0: #9aa6b4; --c1: #3fc1bf; --c2: #f0954a; --c3: #a28cf0; color-scheme: dark; } }
:root[data-theme="dark"] {
  --bg: #11161c; --panel: #171e26; --fg: #e4e9ef; --muted: #98a3b1; --line: #2b3541; --soft: #1e2731;
  --accent: #4fb3d1; --warn-bg: #3a2c10; --warn-fg: #f5c97a; --ok: #5cc98b; --bad: #f08a80;
  --c0: #9aa6b4; --c1: #3fc1bf; --c2: #f0954a; --c3: #a28cf0; color-scheme: dark; }
body { background: var(--bg); color: var(--fg); font: 15px/1.55 var(--sans); }
.wrap { max-width: 960px; margin: 0 auto; padding-block: 32px 64px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: grid; gap: 28px; }
header { display: grid; gap: 10px; }
.eyebrow { font: 500 12px/1 var(--mono); letter-spacing: .08em; text-transform: uppercase; color: var(--accent); }
h1 { font-size: 30px; line-height: 1.2; margin: 0; font-weight: 600; text-wrap: balance; }
h2 { font-size: 19px; margin: 0; font-weight: 600; text-wrap: balance; }
p { margin: 0; max-width: 68ch; }
.muted { color: var(--muted); }
.banner { background: var(--warn-bg); color: var(--warn-fg); border-radius: 8px; padding: 12px 16px; font-size: 14px; }
.env { display: flex; flex-wrap: wrap; gap: 6px 16px; font: 13px/1.4 var(--mono); color: var(--muted); }
section { display: grid; gap: 12px; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 16px; display: grid; gap: 12px; min-width: 0; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
.kpi { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px 16px; display: grid; gap: 4px; }
.kpi b { font: 600 22px/1.2 var(--mono); font-variant-numeric: tabular-nums; }
.kpi span { font-size: 13px; color: var(--muted); }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: right; padding: 7px 10px; border-bottom: 1px solid var(--line); white-space: nowrap; font-variant-numeric: tabular-nums; }
th { font: 500 12px/1.3 var(--sans); color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
th:first-child, td:first-child { text-align: left; }
td.mono { font-family: var(--mono); }
.swatch { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: 0; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 13px; color: var(--muted); }
.controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 13px; color: var(--muted); }
select { font: inherit; color: var(--fg); background: var(--soft); border: 1px solid var(--line); border-radius: 6px; padding: 4px 8px; }
select:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
svg text { fill: var(--muted); font: 12px var(--sans); }
svg .val { fill: var(--fg); font: 11px var(--mono); }
.pill { display: inline-block; font: 500 12px/1 var(--mono); padding: 4px 8px; border-radius: 99px; background: var(--soft); }
.pill.ok { color: var(--ok); } .pill.bad { color: var(--bad); }
code, pre { font-family: var(--mono); font-size: 13px; }
pre { background: var(--soft); border-radius: 8px; padding: 12px 14px; margin: 0; overflow-x: auto; }
.note { font-size: 13px; color: var(--muted); }
</style>

<div class="wrap">
<header>
  <div class="eyebrow">qsbg-bench · results</div>
  <h1>__HEADING__</h1>
  __BANNER__
  <div class="env" id="env"></div>
</header>

<section>
  <div class="kpis" id="kpis"></div>
</section>

<section>
  <h2>Signature cost per operation</h2>
  <p class="muted">Table 6. Median of single-threaded runs on the gateway core, 200-byte message. Lower is better.</p>
  <div class="panel scroll"><table id="micro"></table></div>
</section>

<section>
  <h2>Throughput and tail latency by configuration</h2>
  <p class="muted">Table 9. Closed loop; bars are medians across repetitions, whiskers the 95% bootstrap interval.</p>
  <div class="panel">
    <div class="controls"><label for="pl">Payload</label><select id="pl"></select>
      <span class="legend" id="legend1"></span></div>
    <div class="scroll"><svg id="chartRps" role="img" aria-label="Throughput by configuration"></svg></div>
    <div class="scroll"><svg id="chartP99" role="img" aria-label="p99 latency by configuration"></svg></div>
  </div>
  <div class="panel scroll"><table id="t9"></table></div>
</section>

<section id="openSec">
  <h2>Latency as offered load rises</h2>
  <p class="muted">Open loop, 128-byte payload. Latency is measured from each request's scheduled send time, so queueing shows up in the tail.</p>
  <div class="panel">
    <div class="legend" id="legend2"></div>
    <div class="scroll"><svg id="chartOpen" role="img" aria-label="p99 latency against offered load"></svg></div>
  </div>
</section>

<section>
  <h2>Where the gateway spends its time</h2>
  <p class="muted">Tables 7 and 8. Median per-request stage times inside the gateway, and the metadata each request carries to the backend.</p>
  <div class="panel scroll"><table id="stages"></table></div>
</section>

<section id="gridSec">
  <h2>Batch signing trade-off (C3)</h2>
  <p class="muted">Table 10. Each cell: throughput as % of C0 at the same concurrency, then added median latency versus C0.</p>
  <div class="panel scroll"><table id="grid"></table></div>
</section>

<section id="headSec">
  <h2>Metadata headroom under the 8 KB limit</h2>
  <p class="muted">Filler headers stand in for tracing and authorisation metadata. Requests fail once the header list passes the backend's 8,192-byte gRPC-style limit.</p>
  <div class="panel">
    <div class="legend" id="legend3"></div>
    <div class="scroll"><svg id="chartHead" role="img" aria-label="Metadata size against filler bytes"></svg></div>
  </div>
</section>

<section>
  <h2>Statistical tests</h2>
  <p class="muted">Mann–Whitney U between configurations, Holm-corrected within each condition. With 3 repetitions per group the exact test cannot go below p = 0.1, so nothing here can reach significance; this checks the analysis pipeline. The lab runs need at least 6 repetitions.</p>
  <div class="panel scroll"><table id="tests"></table></div>
</section>

<section>
  <h2>Reproduce</h2>
  <pre>go build -o bin/ ./cmd/...
./bin/certgen -out certs
GW_CPUS=0 GW_PROCS=1 BE_CPUS=1 LG_CPUS=1 scripts/run_pilot.sh results/pilot
python3 analysis/make_report.py results/pilot/summary report.html</pre>
  <p class="note">Full lab procedure, network emulation and the paper's run matrix are in the package README.</p>
</section>
</div>

<script>
const DATA = __DATA__;
const META = __META__;
const CFG = ["C0","C1","C2","C3"];
const CFG_NAME = {C0:"C0 classical mTLS", C1:"C1 hybrid PQ key exchange", C2:"C2 ML-DSA per request", C3:"C3 ML-DSA per batch"};
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const color = c => css("--" + c.toLowerCase());
const fmt = (v, d=0) => v == null || Number.isNaN(v) ? "–" : Number(v).toLocaleString("en-US", {minimumFractionDigits:d, maximumFractionDigits:d});
const el = (tag, attrs={}, text) => { const e = document.createElementNS(tag === "svg" || attrs._svg ? "http://www.w3.org/2000/svg" : "http://www.w3.org/1999/xhtml", tag);
  for (const [k,v] of Object.entries(attrs)) if (k !== "_svg") e.setAttribute(k, v); if (text != null) e.textContent = text; return e; };
const S = (tag, attrs, text) => el(tag, {...attrs, _svg:true}, text);

function table(id, head, rows) {
  const t = document.getElementById(id); t.innerHTML = "";
  const thead = t.createTHead().insertRow(); head.forEach(h => { const th = document.createElement("th"); th.textContent = h; thead.appendChild(th); });
  const tb = t.createTBody();
  rows.forEach(r => { const tr = tb.insertRow(); r.forEach((c, i) => { const td = tr.insertCell();
    if (c && typeof c === "object" && c.html) td.innerHTML = c.html; else td.textContent = c; if (i === 0) td.className = "mono"; }); });
}
const sw = c => `<span class="swatch" style="background:var(--${c.toLowerCase()})"></span>${c}`;
function legend(id, cfgs) { document.getElementById(id).innerHTML = cfgs.map(c => `<span>${sw(c).replace(/>C\d</, ">"+CFG_NAME[c]+"<")}</span>`).join(""); }

// ---- environment + KPIs
document.getElementById("env").innerHTML = META.env.map(x => `<span>${x}</span>`).join("");
const summ = DATA.summary.filter(r => r.mode === "closed");
const pick = (cfg, pl, c) => summ.find(r => r.config === cfg && r.payload === pl && r.concurrency === c);
const plMin = Math.min(...summ.map(r => r.payload)); const cMax = Math.max(...summ.map(r => r.concurrency));
const c0 = pick("C0", plMin, cMax), c2 = pick("C2", plMin, cMax), c3best = (DATA.batch_grid||[]).reduce((a,b) => !a || b.rps > a.rps ? b : a, null);
const mlGo = (DATA.microbench[0]?.results || []).find(r => r.scheme.startsWith("mldsa65"));
const kpis = [
  [META.crosscheck || "–", "ML-DSA-65 cases matching OpenSSL"],
  [mlGo ? fmt(mlGo.sign.median_us) + " µs" : "–", "ML-DSA-65 sign, median"],
  [c0 && c2 ? fmt(100 * c2.rps / c0.rps) + " %" : "–", `C2 throughput vs C0 (${plMin} B, ${cMax} clients)`],
  (() => { const h = (DATA.headroom||[]).find(h => h.config === "C2" && h.pad_bytes === 0);
     const v = h ? h.metadata_bytes_max : c2?.metadata_bytes_avg; return [v ? fmt(v) + " B" : "–", "C2 metadata per request as received, of 8,192 allowed"]; })(),
];
document.getElementById("kpis").innerHTML = kpis.map(([v,l]) => `<div class="kpi"><b>${v}</b><span>${l}</span></div>`).join("");

// ---- micro-benchmark
const microRows = [];
DATA.microbench.forEach(m => (m.results||[]).forEach(r => microRows.push([r.scheme + (m.library ? "" : " (Go)"), fmt(r.signature_bytes), fmt(r.keygen.median_us,1), fmt(r.sign.median_us,1), fmt(r.verify.median_us,1),
  r.sign_ops_per_s_one_core ? fmt(r.sign_ops_per_s_one_core) : fmt(1e6 / r.sign.mean_us)])));
table("micro", ["Scheme", "Signature (B)", "Keygen (µs)", "Sign (µs)", "Verify (µs)", "Signs/s per core"], microRows);

// ---- grouped bar charts
const payloads = [...new Set(summ.map(r => r.payload))].sort((a,b)=>a-b);
const sel = document.getElementById("pl"); payloads.forEach(p => sel.add(new Option(p + " B", p)));
legend("legend1", CFG);
function bars(svgId, metric, lo, hi, label) {
  const pl = +sel.value; const rows = summ.filter(r => r.payload === pl);
  const conc = [...new Set(rows.map(r => r.concurrency))].sort((a,b)=>a-b);
  const W = 880, H = 260, m = {l:64, r:12, t:16, b:40}; const svg = document.getElementById(svgId);
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("width", W); svg.innerHTML = "";
  const maxV = Math.max(1, ...rows.map(r => Math.max(r[hi] ?? r[metric], r[metric]))) * 1.1;
  const y = v => m.t + (H - m.t - m.b) * (1 - v / maxV);
  const ticks = niceTicks(maxV);
  ticks.forEach(t => { svg.appendChild(S("line", {x1:m.l, x2:W-m.r, y1:y(t), y2:y(t), stroke:css("--line")}));
    svg.appendChild(S("text", {x:m.l-8, y:y(t)+4, "text-anchor":"end"}, fmt(t, t < 10 && t % 1 ? 1 : 0))); });
  svg.appendChild(S("text", {x:14, y:H/2, transform:`rotate(-90 14 ${H/2})`, "text-anchor":"middle"}, label));
  const gw = (W - m.l - m.r) / conc.length, bw = Math.min(40, (gw - 24) / CFG.length);
  conc.forEach((c, gi) => {
    const x0 = m.l + gi * gw + (gw - bw * CFG.length) / 2;
    svg.appendChild(S("text", {x:m.l + gi*gw + gw/2, y:H-14, "text-anchor":"middle"}, c + " clients"));
    CFG.forEach((cfg, ci) => { const r = rows.find(r => r.config === cfg && r.concurrency === c); if (!r) return;
      const x = x0 + ci * bw; svg.appendChild(S("rect", {x:x+2, y:y(r[metric]), width:bw-4, height:y(0)-y(r[metric]), fill:color(cfg), rx:2}));
      if (r[lo] != null && r[hi] != null) { const cx = x + bw/2;
        svg.appendChild(S("line", {x1:cx, x2:cx, y1:y(r[lo]), y2:y(r[hi]), stroke:css("--fg"), "stroke-width":1.2}));
        [r[lo], r[hi]].forEach(v => svg.appendChild(S("line", {x1:cx-4, x2:cx+4, y1:y(v), y2:y(v), stroke:css("--fg"), "stroke-width":1.2}))); }
      svg.appendChild(S("text", {class:"val", x:x+bw/2, y:y(r[hi] ?? r[metric]) - 5, "text-anchor":"middle"}, fmt(r[metric], r[metric] < 10 ? 1 : 0)));
    });
  });
}
function niceTicks(max) { const raw = max / 4, p = 10 ** Math.floor(Math.log10(raw)); const step = [1,2,2.5,5,10].map(s => s*p).find(s => s >= raw);
  const out = []; for (let v = 0; v <= max + 1e-9; v += step) out.push(+v.toFixed(6)); return out; }
function drawBars() {
  bars("chartRps", "rps", "rps_ci_lo", "rps_ci_hi", "requests / s");
  bars("chartP99", "lat_p99_ms", "lat_p99_ms_ci_lo", "lat_p99_ms_ci_hi", "p99 latency (ms)");
  const pl = +sel.value;
  table("t9", ["Config", "Clients", "Reps", "RPS", "p50 (ms)", "p99 (ms)", "Gateway CPU (%)", "CPU per request (µs)", "Auth stage (µs)", "Errors (%)"],
    summ.filter(r => r.payload === pl).sort((a,b) => a.concurrency - b.concurrency || a.config.localeCompare(b.config))
      .map(r => [{html: sw(r.config)}, r.concurrency, r.reps, fmt(r.rps), fmt(r.lat_p50_ms,2), fmt(r.lat_p99_ms,2), fmt(r.gw_cpu_pct),
        fmt(r.gw_cpu_us_per_req), fmt(r.stage_auth_us,1), fmt(r.error_rate_pct,2)]));
}
sel.addEventListener("change", drawBars);

// ---- open loop line chart
const open = DATA.summary.filter(r => r.mode === "open");
if (!open.length) document.getElementById("openSec").hidden = true; else {
  legend("legend2", CFG);
  const W = 880, H = 300, m = {l:64, r:16, t:16, b:44}, svg = document.getElementById("chartOpen");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("width", W);
  const rates = [...new Set(open.map(r => r.offered_rate))].sort((a,b)=>a-b);
  const maxX = Math.max(...rates), maxY = Math.max(...open.map(r => r.lat_p99_ms));
  const yMin = Math.max(0.1, Math.min(...open.map(r => r.lat_p99_ms)) * 0.8);
  const x = v => m.l + (W - m.l - m.r) * v / maxX;
  const ly = v => m.t + (H - m.t - m.b) * (1 - (Math.log10(v) - Math.log10(yMin)) / (Math.log10(maxY * 1.3) - Math.log10(yMin)));
  [0.1,1,10,100,1000,10000,100000].filter(t => t >= yMin && t <= maxY*1.3).forEach(t => {
    svg.appendChild(S("line", {x1:m.l, x2:W-m.r, y1:ly(t), y2:ly(t), stroke:css("--line")}));
    svg.appendChild(S("text", {x:m.l-8, y:ly(t)+4, "text-anchor":"end"}, t))});
  rates.forEach(r => svg.appendChild(S("text", {x:x(r), y:H-24, "text-anchor":"middle"}, fmt(r))));
  svg.appendChild(S("text", {x:(W+m.l)/2, y:H-6, "text-anchor":"middle"}, "offered load (requests / s)"));
  svg.appendChild(S("text", {x:14, y:H/2, transform:`rotate(-90 14 ${H/2})`, "text-anchor":"middle"}, "p99 latency (ms, log)"));
  CFG.forEach(cfg => { const pts = open.filter(r => r.config === cfg).sort((a,b) => a.offered_rate - b.offered_rate); if (!pts.length) return;
    svg.appendChild(S("polyline", {points: pts.map(p => `${x(p.offered_rate)},${ly(p.lat_p99_ms)}`).join(" "), fill:"none", stroke:color(cfg), "stroke-width":2}));
    pts.forEach(p => { const c = S("circle", {cx:x(p.offered_rate), cy:ly(p.lat_p99_ms), r: p.error_rate_pct > 1 ? 5 : 3.5,
      fill: p.error_rate_pct > 1 ? css("--panel") : color(cfg), stroke:color(cfg), "stroke-width":2});
      c.appendChild(S("title", {}, `${cfg} @ ${p.offered_rate}/s: p99 ${fmt(p.lat_p99_ms,1)} ms, achieved ${fmt(p.rps)}/s`)); svg.appendChild(c); });
  });
}

// ---- stages table
const stRows = CFG.map(cfg => pick(cfg, plMin, cMax)).filter(Boolean).map(r => [{html: sw(r.config)}, fmt(r.stage_parse_us,1), fmt(r.stage_map_us,1),
  fmt(r.stage_auth_us,1), fmt(r.stage_forward_us,1), fmt(r.stage_total_us,1), fmt(r.metadata_bytes_avg), fmt(r.internal_bytes_out_per_req), fmt(r.signatures_per_req,3)]);
table("stages", ["Config", "Parse JSON", "Map to Protobuf", "Authenticate", "Forward + wait", "Total gateway", "Metadata (B)", "Internal bytes out / req", "Signatures / req"], stRows);
document.getElementById("stages").insertAdjacentHTML("afterend", `<p class="note">Stage times in µs, ${plMin}-byte payload, ${cMax} clients. Internal bytes are TLS bytes the gateway sends to the backend. Metadata here is counted by the gateway, before the HTTP/2 client adds about 111 bytes of its own headers.</p>`);

// ---- batch grid
const grid = DATA.batch_grid || [];
if (!grid.length) document.getElementById("gridSec").hidden = true; else {
  const Ts = [...new Set(grid.map(g => g.batch_window_ms))].sort((a,b)=>a-b), Bs = [...new Set(grid.map(g => g.batch_max))].sort((a,b)=>a-b);
  table("grid", ["Window T", ...Bs.map(b => "B = " + b), "Avg batch size"], Ts.map(t => [t + " ms", ...Bs.map(b => {
    const g = grid.find(g => g.batch_window_ms === t && g.batch_max === b); return g ? `${fmt(g.rps_pct_of_C0)} % / +${fmt(g.added_p50_ms_vs_C0,2)} ms` : "–"; }),
    grid.filter(g => g.batch_window_ms === t).map(g => fmt(g.avg_batch_size,1)).join(" · ")]));
  document.getElementById("grid").insertAdjacentHTML("afterend", `<p class="note">${grid[0].concurrency} clients, 128-byte payload. Average batch size per cell in the last column, in the same order as the B columns.</p>`);
}

// ---- headroom chart
const head = DATA.headroom || [];
if (!head.length) document.getElementById("headSec").hidden = true; else {
  const cfgs = [...new Set(head.map(h => h.config))]; legend("legend3", cfgs);
  const W = 880, H = 280, m = {l:64, r:16, t:16, b:44}, svg = document.getElementById("chartHead");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("width", W);
  const maxX = Math.max(...head.map(h => h.pad_bytes)), maxY = Math.max(9000, ...head.map(h => h.metadata_bytes_max || 0)) * 1.05;
  const x = v => m.l + (W-m.l-m.r) * v / maxX, y = v => m.t + (H-m.t-m.b) * (1 - v / maxY);
  niceTicks(maxY).forEach(t => { svg.appendChild(S("line", {x1:m.l, x2:W-m.r, y1:y(t), y2:y(t), stroke:css("--line")}));
    svg.appendChild(S("text", {x:m.l-8, y:y(t)+4, "text-anchor":"end"}, fmt(t))); });
  niceTicks(maxX).forEach(t => svg.appendChild(S("text", {x:x(t), y:H-24, "text-anchor":"middle"}, fmt(t))));
  svg.appendChild(S("line", {x1:m.l, x2:W-m.r, y1:y(8192), y2:y(8192), stroke:css("--bad"), "stroke-dasharray":"5 4", "stroke-width":1.5}));
  svg.appendChild(S("text", {x:W-m.r, y:y(8192)-6, "text-anchor":"end"}, "8,192-byte limit"));
  svg.appendChild(S("text", {x:(W+m.l)/2, y:H-6, "text-anchor":"middle"}, "filler metadata added (bytes)"));
  svg.appendChild(S("text", {x:14, y:H/2, transform:`rotate(-90 14 ${H/2})`, "text-anchor":"middle"}, "header list size (bytes)"));
  cfgs.forEach(cfg => { const pts = head.filter(h => h.config === cfg).sort((a,b) => a.pad_bytes - b.pad_bytes);
    svg.appendChild(S("polyline", {points: pts.map(p => `${x(p.pad_bytes)},${y(p.metadata_bytes_max)}`).join(" "), fill:"none", stroke:color(cfg), "stroke-width":2}));
    pts.forEach(p => { const failed = p.completed_ok === 0 || p.be_metadata_rejects > 0;
      const c = S("circle", {cx:x(p.pad_bytes), cy:y(p.metadata_bytes_max), r: failed ? 5 : 3.5, fill: failed ? css("--panel") : color(cfg), stroke: failed ? css("--bad") : color(cfg), "stroke-width":2});
      c.appendChild(S("title", {}, `${cfg} +${p.pad_bytes} B: ${fmt(p.metadata_bytes_max)} B, ${failed ? "rejected" : "accepted"}`)); svg.appendChild(c); }); });
  document.getElementById("legend3").insertAdjacentHTML("beforeend", `<span><span class="swatch" style="border:2px solid var(--bad);background:transparent"></span>hollow red point = requests rejected</span>`);
}

// ---- tests
const tests = (DATA.tests || []).filter(t => t.metric === "rps" && t.mode === "closed");
table("tests", ["Condition", "Pair", "n", "p (Holm)", "Effect (rank-biserial)", "Result"],
  tests.map(t => [`${t.payload} B · ${t.concurrency} clients`, t.pair, `${t.n_a} / ${t.n_b}`, fmt(t.mwu_p_holm, 3), fmt(t.rank_biserial, 2),
    {html: t.mwu_p_holm < 0.05 ? '<span class="pill ok">differs</span>' : '<span class="pill">not shown</span>'}]));

drawBars();
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => location.reload());
</script>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("summary_dir")
    ap.add_argument("out")
    ap.add_argument("--title", default="QSBG Pilot Results")
    ap.add_argument("--heading", default="QSBG benchmark: sandbox pilot")
    ap.add_argument("--note", default="")
    ap.add_argument("--env", default="", help="semicolon-separated environment facts")
    ap.add_argument("--crosscheck", default="")
    a = ap.parse_args()
    data = json.load(open(os.path.join(a.summary_dir, "results.json")))
    cross = ""
    if a.crosscheck and os.path.exists(a.crosscheck):
        line = open(a.crosscheck).read().strip().splitlines()[-1]
        cross = line.split(" cases")[0]
    meta = {"env": [html.escape(x.strip()) for x in a.env.split(";") if x.strip()], "crosscheck": cross}
    banner = f'<div class="banner">{html.escape(a.note)}</div>' if a.note else ""
    page = (TEMPLATE.replace("__TITLE__", html.escape(a.title)).replace("__HEADING__", html.escape(a.heading))
            .replace("__BANNER__", banner).replace("__DATA__", json.dumps(data).replace("</", "<\\/"))
            .replace("__META__", json.dumps(meta)))
    with open(a.out, "w") as fh:
        fh.write(page)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
