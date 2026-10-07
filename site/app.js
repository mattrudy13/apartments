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

// ---------- price per sq ft ----------
const ppsf = (price, sqft) => (price != null && sqft ? price / sqft : null);
const fmtPpsf = (n) => (n == null ? "—" : "$" + n.toFixed(2));
/** "$1.85" cell content; tooltip shows the net $/sq ft when specials lower the price. */
function ppsfEl(price, net, sqft) {
  const v = ppsf(price, sqft);
  if (v == null) return h("span", { class: "muted" }, "—");
  const n = net != null && net < price ? ppsf(net, sqft) : null;
  return h("span", { title: n != null ? `Net of specials: ${fmtPpsf(n)}/sq ft` : null }, fmtPpsf(v));
}

// ---------- unit history cells (complex page and shortlist) ----------
const availLabel = (iso, today) => (!iso ? "—" : iso <= today ? "Now" : fmtDate(iso));
/** "New", "3 wk" or "3 wk+" (units already listed when tracking started). */
function listedEl(hist, historyStart) {
  if (!hist) return "—";
  if (hist.is_new) return h("span", { class: "badge new" }, "New");
  // Units already listed at the first pull have been on the market at least this long.
  const sinceStart = hist.first_seen === historyStart;
  if (sinceStart && hist.days_listed === 0) return h("span", { class: "muted", title: "Listed when tracking started" }, "—");
  return h("span", { title: `First seen ${fmtDate(hist.first_seen)}${sinceStart ? " (when tracking started)" : ""}` },
    weeksLabel(hist.days_listed) + (sinceStart ? "+" : ""));
}
function priceChangeEl(hist) {
  if (!hist || !hist.price_changes) return h("span", { class: "muted" }, "—");
  const title = hist.price_history.map((p) => `${fmtDate(p.date)}: ${money(p.price)}`).join("\n");
  const up = hist.price_change > 0;
  return h("span", { class: `delta ${up ? "up" : "down"}`, style: "margin-left:0", title },
    `${up ? "▲" : "▼"} ${money(Math.abs(hist.price_change))}`,
    h("span", { class: "muted" }, ` (${hist.price_changes}×)`));
}

// ---------- shortlist (starred units and floorplans, per browser) ----------
// Entries: {id, kind: "unit"|"plan", slug, complex, code, unitKey?, label, lastPrice, addedAt}.
// Unit ids use build.unit_key ("building#unit"), since unit numbers repeat across buildings.
const unitKey = (u) => `${u.building || ""}#${u.unit_number}`;
const unitId = (slug, u) => `${slug}|u|${unitKey(u)}`;
const planId = (slug, code) => `${slug}|fp|${code}`;
const shortlist = (() => {
  const KEY = "apartments.shortlist.v1";
  let mem = [];  // fallback when storage is blocked (private mode, thumbnails)
  const load = () => {
    try { const v = JSON.parse(localStorage.getItem(KEY) || "[]"); return Array.isArray(v) ? v : []; } catch { return mem; }
  };
  const save = (list) => { mem = list; try { localStorage.setItem(KEY, JSON.stringify(list)); } catch { /* keep in memory */ } };
  return {
    all: load,
    has: (id) => load().some((e) => e.id === id),
    toggle(entry) {
      const list = load(), i = list.findIndex((e) => e.id === entry.id);
      if (i >= 0) list.splice(i, 1); else list.push({ ...entry, addedAt: new Date().toISOString().slice(0, 10) });
      save(list);
    },
    remove: (id) => save(load().filter((e) => e.id !== id)),
    /** Adds entries not already present; returns how many were new. */
    merge(entries) {
      const list = load(), have = new Set(list.map((e) => e.id));
      const fresh = entries.filter((e) => e && typeof e.id === "string" && e.slug && !have.has(e.id));
      save(list.concat(fresh));
      return fresh.length;
    },
  };
})();
const unitEntry = (d, u, plan) => ({
  id: unitId(d.slug, u), kind: "unit", slug: d.slug, complex: d.name, code: u.floorplan_code, unitKey: unitKey(u),
  label: `#${u.unit_number}${u.building ? " · Bldg " + u.building : ""}${plan ? " · " + plan.name : ""}`, lastPrice: u.price,
});
const planEntry = (d, f) => ({
  id: planId(d.slug, f.code), kind: "plan", slug: d.slug, complex: d.name, code: f.code, label: f.name, lastPrice: f.rent_min,
});

/** ☆/★ toggle. Stops the click so it doesn't also expand a floorplan row. */
function starBtn(entry, onChange) {
  const on = shortlist.has(entry.id);
  return h("button", {
    class: "star", type: "button", "aria-pressed": String(on),
    "aria-label": `${on ? "Remove" : "Add"} ${entry.complex} ${entry.label} ${on ? "from" : "to"} shortlist`,
    title: on ? "Remove from shortlist" : "Add to shortlist",
    onclick: (e) => { e.stopPropagation(); shortlist.toggle(entry); onChange(); },
    onkeydown: (e) => e.stopPropagation(),
  }, on ? "★" : "☆");
}

// Share links carry the entries as base64url JSON (?shortlist=...), to move a list between devices.
const b64url = (s) => btoa(unescape(encodeURIComponent(s))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const unb64url = (s) => decodeURIComponent(escape(atob(s.replace(/-/g, "+").replace(/_/g, "/"))));
const shareUrl = () => {
  const slim = shortlist.all().map(({ addedAt, ...e }) => e);
  return `${location.origin}${location.pathname}?shortlist=${b64url(JSON.stringify(slim))}`;
};
/** Imports ?shortlist= from the URL (then strips it); returns how many entries were added, or null. */
function importSharedShortlist() {
  const params = new URLSearchParams(location.search);
  const raw = params.get("shortlist");
  if (!raw) return null;
  let added = 0;
  try { const v = JSON.parse(unb64url(raw)); if (Array.isArray(v)) added = shortlist.merge(v); } catch { added = 0; }
  params.delete("shortlist");
  const qs = params.toString();
  history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
  return added;
}

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

// ---------- overview: shortlist card ----------
/** Matches a shortlist entry to the current data; `gone` when the unit/plan (or complex) is no longer listed. */
function resolveEntry(e, d) {
  const base = { entry: e, d, gone: true };
  if (!d) return base;
  const plans = Object.fromEntries(d.floorplans.map((f) => [f.code, f]));
  if (e.kind === "plan") {
    const f = plans[e.code];
    if (!f) return base;
    return { ...base, gone: false, plan: f, empty: !f.units_available, price: f.rent_min, net: f.effective_min, total: f.total_min,
      sqft: f.sqft, available: f.earliest_available, units: f.units_available };
  }
  const u = d.units.find((x) => unitKey(x) === e.unitKey);
  if (!u) return base;
  const f = plans[u.floorplan_code] || {};
  return { ...base, gone: false, plan: f, unit: u, price: u.price, net: u.effective && u.effective.applied.length ? u.effective.rent : null,
    total: u.total_price, sqft: u.sqft || f.sqft, available: u.available_date, units: 1 };
}

async function shortlistCard() {
  const card = h("div", { class: "card stack" });
  const cache = {};  // slug -> complex data (null when it can't be loaded)
  const draw = async () => {
    const entries = shortlist.all();
    if (!entries.length) { card.hidden = true; return; }
    card.hidden = false;
    await Promise.all([...new Set(entries.map((e) => e.slug))].filter((s) => !(s in cache)).map((s) =>
      getJSON(`data/${encodeURIComponent(s)}.json`).then((d) => { cache[s] = d; }, () => { cache[s] = null; })));
    const rows = entries.map((e) => resolveEntry(e, cache[e.slug]));
    // Cheapest available first; "Call" prices, empty plans, then items no longer listed go last.
    const rank = (r) => (r.gone ? 3 : r.empty ? 2 : r.price == null ? 1 : 0);
    rows.sort((a, b) => rank(a) - rank(b) || (a.price ?? 0) - (b.price ?? 0) || a.entry.complex.localeCompare(b.entry.complex));
    const totalBasis = (r) => r.d && r.d.price_basis === "total";
    const shareBtn = h("button", { class: "chip", type: "button", onclick: async () => {
      const url = shareUrl();
      try { await navigator.clipboard.writeText(url); shareBtn.textContent = "Link copied"; setTimeout(() => { shareBtn.textContent = "Copy share link"; }, 2000); }
      catch { shareBox.replaceChildren(h("input", { class: "share-url", readonly: true, value: url, onfocus: (ev) => ev.target.select() })); shareBox.querySelector("input").focus(); }
    }, title: "Copy a link that adds these items to the shortlist in another browser" }, "Copy share link");
    const shareBox = h("div");
    card.replaceChildren(
      h("div", { class: "card-head" }, h("h2", {}, `Shortlist `, h("span", { class: "muted" }, `(${entries.length})`)), shareBtn),
      shareBox,
      h("div", { class: "table-scroll" }, h("table", {},
        h("thead", {}, h("tr", {}, h("th", {}, ""), h("th", {}, "Complex / item"), h("th", { class: "hide-sm" }, "Bed / Bath"), h("th", { class: "r hide-sm" }, "Sq ft"),
          h("th", { class: "r" }, "Price"), h("th", { class: "r", title: "Listed price per square foot; hover for net of specials" }, "$/sq ft"),
          h("th", {}, "Available"), h("th", { class: "hide-sm" }, "Listed"), h("th", { class: "hide-sm" }, "Price change"))),
        h("tbody", {}, rows.map((r) => {
          const e = r.entry, f = r.plan || {};
          const kindLabel = e.kind === "plan" ? `Plan ${e.label}` : `Unit ${e.label}`;
          const status = r.gone ? `No longer listed${e.lastPrice ? ` (last ${money(e.lastPrice)})` : ""}` : r.empty ? "No units available" : null;
          return h("tr", { class: r.gone || r.empty ? "dim" : "" },
            h("td", {}, starBtn(e, draw)),
            h("td", { class: "name-cell" },
              h("a", { href: `complex.html?c=${encodeURIComponent(e.slug)}` }, e.complex),
              h("div", { class: "addr" }, kindLabel, r.plan ? h("span", { class: "show-sm" }, ` · ${bedLabel(f.beds)}`) : null, status ? h("span", { class: "muted" }, ` · ${status}`) : null)),
            h("td", { class: "hide-sm" }, r.plan ? `${bedLabel(f.beds)} / ${f.baths ?? "—"} BA` : "—"),
            h("td", { class: "r num hide-sm" }, r.sqft ? r.sqft.toLocaleString() : "—"),
            h("td", { class: "r num" }, r.gone || r.empty ? "—" : [
              h("span", { title: totalBasis(r) ? "Includes required monthly fees" : null }, priceOrCall(r.price, r.units)),
              e.kind === "plan" && f.rent_max && f.rent_max !== f.rent_min ? h("span", { class: "muted small hide-sm" }, ` – ${money(f.rent_max)}`) : null,
              netEl(r.net, r.price),
              r.total && !totalBasis(r) ? h("div", { class: "muted small", title: "Base rent plus required monthly fees" }, `${money(r.total)} total`) : null]),
            h("td", { class: "r num" }, r.gone || r.empty ? "—" : ppsfEl(r.price, r.net, r.sqft)),
            h("td", {}, r.gone || r.empty ? "—" : availLabel(r.available, r.d.date)),
            h("td", { class: "hide-sm" }, r.unit ? listedEl(r.unit.history, r.d.history_start || r.d.dates[0]) : "—"),
            h("td", { class: "hide-sm" }, r.unit ? priceChangeEl(r.unit.history) : h("span", { class: "muted" }, "—")));
        })))),
      h("p", { class: "note" }, "Starred floorplans and units, saved in this browser. Prices are base rent where the site shows it. Plans show their lowest listed price. Use “Copy share link” to open this list on another device."),
    );
  };
  await draw();
  return card;
}

// ---------- overview page ----------
async function renderOverview() {
  const imported = importSharedShortlist();
  const { complexes } = await getJSON("data/summary.json");
  const root = document.getElementById("app");
  if (imported != null) {
    add(root, h("div", { class: "banner info" }, imported
      ? `Added ${imported} item${imported === 1 ? "" : "s"} to your shortlist from a shared link.`
      : "Everything in that shared link is already on your shortlist."));
  }

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

  add(root, await shortlistCard());

  // Table: sortable; defaults to cheapest first. Price sorts use the net price when specials lower it.
  const bedKeys = sortBedKeys(complexes.flatMap((c) => Object.keys(c.by_beds || {})));
  // "base": base rent (net when specials lower it). "total": total monthly incl. required fees
  // (net of specials) where the site lists fees; otherwise falls back to base, marked.
  const priceMode = { mode: "base" };
  const baseBest = (x) => (x ? (x.min_effective ?? x.min_price ?? null) : null);
  const totalBest = (x) => (x ? (x.min_total_net ?? x.min_total ?? null) : null);
  const bestPrice = (x) => (priceMode.mode === "total" ? (totalBest(x) ?? baseBest(x)) : baseBest(x));
  const sortValue = {
    name: (c) => c.name.toLowerCase(),
    units: (c) => c.units ?? null,
    price: (c) => bestPrice(c),
    ...Object.fromEntries(bedKeys.map((k) => [`bed:${k}`, (c) => bestPrice((c.by_beds || {})[k])])),
  };
  const tableState = { sort: "price", dir: 1 };
  const thead = h("thead"), tbody = h("tbody"), modeChips = h("div", { class: "filters" });
  const sortTh = (key, label, cls = "", title = null) => h("th", {
    class: `sortable ${cls}`, title,
    "aria-sort": tableState.sort === key ? (tableState.dir > 0 ? "ascending" : "descending") : null,
    onclick: () => { tableState.dir = tableState.sort === key ? -tableState.dir : 1; tableState.sort = key; drawTable(); },
  }, label);
  const noFees = () => h("div", { class: "muted small", title: "This site doesn't list its required monthly fees; showing base rent" }, "fees not listed");
  /** Price cell content for a complex or bedroom bucket in the current mode. */
  const priceCell = (x, units, { complex = false } = {}) => {
    if (priceMode.mode === "total" && x && x.min_total != null) {
      return [h("span", { title: "Total monthly: rent plus required monthly fees" }, money(x.min_total)), netEl(x.min_total_net, x.min_total)];
    }
    const showFeesNote = priceMode.mode === "total" && x && x.min_price != null;
    return [priceOrCall(x ? x.min_price : null, units), netEl(x && x.min_effective, x && x.min_price), showFeesNote ? noFees() : null,
      complex && priceMode.mode === "base" ? deltaEl(x.min_price_delta, { isPrice: true }) : null,
      complex && priceMode.mode === "base" && x.price_basis === "total" && x.min_price != null ? h("div", { class: "muted small", title: "This site only shows prices that include required monthly fees" }, "incl. fees") : null];
  };
  const checksBadge = (c) => (c.checks && c.checks.length
    ? h("span", { class: "badge warn", style: "margin-left:8px", title: "Data looks off:\n" + c.checks.join("\n") }, "check data") : null);
  const row = (c) => h("tr", {},
    h("td", { class: "name-cell" },
      h("a", { href: `complex.html?c=${encodeURIComponent(c.slug)}` }, c.name),
      c.stale ? h("span", { class: "badge warn", style: "margin-left:8px", title: c.error || "" }, "stale") : null,
      checksBadge(c),
      h("div", { class: "addr" }, c.address || "")),
    h("td", { class: "r num" }, c.units ?? "—", deltaEl(c.units_delta)),
    h("td", { class: "r num" }, priceCell(c, c.units, { complex: true })),
    bedKeys.map((k) => {
      const b = (c.by_beds || {})[k];
      return h("td", { class: "r num hide-sm" }, b ? [h("span", {}, priceCell(b, b.units)[0], h("span", { class: "muted small" }, ` (${b.units})`)), ...priceCell(b, b.units).slice(1)] : h("span", { class: "muted" }, "—"));
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
    modeChips.replaceChildren(...[["base", "Base rent"], ["total", "Total per month"]].map(([k, label]) =>
      h("button", { class: "chip", "aria-pressed": String(priceMode.mode === k), onclick: () => { priceMode.mode = k; drawTable(); } }, label)));
    thead.replaceChildren(h("tr", {},
      sortTh("name", "Complex"), sortTh("units", "Units", "r"), sortTh("price", priceMode.mode === "total" ? "Lowest total/mo" : "Lowest price", "r", "Sorted by net price when specials lower it"),
      bedKeys.map((k) => sortTh(`bed:${k}`, k, "r hide-sm", "Lowest price (units available); sorted by net price when specials lower it")),
      h("th", { class: "hide-sm" }, "Price trend"), h("th", {}, "Updated")));
    tbody.replaceChildren(...sorted.map(row));
  };
  drawTable();
  add(root,
    h("div", { class: "card stack" },
      h("h2", {}, "Availability"),
      modeChips,
      h("div", { class: "table-scroll" }, h("table", {}, thead, tbody)),
      h("p", { class: "note" }, "Click a column to sort; price columns sort by net price when specials lower it, and complexes without a price go last. Prices are base rent where the site shows it. Deltas compare with the previous pull. Bedroom columns show the lowest price with units available in parentheses. “Net” is the effective monthly rent after specials (e.g. months free) spread over the lease. “Call” means the complex lists units but doesn't publish prices. “Total per month” adds the required monthly fees a site lists (e.g. trash, pest control); sites that don't list fees show base rent, marked “fees not listed”. Star ☆ floorplans or units on a complex page to build a shortlist here."),
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
    d.checks && d.checks.length ? h("div", { class: "banner" },
      h("strong", {}, "Data looks off — double-check on the official site:"),
      h("ul", { style: "margin:6px 0 0 18px;padding:0" }, d.checks.map((r) => h("li", {}, r)))) : null,
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
  const state = { beds: null, showAll: false, starredOnly: false, sort: "rent_min", dir: 1 };
  const filterRow = h("div", { class: "filters" });
  const tbody = h("tbody");
  const closed = new Set();  // plans the user collapsed while "Starred only" auto-opens them
  const starredCount = () => shortlist.all().filter((e) => e.slug === d.slug).length;
  const drawFilters = () => {
    const n = starredCount();
    if (!n) state.starredOnly = false;
    filterRow.replaceChildren(
      ...[null, ...bedOptions].map((b) =>
        h("button", { class: "chip", "aria-pressed": String(state.beds === b), onclick: () => { state.beds = b; drawFilters(); drawTable(); } }, b === null ? "All" : bedLabel(b))),
      h("button", {
        class: "chip star-chip", "aria-pressed": String(state.starredOnly), disabled: !n,
        title: n ? "Show only starred floorplans and units" : "Star ☆ a floorplan or unit to use this filter",
        onclick: () => { state.starredOnly = !state.starredOnly; closed.clear(); drawFilters(); drawTable(); },
      }, `★ Starred only${n ? ` (${n})` : ""}`),
      h("label", { class: "toggle" },
        h("input", { type: "checkbox", checked: state.showAll, disabled: state.starredOnly, onchange: (e) => { state.showAll = e.target.checked; drawTable(); } }),
        "Show plans with no availability"),
    );
  };

  // Precomputed so the generic column sort handles it; only plans with units have a current price.
  for (const f of d.floorplans) f.ppsf = f.units_available ? ppsf(f.rent_min, f.sqft) : null;
  const columns = [
    { key: "name", label: "Floorplan" },
    { key: "beds", label: "Bed / Bath", r: false },
    { key: "sqft", label: "Sq ft", r: true, hideSm: true },
    { key: "rent_min", label: "From", r: true },
    { key: "ppsf", label: "$/sq ft", r: true, hideSm: true, title: "Lowest listed price per square foot; hover for net of specials" },
    hasNet && { key: "effective_min", label: "Net", r: true },
    { key: "units_available", label: "Units", r: true },
    { key: "earliest_available", label: "Earliest", r: false },
  ].filter(Boolean);
  const thead = h("thead");
  const drawHead = () => {
    thead.replaceChildren(h("tr", {},
      columns.map((c) => h("th", {
        class: `sortable ${c.r ? "r" : ""} ${c.hideSm ? "hide-sm" : ""}`, title: c.title,
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
  const historyStart = d.history_start || d.dates[0];
  const open = new Set();
  const planStarred = (f) => shortlist.has(planId(d.slug, f.code));
  const unitStarred = (u) => shortlist.has(unitId(d.slug, u));
  const onStar = () => { drawFilters(); drawTable(); };
  const drawTable = () => {
    const starredOnly = state.starredOnly && starredCount() > 0;
    let plans = d.floorplans.filter((f) => (state.beds === null || f.beds === state.beds) && (starredOnly
      ? planStarred(f) || (unitsByPlan[f.code] || []).some(unitStarred)
      : state.showAll || f.units_available > 0));
    plans.sort((a, b) => {
      const av = a[state.sort], bv = b[state.sort];
      if (av == null && bv == null) return 0;
      if (av == null) return 1; if (bv == null) return -1;
      return (av < bv ? -1 : av > bv ? 1 : 0) * state.dir;
    });
    const rows = [];
    for (const f of plans) {
      let units = (unitsByPlan[f.code] || []).slice().sort((a, b) => (a.price ?? 1e9) - (b.price ?? 1e9));
      // Starred only: show just the starred units, unless the whole plan is starred; open plans with starred units.
      const hasStarredUnits = starredOnly && units.some(unitStarred);
      if (hasStarredUnits && !planStarred(f)) units = units.filter(unitStarred);
      const hist = (d.floorplan_history[f.code] || []).map((p) => p.rent_min);
      const isOpen = open.has(f.code) || (hasStarredUnits && !closed.has(f.code));
      const toggle = () => {
        if (!units.length) return;
        if (isOpen) { open.delete(f.code); closed.add(f.code); } else { open.add(f.code); closed.delete(f.code); }
        drawTable();
      };
      rows.push(h("tr", {
        class: `fp-row ${f.units_available ? "" : "unavailable"} ${units.length ? "" : "no-units"} ${isOpen ? "open" : ""}`,
        tabindex: units.length ? "0" : null, "aria-expanded": units.length ? String(isOpen) : null,
        onclick: toggle, onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } },
      },
        h("td", { class: "fp-name" }, starBtn(planEntry(d, f), onStar),
          f.image_url ? h("img", { class: "fp-thumb hide-sm", src: f.image_url, alt: "", loading: "lazy" }) : null, h("strong", {}, f.name)),
        h("td", { class: "bed-cell" }, `${bedLabel(f.beds)} / ${f.baths ?? "—"} BA`),
        h("td", { class: "r num hide-sm" }, f.sqft ? f.sqft.toLocaleString() : "—"),
        h("td", { class: "r num" }, f.units_available ? priceOrCall(f.rent_min, f.units_available) : "—",
          f.units_available && f.rent_max && f.rent_max !== f.rent_min ? h("span", { class: "muted small hide-sm" }, ` – ${money(f.rent_max)}`) : null,
          f.units_available && f.total_min && !totalBasis ? h("div", { class: "muted small", title: "Base rent plus required monthly fees" }, `${money(f.total_min)} total`) : null,
          // Phones hide the $/sq ft column, so show it under the price instead.
          f.ppsf != null ? h("div", { class: "muted small show-sm" }, `${fmtPpsf(f.ppsf)}/sq ft`) : null),
        h("td", { class: "r num hide-sm" }, f.units_available ? ppsfEl(f.rent_min, f.effective_min, f.sqft) : h("span", { class: "muted" }, "—")),
        hasNet && h("td", { class: "r num" }, f.units_available && f.effective_min != null && f.effective_min < f.rent_min
          ? h("strong", { title: "Lowest effective monthly rent after specials" }, money(f.effective_min)) : h("span", { class: "muted" }, "—")),
        h("td", { class: "r num" }, f.units_available || h("span", { class: "muted" }, "0")),
        h("td", {}, f.units_available ? availLabel(f.earliest_available, today) : "—"),
        h("td", { class: "hide-sm" }, sparkline(hist, { width: 70, height: 22 })),
        h("td", { class: "hide-sm specials-cell" }, (f.special_terms || []).map((t) => specialBadge(t))),
      ));
      if (isOpen) {
        rows.push(h("tr", { class: "units-row" }, h("td", { colspan: columns.length + 2 },
          h("table", {},
            h("thead", {}, h("tr", {}, h("th", {}, "Unit"), hasBuilding && h("th", {}, "Building"), hasFloor && h("th", {}, "Floor"), h("th", { class: "r" }, totalBasis ? "Price (incl. fees)" : "Price"), hasTotal && h("th", { class: "r", title: "Base rent plus required monthly fees" }, "Total/mo"), hasNet && h("th", { class: "r" }, "Net"), h("th", { class: "r" }, "Sq ft"), h("th", { class: "r", title: "Listed price per square foot" }, "$/sq ft"), h("th", {}, "Available"), h("th", {}, "Listed"), h("th", {}, "Price change"), h("th", {}, ""))),
            h("tbody", {}, units.map((u) => h("tr", {},
              h("td", { class: "num unit-cell" }, starBtn(unitEntry(d, u, f), onStar), u.unit_number), hasBuilding && h("td", {}, u.building || "—"), hasFloor && h("td", {}, u.floor || "—"),
              h("td", { class: "r num" }, priceOrCall(u.price, 1)),
              hasTotal && h("td", { class: "r num muted" }, u.total_price ? money(u.total_price) : "—"),
              hasNet && h("td", { class: "r num" }, unitNetEl(u)),
              h("td", { class: "r num" }, u.sqft ? u.sqft.toLocaleString() : "—"),
              h("td", { class: "r num" }, ppsfEl(u.price, u.effective && u.effective.applied.length ? u.effective.rent : null, u.sqft || f.sqft)),
              h("td", {}, availLabel(u.available_date, today)),
              h("td", {}, listedEl(u.history, historyStart)),
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
    h("p", { class: "note" }, "Click a floorplan to see its available units. Star ☆ a floorplan or unit to add it to your shortlist on the overview (saved in this browser). “From” is the lowest listed price; “$/sq ft” is that price per square foot; “Net” is the lowest effective monthly rent after specials. Hover a unit's net rent for how it was calculated (* = the special is for select units only, so confirm the unit qualifies). The trend shows that plan's lowest listed price at each pull."),
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
