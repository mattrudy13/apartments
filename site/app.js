/* Apartment tracker front end. Data comes from site/data/*.json (written by build.py). */

// ---------- helpers ----------
const money = (n) => (n == null ? "—" : "$" + Math.round(n).toLocaleString("en-US"));
const fmtDate = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};
const shortDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
const bedKeyOrder = (k) => (k === "Studio" ? 0 : k === "Other" ? 99 : parseFloat(k));
const sortBedKeys = (keys) => [...new Set(keys)].sort((a, b) => bedKeyOrder(a) - bedKeyOrder(b));
const bedLabel = (b) => (b == null ? "—" : b === 0 ? "Studio" : `${b} BR`);
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const seriesColor = (i) => cssVar(`--series-${(i % 8) + 1}`);

/** Tiny DOM builder: h("td", {class: "r"}, "text", childNode). Strings become text nodes. */
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style") el.style.cssText = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

/** Delta badge. For prices, up is bad (red); for unit counts, up is good. */
function deltaEl(value, { isPrice = false } = {}) {
  if (value == null) return null;
  if (value === 0) return h("span", { class: "delta flat" }, "no change");
  const up = value > 0;
  const good = isPrice ? !up : up;
  const text = (up ? "▲ " : "▼ ") + (isPrice ? money(Math.abs(value)) : Math.abs(value));
  return h("span", { class: `delta ${good ? "down" : "up"}`, title: "vs previous pull" }, text);
}

/** A price, or "Call" when units are listed but the site publishes no price. */
function priceOrCall(price, units) {
  if (price == null && units) return h("span", { class: "muted", title: "Units are listed, but this site doesn't publish prices" }, "Call");
  return money(price);
}

/** "net $1,685" line shown under a listed price when specials lower it. */
function netEl(eff, listed) {
  if (eff == null || listed == null || eff >= listed) return null;
  return h("div", { class: "net", title: "Effective monthly rent after specials, spread over the lease" }, `net ${money(eff)}`);
}

const weeksLabel = (days) => (days < 7 ? `${days}d` : `${Math.round(days / 7)} wk`);

/** Chip pair that toggles a chart between listed and net (after specials) prices. */
function priceModeChips(state, onChange) {
  const row = h("div", { class: "filters", style: "margin-bottom:8px" });
  const draw = () => row.replaceChildren(...[["listed", "Listed price"], ["net", "Net of specials"]].map(([k, label]) =>
    h("button", { class: "chip", "aria-pressed": String(state.mode === k), onclick: () => { state.mode = k; draw(); onChange(); } }, label)));
  draw();
  return row;
}

function sparkline(values, { width = 90, height = 26, color = cssVar("--accent") } = {}) {
  const pts = values.map((v, i) => [i, v]).filter(([, v]) => v != null);
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("width", width); svg.setAttribute("height", height);
  svg.setAttribute("class", "spark"); svg.setAttribute("aria-hidden", "true");
  if (pts.length < 2) return svg;
  const ys = pts.map((p) => p[1]);
  const min = Math.min(...ys), max = Math.max(...ys), span = max - min || 1;
  const n = values.length - 1 || 1;
  const xy = pts.map(([i, v]) => [2 + (i / n) * (width - 4), height - 3 - ((v - min) / span) * (height - 6)]);
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", xy.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(""));
  path.setAttribute("fill", "none"); path.setAttribute("stroke", color);
  path.setAttribute("stroke-width", "2"); path.setAttribute("stroke-linejoin", "round"); path.setAttribute("stroke-linecap", "round");
  const dot = document.createElementNS(ns, "circle");
  const [lx, ly] = xy[xy.length - 1];
  dot.setAttribute("cx", lx); dot.setAttribute("cy", ly); dot.setAttribute("r", "2.5"); dot.setAttribute("fill", color);
  svg.append(path, dot);
  return svg;
}

/** append() that skips null/false (optional elements) instead of printing "null". */
const add = (parent, ...kids) => parent.append(...kids.flat().filter((k) => k != null && k !== false));

// ---------- charts (Chart.js) ----------
const charts = [];
const crosshair = {
  id: "crosshair",
  afterDatasetsDraw(chart) {
    const active = chart.tooltip && chart.tooltip.getActiveElements();
    if (!active || !active.length) return;
    const x = active[0].element.x, { top, bottom } = chart.chartArea, ctx = chart.ctx;
    ctx.save(); ctx.strokeStyle = cssVar("--text-3"); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke(); ctx.restore();
  },
};

/** Line chart, one y-axis. series: [{label, colorIndex, data: [number|null]}] */
function lineChart(canvas, labels, series, { money: isMoney = true, yMin, yMax, compact = false } = {}) {
  const make = () => {
    const text2 = cssVar("--text-2"), grid = cssVar("--grid"), surface = cssVar("--surface");
    return new Chart(canvas, {
      type: "line",
      data: {
        labels: labels.map(shortDate),
        datasets: series.map((s) => ({
          label: s.label, data: s.data, spanGaps: true,
          borderColor: seriesColor(s.colorIndex), backgroundColor: seriesColor(s.colorIndex),
          borderWidth: 2, pointRadius: labels.length > 12 ? 0 : compact ? 3 : 4, pointHoverRadius: 5,
          pointBorderColor: surface, pointBorderWidth: 2, tension: 0,
        })),
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: cssVar("--surface"), titleColor: cssVar("--text-2"), bodyColor: cssVar("--text"),
            borderColor: cssVar("--border"), borderWidth: 1, padding: 10, boxWidth: 12, boxHeight: 2, usePointStyle: false,
            callbacks: { label: (c) => ` ${isMoney ? money(c.parsed.y) : c.parsed.y}  ${c.dataset.label}` },
            itemSort: (a, b) => (b.parsed.y ?? 0) - (a.parsed.y ?? 0),
          },
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: text2, maxRotation: 0, autoSkipPadding: 16, maxTicksLimit: compact ? 3 : undefined }, border: { color: grid } },
          y: {
            grid: { color: grid }, border: { display: false },
            ticks: { color: text2, callback: (v) => (isMoney ? money(v) : v), maxTicksLimit: compact ? 3 : 5, precision: 0 },
            // Small multiples share one scale so cards compare at a glance.
            ...(yMin != null && yMax != null ? { min: yMin, max: yMax } : { grace: "10%" }),
          },
        },
      },
      plugins: [crosshair],
    });
  };
  // Re-drawing a canvas (e.g. listed/net toggle) replaces its chart instead of stacking a new one.
  // Drop charts whose canvas left the page (small multiples re-render their grid).
  for (let j = charts.length - 1; j >= 0; j--) {
    if (!charts[j].canvas.isConnected && charts[j].canvas !== canvas) { charts[j].chart.destroy(); charts.splice(j, 1); }
  }
  const i = charts.findIndex((c) => c.canvas === canvas);
  if (i >= 0) { charts[i].chart.destroy(); charts.splice(i, 1); }
  const entry = { canvas, make, chart: make() };
  charts.push(entry);
  return entry.chart;
}

function legendEl(series) {
  if (series.length < 2) return null;
  return h("div", { class: "legend" }, series.map((s) => h("span", { style: `--c: ${seriesColor(s.colorIndex)}` }, s.label)));
}

// Re-render charts when the color scheme flips so they pick up the dark/light tokens.
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
  for (const c of charts) { c.chart.destroy(); c.chart = c.make(); }
});

async function getJSON(path) {
  const res = await fetch(path, { cache: "no-cache" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

// ---------- overview page ----------
async function renderOverview() {
  const { complexes } = await getJSON("data/summary.json");
  const root = document.getElementById("app");

  const lastDate = complexes.map((c) => c.date).filter(Boolean).sort().pop();
  document.getElementById("updated").textContent = lastDate ? `Last pull ${fmtDate(lastDate)}` : "";

  // Totals
  const totalUnits = complexes.reduce((s, c) => s + (c.units || 0), 0);
  const cheapest = complexes.filter((c) => c.min_price != null).sort((a, b) => a.min_price - b.min_price)[0];
  add(root, 
    h("div", { class: "tiles" },
      h("div", { class: "card tile" }, h("div", { class: "label" }, "Complexes tracked"), h("div", { class: "value num" }, complexes.length)),
      h("div", { class: "card tile" }, h("div", { class: "label" }, "Units available"), h("div", { class: "value num" }, totalUnits)),
      h("div", { class: "card tile" }, h("div", { class: "label" }, "Lowest price anywhere"),
        h("div", { class: "value num" }, money(cheapest && cheapest.min_price)),
        h("div", { class: "sub" }, cheapest ? cheapest.name : "")),
      (() => {
        const best = complexes.filter((c) => c.min_effective != null).sort((a, b) => a.min_effective - b.min_effective)[0];
        return best && best.min_effective < (cheapest ? cheapest.min_price : Infinity)
          ? h("div", { class: "card tile" }, h("div", { class: "label" }, "Lowest net of specials"),
              h("div", { class: "value num" }, money(best.min_effective)), h("div", { class: "sub" }, best.name))
          : null;
      })(),
    ),
  );

  // Table: sortable; defaults to cheapest first. Price sorts use the net price when specials lower it.
  const bedKeys = sortBedKeys(complexes.flatMap((c) => Object.keys(c.by_beds || {})));
  const bestPrice = (x) => (x ? (x.min_effective ?? x.min_price ?? null) : null);
  const sortValue = {
    name: (c) => c.name.toLowerCase(),
    units: (c) => c.units ?? null,
    price: (c) => bestPrice(c),
    ...Object.fromEntries(bedKeys.map((k) => [`bed:${k}`, (c) => bestPrice((c.by_beds || {})[k])])),
  };
  const tableState = { sort: "price", dir: 1 };
  const thead = h("thead"), tbody = h("tbody");
  const sortTh = (key, label, cls = "", title = null) => h("th", {
    class: `sortable ${cls}`, title,
    "aria-sort": tableState.sort === key ? (tableState.dir > 0 ? "ascending" : "descending") : null,
    onclick: () => { tableState.dir = tableState.sort === key ? -tableState.dir : 1; tableState.sort = key; drawTable(); },
  }, label);
  const row = (c) => h("tr", {},
    h("td", { class: "name-cell" },
      h("a", { href: `complex.html?c=${encodeURIComponent(c.slug)}` }, c.name),
      c.stale ? h("span", { class: "badge warn", style: "margin-left:8px", title: c.error || "" }, "stale") : null,
      h("div", { class: "addr" }, c.address || "")),
    h("td", { class: "r num" }, c.units ?? "—", deltaEl(c.units_delta)),
    h("td", { class: "r num" }, priceOrCall(c.min_price, c.units), deltaEl(c.min_price_delta, { isPrice: true }),
      netEl(c.min_effective, c.min_price), c.price_basis === "total" && c.min_price != null ? h("div", { class: "muted small", title: "This site only shows prices that include required monthly fees" }, "incl. fees") : null),
    bedKeys.map((k) => {
      const b = (c.by_beds || {})[k];
      return h("td", { class: "r num hide-sm" }, b ? [h("span", {}, priceOrCall(b.min_price, b.units), h("span", { class: "muted small" }, ` (${b.units})`)), netEl(b.min_effective, b.min_price)] : h("span", { class: "muted" }, "—"));
    }),
    h("td", { class: "hide-sm" }, sparkline((c.history || []).map((p) => p.min_price))),
    h("td", { class: "muted small" }, fmtDate(c.date)),
  );
  const drawTable = () => {
    const val = sortValue[tableState.sort];
    const sorted = complexes.slice().sort((a, b) => {
      const av = val(a), bv = val(b);
      if (av == null && bv == null) return a.name.localeCompare(b.name);
      if (av == null) return 1; if (bv == null) return -1;  // no price / no units: always last
      return (av < bv ? -1 : av > bv ? 1 : 0) * tableState.dir;
    });
    thead.replaceChildren(h("tr", {},
      sortTh("name", "Complex"), sortTh("units", "Units", "r"), sortTh("price", "Lowest price", "r", "Sorted by net price when specials lower it"),
      bedKeys.map((k) => sortTh(`bed:${k}`, k, "r hide-sm", "Lowest price (units available); sorted by net price when specials lower it")),
      h("th", { class: "hide-sm" }, "Price trend"), h("th", {}, "Updated")));
    tbody.replaceChildren(...sorted.map(row));
  };
  drawTable();
  add(root,
    h("div", { class: "card" },
      h("h2", {}, "Availability"),
      h("div", { class: "table-scroll" }, h("table", {}, thead, tbody)),
      h("p", { class: "note" }, "Click a column to sort; price columns sort by net price when specials lower it, and complexes without a price go last. Prices are base rent where the site shows it. Deltas compare with the previous pull. Bedroom columns show the lowest price with units available in parentheses. “Net” is the effective monthly rent after specials (e.g. months free) spread over the lease. “Call” means the complex lists units but doesn't publish prices."),
    ),
  );

  // Trends as small multiples: one mini chart per complex on a shared scale (no per-complex colors needed).
  const dates = [...new Set(complexes.flatMap((c) => (c.history || []).map((p) => p.date)))].sort();
  const trend = { mode: "listed" };
  const modes = [["listed", "Lowest price"], ["net", "Net of specials"], ["units", "Units available"]];
  const chips = h("div", { class: "filters" });
  const grid = h("div", { class: "multiples" });
  const drawTrends = () => {
    const key = { listed: "min_price", net: "min_effective", units: "units" }[trend.mode];
    const isMoney = trend.mode !== "units";
    chips.replaceChildren(...modes.map(([k, label]) =>
      h("button", { class: "chip", "aria-pressed": String(trend.mode === k), onclick: () => { trend.mode = k; drawTrends(); } }, label)));
    const seriesOf = (c) => {
      const byDate = Object.fromEntries((c.history || []).map((p) => [p.date, p[key] ?? (key === "min_effective" ? p.min_price : null)]));
      return dates.map((d) => byDate[d] ?? null);
    };
    const all = complexes.flatMap(seriesOf).filter((v) => v != null);
    const lo = Math.min(...all), hi = Math.max(...all), pad = Math.max((hi - lo) * 0.08, isMoney ? 25 : 1);
    const yMin = all.length ? Math.max(0, Math.floor((lo - pad) / (isMoney ? 50 : 1)) * (isMoney ? 50 : 1)) : undefined;
    const yMax = all.length ? Math.ceil((hi + pad) / (isMoney ? 50 : 1)) * (isMoney ? 50 : 1) : undefined;
    const pending = [];
    grid.replaceChildren(...complexes.map((c) => {
      const data = seriesOf(c);
      const latest = [...data].reverse().find((v) => v != null);
      const unpriced = isMoney && latest == null && c.units;
      const canvas = h("canvas", { role: "img", "aria-label": `${c.name}: ${modes.find((m) => m[0] === trend.mode)[1].toLowerCase()} over time` });
      if (!unpriced && latest != null) pending.push(() => lineChart(canvas, dates, [{ label: c.name, colorIndex: 0, data }], { money: isMoney, yMin, yMax, compact: true }));
      return h("div", { class: "mini" },
        h("div", { class: "mini-head" },
          h("a", { href: `complex.html?c=${encodeURIComponent(c.slug)}` }, c.name),
          h("span", { class: "num mini-value" }, unpriced ? "Call" : latest == null ? "—" : isMoney ? money(latest) : latest)),
        unpriced ? h("div", { class: "mini-empty muted small" }, "Prices not published")
          : latest == null ? h("div", { class: "mini-empty muted small" }, "No data yet")
          : h("div", { class: "mini-chart" }, canvas));
    }));
    pending.forEach((f) => f());
  };
  add(root,
    h("div", { class: "card stack" },
      h("h2", {}, "Trends"), chips, grid,
      h("p", { class: "note" }, dates.length < 2
        ? "History builds up with each scheduled pull — trend lines appear after the second one. All cards share one scale."
        : "All cards share one scale, so heights compare directly across complexes."),
    ),
  );
  drawTrends();
}

// ---------- complex detail page ----------
function describeTerms(t) {
  const parts = [];
  if (t.months_free) parts.push(`${+t.months_free.toFixed(2)} month${t.months_free === 1 ? "" : "s"} free`);
  if (t.one_time_off) parts.push(`${money(t.one_time_off)} off once`);
  if (t.monthly_off) parts.push(`${money(t.monthly_off)} off per month`);
  return `Read as: ${parts.join(" + ")}${t.caveats.length ? " — " + t.caveats.join(", ") : ""}.`;
}

async function renderComplex() {
  const slug = new URLSearchParams(location.search).get("c");
  const root = document.getElementById("app");
  if (!slug) { add(root, h("p", {}, "No complex selected. ", h("a", { href: "./" }, "Back to overview"))); return; }
  const [d, { complexes }] = await Promise.all([getJSON(`data/${encodeURIComponent(slug)}.json`), getJSON("data/summary.json")]);
  const s = complexes.find((c) => c.slug === slug) || {};
  document.title = `${d.name} · Apartments`;
  document.getElementById("title").textContent = d.name;
  document.getElementById("updated").textContent = `Last pull ${fmtDate(d.date)}`;

  // Header
  add(root, 
    h("div", { class: "muted" },
      [d.property.address, d.property.phone].filter(Boolean).join(" · "), " · ",
      h("a", { href: d.url, target: "_blank", rel: "noopener" }, "Official site ↗")),
    d.stale ? h("div", { class: "banner" }, `The latest pull failed (${d.error || "unknown error"}). Showing data from ${fmtDate(d.date)}.`) : null,
  );

  const unitsByPlan = {};
  for (const u of d.units) (unitsByPlan[u.floorplan_code] ||= []).push(u);
  const today = d.date;
  const hasBuilding = d.units.some((u) => u.building), hasFloor = d.units.some((u) => u.floor);
  const hasNet = d.floorplans.some((f) => f.effective_min != null && f.effective_min < f.rent_min);
  const hasTotal = d.units.some((u) => u.total_price);
  const totalBasis = d.price_basis === "total";

  // Tiles
  const availPlans = d.floorplans.filter((f) => f.units_available > 0);
  add(root, 
    h("div", { class: "tiles" },
      h("div", { class: "card tile" }, h("div", { class: "label" }, "Units available"), h("div", { class: "value num" }, s.units ?? "—"), h("div", { class: "sub" }, deltaEl(s.units_delta) || "")),
      h("div", { class: "card tile" }, h("div", { class: "label" }, totalBasis ? "Lowest price (incl. fees)" : "Lowest price"),
        h("div", { class: "value num" }, s.priced === false ? "Call" : money(s.min_price)),
        h("div", { class: "sub" }, s.priced === false ? "This site doesn't publish prices" : [deltaEl(s.min_price_delta, { isPrice: true }) || "",
          netEl(s.min_effective, s.min_price), s.min_total && !totalBasis ? h("div", { class: "muted" }, `${money(s.min_total)} total/mo`) : null])),
      h("div", { class: "card tile" }, h("div", { class: "label" }, "Floorplans with availability"), h("div", { class: "value num" }, `${availPlans.length} / ${d.floorplans.length}`)),
    ),
  );

  // Filters
  const bedOptions = [...new Set(d.floorplans.map((f) => f.beds))].sort((a, b) => (a ?? 99) - (b ?? 99));
  const state = { beds: null, showAll: false, sort: "rent_min", dir: 1 };
  const filterRow = h("div", { class: "filters" });
  const tbody = h("tbody");
  const drawFilters = () => {
    filterRow.replaceChildren(
      ...[null, ...bedOptions].map((b) =>
        h("button", { class: "chip", "aria-pressed": String(state.beds === b), onclick: () => { state.beds = b; drawFilters(); drawTable(); } }, b === null ? "All" : bedLabel(b))),
      h("label", { class: "toggle" },
        h("input", { type: "checkbox", checked: state.showAll, onchange: (e) => { state.showAll = e.target.checked; drawTable(); } }),
        "Show plans with no availability"),
    );
  };

  const columns = [
    { key: "name", label: "Floorplan" },
    { key: "beds", label: "Bed / Bath", r: false },
    { key: "sqft", label: "Sq ft", r: true, hideSm: true },
    { key: "rent_min", label: "From", r: true },
    hasNet && { key: "effective_min", label: "Net", r: true },
    { key: "units_available", label: "Units", r: true },
    { key: "earliest_available", label: "Earliest", r: false },
  ].filter(Boolean);
  const thead = h("thead");
  const drawHead = () => {
    thead.replaceChildren(h("tr", {},
      columns.map((c) => h("th", {
        class: `sortable ${c.r ? "r" : ""} ${c.hideSm ? "hide-sm" : ""}`,
        "aria-sort": state.sort === c.key ? (state.dir > 0 ? "ascending" : "descending") : null,
        onclick: () => { state.dir = state.sort === c.key ? -state.dir : 1; state.sort = c.key; drawHead(); drawTable(); },
      }, c.label)),
      h("th", { class: "hide-sm" }, "Trend"), h("th", { class: "hide-sm" }, "Specials")));
  };

  const caveatText = (t) => (t.caveats.length ? t.caveats.join(" · ") : "");
  const specialBadge = (t) => h("span", {
    class: `badge ${t.parsed ? "special" : ""}`,
    title: [t.title, t.description, t.parsed ? caveatText(t) : "Terms not understood — not included in net rent"].filter(Boolean).join("\n"),
  }, t.title, t.parsed ? "" : " ?", t.caveats.length && t.parsed ? h("span", { class: "caveat" }, ` · ${caveatText(t)}`) : null);
  const unitNetEl = (u) => {
    const e = u.effective;
    if (!e) return h("span", { class: "muted" }, "—");
    const lines = [
      e.applied.length ? `Applied: ${e.applied.join(", ")}` : "No specials apply",
      `${e.lease_months}-month lease${e.lease_assumed ? " (assumed)" : ""}`,
      ...e.skipped.map((x) => `Not applied — ${x}`),
      e.uncertain ? "Special is for select units only; ask whether this unit qualifies." : null,
    ].filter(Boolean);
    if (!e.applied.length) return h("span", { class: "muted", title: lines.join("\n") }, "n/a");
    return h("span", { title: lines.join("\n") }, h("strong", {}, money(e.rent)), e.uncertain ? " *" : "");
  };
  const listedEl = (hist) => {
    if (!hist) return "—";
    if (hist.is_new) return h("span", { class: "badge new" }, "New");
    // Units already listed at the first pull have been on the market at least this long.
    const sinceStart = hist.first_seen === d.dates[0];
    if (sinceStart && hist.days_listed === 0) return h("span", { class: "muted", title: "Listed when tracking started" }, "—");
    return h("span", { title: `First seen ${fmtDate(hist.first_seen)}${sinceStart ? " (when tracking started)" : ""}` },
      weeksLabel(hist.days_listed) + (sinceStart ? "+" : ""));
  };
  const priceChangeEl = (hist) => {
    if (!hist || !hist.price_changes) return h("span", { class: "muted" }, "—");
    const title = hist.price_history.map((p) => `${fmtDate(p.date)}: ${money(p.price)}`).join("\n");
    const up = hist.price_change > 0;
    return h("span", { class: `delta ${up ? "up" : "down"}`, style: "margin-left:0", title },
      `${up ? "▲" : "▼"} ${money(Math.abs(hist.price_change))}`,
      h("span", { class: "muted" }, ` (${hist.price_changes}×)`));
  };
  const availLabel = (iso) => (!iso ? "—" : iso <= today ? "Now" : fmtDate(iso));
  const open = new Set();
  const drawTable = () => {
    let plans = d.floorplans.filter((f) => (state.showAll || f.units_available > 0) && (state.beds === null || f.beds === state.beds));
    plans.sort((a, b) => {
      const av = a[state.sort], bv = b[state.sort];
      if (av == null && bv == null) return 0;
      if (av == null) return 1; if (bv == null) return -1;
      return (av < bv ? -1 : av > bv ? 1 : 0) * state.dir;
    });
    const rows = [];
    for (const f of plans) {
      const units = (unitsByPlan[f.code] || []).slice().sort((a, b) => (a.price ?? 1e9) - (b.price ?? 1e9));
      const hist = (d.floorplan_history[f.code] || []).map((p) => p.rent_min);
      const isOpen = open.has(f.code);
      const toggle = () => { if (!units.length) return; isOpen ? open.delete(f.code) : open.add(f.code); drawTable(); };
      rows.push(h("tr", {
        class: `fp-row ${f.units_available ? "" : "unavailable"} ${units.length ? "" : "no-units"} ${isOpen ? "open" : ""}`,
        tabindex: units.length ? "0" : null, "aria-expanded": units.length ? String(isOpen) : null,
        onclick: toggle, onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } },
      },
        h("td", {}, f.image_url ? h("img", { class: "fp-thumb hide-sm", src: f.image_url, alt: "", loading: "lazy" }) : null, h("strong", {}, f.name)),
        h("td", {}, `${bedLabel(f.beds)} / ${f.baths ?? "—"} BA`),
        h("td", { class: "r num hide-sm" }, f.sqft ? f.sqft.toLocaleString() : "—"),
        h("td", { class: "r num" }, f.units_available ? priceOrCall(f.rent_min, f.units_available) : "—",
          f.units_available && f.rent_max && f.rent_max !== f.rent_min ? h("span", { class: "muted small" }, ` – ${money(f.rent_max)}`) : null,
          f.units_available && f.total_min && !totalBasis ? h("div", { class: "muted small", title: "Base rent plus required monthly fees" }, `${money(f.total_min)} total`) : null),
        hasNet && h("td", { class: "r num" }, f.units_available && f.effective_min != null && f.effective_min < f.rent_min
          ? h("strong", { title: "Lowest effective monthly rent after specials" }, money(f.effective_min)) : h("span", { class: "muted" }, "—")),
        h("td", { class: "r num" }, f.units_available || h("span", { class: "muted" }, "0")),
        h("td", {}, f.units_available ? availLabel(f.earliest_available) : "—"),
        h("td", { class: "hide-sm" }, sparkline(hist, { width: 70, height: 22 })),
        h("td", { class: "hide-sm specials-cell" }, (f.special_terms || []).map((t) => specialBadge(t))),
      ));
      if (isOpen) {
        rows.push(h("tr", { class: "units-row" }, h("td", { colspan: columns.length + 2 },
          h("table", {},
            h("thead", {}, h("tr", {}, h("th", {}, "Unit"), hasBuilding && h("th", {}, "Building"), hasFloor && h("th", {}, "Floor"), h("th", { class: "r" }, totalBasis ? "Price (incl. fees)" : "Price"), hasTotal && h("th", { class: "r", title: "Base rent plus required monthly fees" }, "Total/mo"), hasNet && h("th", { class: "r" }, "Net"), h("th", { class: "r" }, "Sq ft"), h("th", {}, "Available"), h("th", {}, "Listed"), h("th", {}, "Price change"), h("th", {}, ""))),
            h("tbody", {}, units.map((u) => h("tr", {},
              h("td", { class: "num" }, u.unit_number), hasBuilding && h("td", {}, u.building || "—"), hasFloor && h("td", {}, u.floor || "—"),
              h("td", { class: "r num" }, priceOrCall(u.price, 1)),
              hasTotal && h("td", { class: "r num muted" }, u.total_price ? money(u.total_price) : "—"),
              hasNet && h("td", { class: "r num" }, unitNetEl(u)),
              h("td", { class: "r num" }, u.sqft ? u.sqft.toLocaleString() : "—"),
              h("td", {}, availLabel(u.available_date)),
              h("td", {}, listedEl(u.history)),
              h("td", { class: "num" }, priceChangeEl(u.history)),
              h("td", {}, u.apply_url ? h("a", { href: u.apply_url, target: "_blank", rel: "noopener", onclick: (e) => e.stopPropagation() }, "Apply ↗") : ""),
            )))))));
      }
    }
    if (!rows.length) rows.push(h("tr", {}, h("td", { colspan: columns.length + 2, class: "muted" }, "No floorplans match.")));
    tbody.replaceChildren(...rows);
  };

  drawFilters(); drawHead(); drawTable();
  const uniqueSpecials = [...new Map(d.floorplans.flatMap((f) => f.special_terms || []).map((t) => [t.title + t.description, t])).values()];
  if (uniqueSpecials.length) {
    const lease = d.floorplans.map((f) => f.lease_months).find(Boolean);
    add(root, h("div", { class: "card stack" },
      h("h2", {}, "Current specials"),
      uniqueSpecials.map((t) => h("div", { class: "special-row" },
        h("div", {}, h("strong", {}, t.title), t.parsed ? null : h("span", { class: "badge", style: "margin-left:8px" }, "not included in net rent")),
        t.description ? h("div", { class: "muted small" }, t.description) : null,
        t.parsed ? h("div", { class: "small" }, describeTerms(t)) : null)),
      h("p", { class: "note" }, lease
        ? `Prices are quoted for a ${lease}-month lease, so net rent spreads the discount over ${lease} months.`
        : "The site doesn't say which lease term prices are for; net rent assumes 12 months."),
    ));
  }
  add(root, h("div", { class: "card stack" },
    h("h2", {}, "Floorplans"), filterRow,
    h("div", { class: "table-scroll" }, h("table", {}, thead, tbody)),
    h("p", { class: "note" }, "Click a floorplan to see its available units. “From” is the lowest listed price; “Net” is the lowest effective monthly rent after specials. Hover a unit's net rent for how it was calculated (* = the special is for select units only, so confirm the unit qualifies). The trend shows that plan's lowest listed price at each pull."),
    totalBasis ? h("p", { class: "note" }, "This site only shows a “Total Monthly Leasing Price”, which already includes required monthly fees, so its prices run slightly higher than base rent elsewhere.") : null,
    hasTotal && !totalBasis ? h("p", { class: "note" }, "Prices are base rent. “Total/mo” adds the required monthly fees the site lists (e.g. trash, pest control).") : null,
    d.units.length && d.units.every((u) => u.price == null) ? h("p", { class: "note" }, "This site lists available units but doesn't publish prices (“Call”).") : null,
    d.gone_units && d.gone_units.length ? h("p", { class: "note" },
      `No longer listed since ${fmtDate(d.gone_units[0].last_seen)}: `,
      d.gone_units.map((g) => `${g.building ? g.building + " #" : "#"}${g.unit_number} (${money(g.last_price)})`).join(", ")) : null,
  ));

  // Price history by bedroom count (few series → readable; per-plan trends live in the table)
  const bedKeys = sortBedKeys(d.bed_history.flatMap((p) => Object.keys(p.by_beds)));
  const bedSeries = (key) => bedKeys.map((k, i) => ({
    label: k, colorIndex: i,
    data: d.bed_history.map((p) => (p.by_beds[k] ? p.by_beds[k][key] : null)),
  }));
  const series = bedSeries("min_price");
  const cxMode = { mode: "listed" };
  const canvas = h("canvas", { role: "img", "aria-label": "Lowest price over time by bedroom count" });
  add(root, h("div", { class: "card" },
    h("h2", {}, "Lowest price by bedroom count"),
    priceModeChips(cxMode, () => lineChart(canvas, d.dates, bedSeries(cxMode.mode === "net" ? "min_effective" : "min_price"))),
    legendEl(series), h("div", { class: "chart-box" }, canvas),
    d.dates.length < 2 ? h("p", { class: "note" }, "History builds up with each scheduled pull — trend lines appear after the second one.") : null,
  ));
  lineChart(canvas, d.dates, series);
}

// ---------- boot ----------
const page = document.body.dataset.page;
(page === "complex" ? renderComplex() : renderOverview()).catch((err) => {
  console.error(err);
  document.getElementById("app").append(h("div", { class: "banner" }, `Couldn't load data: ${err.message}`));
});
