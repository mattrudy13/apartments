/* Apartment tracker front end. Data comes from site/data/*.json (written by build.py). */

// ---------- helpers ----------
const money = (n) => (n == null ? "—" : "$" + Math.round(n).toLocaleString("en-US"));
const fmtDate = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};
const shortDate = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" });
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
function lineChart(canvas, labels, series, { money: isMoney = true } = {}) {
  const make = () => {
    const text2 = cssVar("--text-2"), grid = cssVar("--grid"), surface = cssVar("--surface");
    return new Chart(canvas, {
      type: "line",
      data: {
        labels: labels.map(shortDate),
        datasets: series.map((s) => ({
          label: s.label, data: s.data, spanGaps: true,
          borderColor: seriesColor(s.colorIndex), backgroundColor: seriesColor(s.colorIndex),
          borderWidth: 2, pointRadius: labels.length > 12 ? 0 : 4, pointHoverRadius: 5,
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
          x: { grid: { display: false }, ticks: { color: text2, maxRotation: 0, autoSkipPadding: 16 }, border: { color: grid } },
          y: {
            grid: { color: grid }, border: { display: false },
            ticks: { color: text2, callback: (v) => (isMoney ? money(v) : v), maxTicksLimit: 5, precision: 0 },
            grace: "10%",
          },
        },
      },
      plugins: [crosshair],
    });
  };
  const entry = { make, chart: make() };
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
  const colorIndex = Object.fromEntries(complexes.map((c, i) => [c.slug, i])); // color follows the complex

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
    ),
  );

  // Table
  const bedKeys = [...new Set(complexes.flatMap((c) => Object.keys(c.by_beds || {})))].sort();
  const rows = complexes.map((c) =>
    h("tr", {},
      h("td", { class: "name-cell" },
        h("a", { href: `complex.html?c=${encodeURIComponent(c.slug)}` }, c.name),
        c.stale ? h("span", { class: "badge warn", style: "margin-left:8px", title: c.error || "" }, "stale") : null,
        h("div", { class: "addr" }, c.address || "")),
      h("td", { class: "r num" }, c.units ?? "—", deltaEl(c.units_delta)),
      h("td", { class: "r num" }, money(c.min_price), deltaEl(c.min_price_delta, { isPrice: true })),
      bedKeys.map((k) => {
        const b = (c.by_beds || {})[k];
        return h("td", { class: "r num hide-sm" }, b ? h("span", {}, money(b.min_price), h("span", { class: "muted small" }, ` (${b.units})`)) : h("span", { class: "muted" }, "—"));
      }),
      h("td", { class: "hide-sm" }, sparkline((c.history || []).map((p) => p.min_price), { color: seriesColor(colorIndex[c.slug]) })),
      h("td", { class: "muted small" }, fmtDate(c.date)),
    ),
  );
  add(root, 
    h("div", { class: "card" },
      h("h2", {}, "Availability"),
      h("div", { class: "table-scroll" },
        h("table", {},
          h("thead", {}, h("tr", {},
            h("th", {}, "Complex"), h("th", { class: "r" }, "Units"), h("th", { class: "r" }, "Lowest price"),
            bedKeys.map((k) => h("th", { class: "r hide-sm", title: "Lowest price (units available)" }, k)),
            h("th", { class: "hide-sm" }, "Price trend"), h("th", {}, "Updated"))),
          h("tbody", {}, rows))),
      h("p", { class: "note" }, "Deltas compare with the previous pull. Bedroom columns show the lowest price with units available in parentheses."),
    ),
  );

  // History charts: complexes × dates
  const dates = [...new Set(complexes.flatMap((c) => (c.history || []).map((p) => p.date)))].sort();
  const seriesFor = (key) => complexes.map((c) => {
    const byDate = Object.fromEntries((c.history || []).map((p) => [p.date, p[key]]));
    return { label: c.name, colorIndex: colorIndex[c.slug], data: dates.map((d) => byDate[d] ?? null) };
  });
  const priceSeries = seriesFor("min_price"), unitSeries = seriesFor("units");
  const priceCanvas = h("canvas", { role: "img", "aria-label": "Lowest available price over time by complex" });
  const unitCanvas = h("canvas", { role: "img", "aria-label": "Units available over time by complex" });
  add(root, 
    h("div", { class: "grid-2" },
      h("div", { class: "card" }, h("h2", {}, "Lowest price over time"), legendEl(priceSeries), h("div", { class: "chart-box" }, priceCanvas)),
      h("div", { class: "card" }, h("h2", {}, "Units available over time"), legendEl(unitSeries), h("div", { class: "chart-box" }, unitCanvas)),
    ),
    dates.length < 2 ? h("p", { class: "note" }, "History builds up with each scheduled pull — trend lines appear after the second one.") : null,
  );
  lineChart(priceCanvas, dates, priceSeries);
  lineChart(unitCanvas, dates, unitSeries, { money: false });
}

// ---------- complex detail page ----------
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

  // Tiles
  const availPlans = d.floorplans.filter((f) => f.units_available > 0);
  add(root, 
    h("div", { class: "tiles" },
      h("div", { class: "card tile" }, h("div", { class: "label" }, "Units available"), h("div", { class: "value num" }, s.units ?? "—"), h("div", { class: "sub" }, deltaEl(s.units_delta) || "")),
      h("div", { class: "card tile" }, h("div", { class: "label" }, "Lowest price"), h("div", { class: "value num" }, money(s.min_price)), h("div", { class: "sub" }, deltaEl(s.min_price_delta, { isPrice: true }) || "")),
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
    { key: "units_available", label: "Units", r: true },
    { key: "earliest_available", label: "Earliest", r: false },
  ];
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
        h("td", { class: "r num" }, f.units_available ? money(f.rent_min) : "—",
          f.units_available && f.rent_max && f.rent_max !== f.rent_min ? h("span", { class: "muted small" }, ` – ${money(f.rent_max)}`) : null),
        h("td", { class: "r num" }, f.units_available || h("span", { class: "muted" }, "0")),
        h("td", {}, f.units_available ? availLabel(f.earliest_available) : "—"),
        h("td", { class: "hide-sm" }, sparkline(hist, { width: 70, height: 22 })),
        h("td", { class: "hide-sm" }, f.specials.map((sp) => h("span", { class: "badge special" }, sp))),
      ));
      if (isOpen) {
        rows.push(h("tr", { class: "units-row" }, h("td", { colspan: columns.length + 2 },
          h("table", {},
            h("thead", {}, h("tr", {}, h("th", {}, "Unit"), hasBuilding && h("th", {}, "Building"), hasFloor && h("th", {}, "Floor"), h("th", { class: "r" }, "Price"), h("th", { class: "r" }, "Sq ft"), h("th", {}, "Available"), h("th", {}, ""))),
            h("tbody", {}, units.map((u) => h("tr", {},
              h("td", { class: "num" }, u.unit_number), hasBuilding && h("td", {}, u.building || "—"), hasFloor && h("td", {}, u.floor || "—"),
              h("td", { class: "r num" }, money(u.price)), h("td", { class: "r num" }, u.sqft ? u.sqft.toLocaleString() : "—"),
              h("td", {}, availLabel(u.available_date)),
              h("td", {}, u.apply_url ? h("a", { href: u.apply_url, target: "_blank", rel: "noopener", onclick: (e) => e.stopPropagation() }, "Apply ↗") : ""),
            )))))));
      }
    }
    if (!rows.length) rows.push(h("tr", {}, h("td", { colspan: columns.length + 2, class: "muted" }, "No floorplans match.")));
    tbody.replaceChildren(...rows);
  };

  drawFilters(); drawHead(); drawTable();
  add(root, h("div", { class: "card stack" },
    h("h2", {}, "Floorplans"), filterRow,
    h("div", { class: "table-scroll" }, h("table", {}, thead, tbody)),
    h("p", { class: "note" }, "Click a floorplan to see its available units. “From” is the lowest listed price; the trend shows that plan's lowest price at each pull."),
  ));

  // Price history by bedroom count (few series → readable; per-plan trends live in the table)
  const bedKeys = [...new Set(d.bed_history.flatMap((p) => Object.keys(p.by_beds)))].sort();
  const series = bedKeys.map((k, i) => ({
    label: k, colorIndex: i,
    data: d.bed_history.map((p) => (p.by_beds[k] ? p.by_beds[k].min_price : null)),
  }));
  const canvas = h("canvas", { role: "img", "aria-label": "Lowest price over time by bedroom count" });
  add(root, h("div", { class: "card" },
    h("h2", {}, "Lowest price by bedroom count"), legendEl(series), h("div", { class: "chart-box" }, canvas),
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
