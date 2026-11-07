/* NFL Futures Tracker */
(() => {
  "use strict";

  const SHORT_SERIES = {
    "Pro Football: 2027 Champion": "Super Bowl",
    "Pro Football: 2027 AFC Champion": "AFC Champion",
    "Pro Football: 2027 NFC Champion": "NFC Champion",
    "Pro Football: Team to Make Postseason": "Make Playoffs",
    "Pro Football: AFC East Champion": "AFC East",
    "Pro Football: AFC North Champion": "AFC North",
    "Pro Football: AFC South Champion": "AFC South",
    "Pro Football: AFC West Champion": "AFC West",
    "Pro Football: NFC East Champion": "NFC East",
    "Pro Football: NFC North Champion": "NFC North",
    "Pro Football: NFC South Champion": "NFC South",
    "Pro Football: NFC West Champion": "NFC West",
    "Pro Football: 2026 MVP Winner": "MVP",
    "Pro Football: 2026-27 AP Offensive Player of the Year Winner": "Off. Player of Year",
    "Pro Football: 2026-27 AP Defensive Player of the Year Winner": "Def. Player of Year",
    "Pro Football: 2026-27 AP Offensive Rookie of the Year Winner": "Off. Rookie of Year",
    "Pro Football: 2026-27 AP Defensive Rookie of the Year Winner": "Def. Rookie of Year",
    "Pro Football: 2026-27 AP Coach of the Year Winner": "Coach of Year",
    "Pro Football: 2026-27 AP Comeback Player of the Year Winner": "Comeback Player",
  };
  const shortSeries = (s) => SHORT_SERIES[s] || s.replace(/^Pro Football:\s*/, "");

  // Categorical slots (validated dark-mode order) for time-series lines.
  const SERIES_COLORS = ["#74aef0", "#f0a35b", "#54c7a5", "#e8cf72", "#ed89c4", "#b1c98a", "#ad9cf0", "#ef8f8f"];
  const MAX_LINES = 8;
  const LINE_DASHES = ["none", "8 3", "3 3", "12 3 3 3", "2 4", "10 4", "6 3 2 3", "14 4"];
  const marketSlots = new Map();
  const colorFor = id => SERIES_COLORS[marketSlots.get(id)];
  const dashFor = id => LINE_DASHES[marketSlots.get(id)];
  const lineKey = id => `<svg class="line-key" viewBox="0 0 32 12" aria-hidden="true"><path d="M1 6H31" fill="none" stroke="${colorFor(id)}" stroke-width="3" stroke-dasharray="${dashFor(id)}"/></svg>`;

  const $ = (id) => document.getElementById(id);
  const fmt = (v) => (v == null ? "—" : v.toFixed(1));

  let DATA = null;
  let source = "average";
  const sourceLabel = () => ({kalshi: "Kalshi", polymarket: "Polymarket", average: "Average"})[source];
  const pricesFor = (m) => source === "average"
    ? m.prices.polymarket.map((p, i) => p == null || m.prices.kalshi[i] == null ? null : (p + m.prices.kalshi[i]) / 2)
    : m.prices[source];
  const available = (m) => pricesFor(m).some(p => p != null);
  const selectedMarkets = []; // market ids; visual slots stay stable until removal

  // "Pre Week 1", plus "(partial)" when the snapshot predates the week's last game
  const snapLabel = (s) => s.label + (s.partial ? " (partial)" : "");
  // "Pre Week 1 · Sep 10, 8:00 PM ET (partial)" — friendly label with exact time
  const snapFull = (s) => (s.label === s.time || s.time.startsWith(s.label + ",") ? s.time : `${s.label} · ${s.time}`) + (s.partial ? " (partial)" : "");

  fetch("data/data.json?t=" + Date.now())
    .then((r) => r.json())
    .then((d) => {
      DATA = d;
      init();
    })
    .catch((e) => {
      $("movers-list").innerHTML = `<div class="empty-note">Failed to load data: ${e}</div>`;
    });

  function init() {
    $("gen-note").textContent = `Data generated ${DATA.generated} · ${DATA.markets.length} markets · ${DATA.snapshots.length} snapshots`;
    document.querySelectorAll('input[name="price-source"]').forEach(input => {
      input.addEventListener("change", () => {
        source = input.value;
        renderSourceNote();
        $("ts-suggestions").hidden = true;
        $("ts-market-search").setAttribute("aria-expanded", "false");
        renderMovers(true);
        renderTimeSeries();
      });
    });
    renderSourceNote();
    buildSnapshotSelects();
    buildSeriesFilters();
    bindTabs();
    bindMoversControls();
    bindTimeSeriesControls();
    renderMovers();
    renderTimeSeries();
  }

  function renderSourceNote() {
    $("source-note").textContent = source === "average"
      ? "Equal-weight average of Kalshi midpoint and Polymarket price. Both observations required; — means one or both are missing."
      : source === "kalshi"
      ? "Kalshi bid/ask midpoint. Division markets are not included in these snapshots. — means no observation."
      : "Polymarket historical price. — means no observation.";
  }

  /* ---------------- tabs ---------------- */

  function bindTabs() {
    document.querySelectorAll(".tab").forEach((tab) => {
      tab.addEventListener("click", () => switchView(tab.dataset.view));
      tab.addEventListener("keydown", (e) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
        e.preventDefault();
        const view = e.key === "Home" ? "movers" : e.key === "End" ? "series" : tab.dataset.view === "movers" ? "series" : "movers";
        switchView(view);
        $("tab-" + view).focus();
      });
    });
  }

  function switchView(view) {
    document.querySelectorAll(".tab").forEach((t) => {
      const on = t.dataset.view === view;
      t.classList.toggle("active", on);
      t.setAttribute("aria-selected", on);
      t.tabIndex = on ? 0 : -1;
    });
    document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
    $(`view-${view}`).classList.add("active");
    if (view === "series") renderTimeSeries();
  }

  /* ---------------- movers view ---------------- */

  function buildSnapshotSelects() {
    const from = $("from-select");
    const to = $("to-select");
    DATA.snapshots.forEach((s, i) => {
      const optF = new Option(snapLabel(s), i);
      const optT = new Option(snapLabel(s), i);
      optF.title = optT.title = s.time;
      from.add(optF);
      to.add(optT);
    });
    from.value = 0;
    to.value = DATA.snapshots.length - 1;
  }

  function buildSeriesFilters() {
    const teamSet = new Set(DATA.teamSeries);
    for (const sel of [$("series-filter"), $("ts-series-select")]) {
      sel.add(new Option(sel.id === "series-filter" ? "All markets" : "All series", "all"));
      const teams = document.createElement("optgroup");
      teams.label = "Team series";
      const indiv = document.createElement("optgroup");
      indiv.label = "Individual awards";
      DATA.series.forEach((s) => {
        (teamSet.has(s) ? teams : indiv).append(new Option(shortSeries(s), s));
      });
      sel.append(teams, indiv);
    }
  }

  const moversSort = { key: "delta", asc: false };
  let moversOrder = new Map();
  let sortSourceLabel = "Average";

  function bindMoversControls() {
    ["from-select", "to-select", "series-filter"].forEach((id) =>
      $(id).addEventListener("change", renderMovers)
    );
    $("search-input").addEventListener("input", renderMovers);
    document.querySelectorAll(".col-sort").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.sort;
        if (moversSort.key === key) moversSort.asc = !moversSort.asc;
        else { moversSort.key = key; moversSort.asc = false; }
        renderMovers();
      });
    });
  }

  function renderMovers(preserveOrder = false) {
    const fromIdx = +$("from-select").value;
    const toIdx = +$("to-select").value;
    const series = $("series-filter").value;
    const q = $("search-input").value.trim().toLowerCase();

    let rows = DATA.markets
      .filter((m) => series === "all" || m.series === series)
      .filter((m) => !q || m.name.toLowerCase().includes(q) || m.question.toLowerCase().includes(q))
      .map((m) => {
        const a = pricesFor(m)[fromIdx];
        const b = pricesFor(m)[toIdx];
        return { m, a, b, d: a != null && b != null ? b - a : null };
      });

    const keyFn = { delta: (r) => (r.d == null ? null : Math.abs(r.d)), from: (r) => r.a, to: (r) => r.b }[moversSort.key];
    if (preserveOrder === true) {
      rows.sort((x, y) => moversOrder.get(x.m.id) - moversOrder.get(y.m.id));
    } else {
      rows.sort((x, y) => {
        const kx = keyFn(x);
        const ky = keyFn(y);
        if (kx == null && ky == null) return x.m.name.localeCompare(y.m.name);
        if (kx == null) return 1;      // nulls always sink to the bottom
        if (ky == null) return -1;
        return moversSort.asc ? kx - ky : ky - kx;
      });
      moversOrder = new Map(rows.map((r, i) => [r.m.id, i]));
      sortSourceLabel = sourceLabel();
    }
    rows = rows.filter(r => available(r.m));
    document.querySelectorAll(".col-sort").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.sort === moversSort.key);
      btn.classList.toggle("asc", btn.dataset.sort === moversSort.key && moversSort.asc);
      const active = btn.dataset.sort === moversSort.key;
      btn.setAttribute("aria-pressed", active);
      btn.setAttribute("aria-label", `Sort by ${btn.dataset.sort === "delta" ? "absolute change in percentage points" : btn.dataset.sort + " probability"}${active ? ", ordered using " + sortSourceLabel + ", " + (moversSort.asc ? "ascending" : "descending") : ""}`);
    });

    const maxAbs = Math.max(0.5, ...rows.map((r) => Math.abs(r.d ?? 0)));
    const list = $("movers-list");
    list.innerHTML = "";
    const frag = document.createDocumentFragment();

    rows.forEach((r, i) => {
      const btn = document.createElement("button");
      btn.className = "mover-row";
      btn.type = "button";
      btn.title = `${r.m.question}\nChart this market`;
      const d = r.d;
      const cls = d == null || Math.abs(d) < 0.05 ? "zero" : d > 0 ? "pos" : "neg";
      const w = d == null ? 0 : (Math.abs(d) / maxAbs) * 50;
      btn.innerHTML = `
        <span class="rank">${i + 1}</span>
        <span class="name">${esc(r.m.name)}${series === "all" ? `<span class="stag">${esc(shortSeries(r.m.series))}</span>` : ""}</span>
        <span class="price">${fmt(r.a)}</span>
        <span class="price">${fmt(r.b)}</span>
        <span class="barcell"><span class="axis"></span>${
          d == null || Math.abs(d) < 0.05
            ? ""
            : `<span class="bar ${d > 0 ? "pos" : "neg"}" style="width:${w}%"></span>`
        }</span>
        <span class="delta ${cls}">${d == null ? "—" : (d > 0 ? "+" : "") + d.toFixed(1)}</span>`;
      btn.addEventListener("click", () => {
        switchView("series");
        addMarket(r.m.id);
        $("tab-series").focus();
      });
      frag.append(btn);
    });
    list.append(frag);

    const fromLabel = snapFull(DATA.snapshots[fromIdx]);
    const toLabel = snapFull(DATA.snapshots[toIdx]);
    const sortName = { delta: "absolute change", from: "From price", to: "To price" }[moversSort.key];
    $("movers-summary").textContent = `${sourceLabel()} · ${rows.length} market${rows.length === 1 ? "" : "s"} · ${fromLabel} → ${toLabel} · ordered by ${sortSourceLabel} ${sortName} (${moversSort.asc ? "low to high" : "high to low"})${rows.length ? " · select a row to chart it" : ""}`;
    if (!rows.length) {
      const note = document.createElement("div");
      note.className = "empty-note";
      note.textContent = `No ${sourceLabel()} observations match this series and search. `;
      const reset = document.createElement("button");
      reset.textContent = "Clear search";
      reset.onclick = () => { $("search-input").value = ""; renderMovers(); $("search-input").focus(); };
      note.append(reset); list.append(note);
    }
    if (rows.some(r => r.a == null || r.b == null)) {
      const first = Math.min(...rows.map(r => pricesFor(r.m).findIndex(p => p != null)).filter(i => i >= 0));
      $("movers-summary").textContent += ` · — = no observation; ${series === "all" ? "Available" : shortSeries(series)} history begins ${DATA.snapshots[first]?.label || "an unavailable date"}. Coverage varies by market.`;
    }
    if (fromIdx > toIdx) $("movers-summary").textContent += " · Reverse comparison: change is To minus From";
    if (fromIdx === toIdx) {
      $("movers-summary").textContent += " · from and to are the same snapshot";
    }
  }

  /* ---------------- time-series view ---------------- */

  function bindTimeSeriesControls() {
    const input = $("ts-market-search"), sugg = $("ts-suggestions");
    const close = () => { sugg.hidden = true; input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); };
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-controls", "ts-suggestions");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-expanded", "false");
    sugg.setAttribute("role", "listbox");
    sugg.setAttribute("aria-label", "Matching markets");
    let active = -1;
    const update = () => {
      active = -1;
      input.removeAttribute("aria-activedescendant");
      const q = input.value.trim().toLowerCase(), series = $("ts-series-select").value;
      const pool = DATA.markets.filter(available).filter(m => (series === "all" || m.series === series) && (!q || m.name.toLowerCase().includes(q) || m.question.toLowerCase().includes(q)));
      sugg.innerHTML = "";
      pool.forEach((m, i) => {
        const b = document.createElement("div");
        b.id = "suggestion-" + i; b.setAttribute("role", "option"); b.setAttribute("aria-selected", "false");
        b.setAttribute("aria-disabled", selectedMarkets.includes(m.id));
        b.innerHTML = `<span>${esc(m.name)}</span><span class="sser">${selectedMarkets.includes(m.id) ? "Selected · " : ""}${esc(shortSeries(m.series))}</span>`;
        b.addEventListener("pointerdown", e => e.preventDefault());
        b.addEventListener("click", () => {
          if (addMarket(m.id)) { input.value = ""; close(); }
          input.focus();
        });
        sugg.append(b);
      });
      if (!pool.length) sugg.innerHTML = '<div class="empty-note">No matching markets. Try another name or series.</div>';
      sugg.hidden = false; input.setAttribute("aria-expanded", "true");
    };
    input.addEventListener("input", update);
    input.addEventListener("click", update);
    input.addEventListener("blur", close);
    input.addEventListener("keydown", e => {
      if (e.key === "Escape") { e.preventDefault(); close(); return; }
      if (!["ArrowDown", "ArrowUp", "Enter"].includes(e.key)) return;
      if (e.key === "Enter" && sugg.hidden) return;
      e.preventDefault();
      if (sugg.hidden) update();
      const options = [...sugg.querySelectorAll('[role="option"]')];
      if (!options.length) return;
      if (e.key === "Enter") { options[Math.max(0, active)].click(); return; }
      active = (active + (e.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
      options.forEach((b, i) => b.setAttribute("aria-selected", i === active));
      input.setAttribute("aria-activedescendant", options[active].id);
      options[active].scrollIntoView({block: "nearest"});
    });
    $("ts-series-select").addEventListener("change", () => {
      const series = $("ts-series-select").value;
      const markets = DATA.markets.filter(m => m.series === series);
      if (markets.length && !markets.some(available) && markets.some(m => m.prices.polymarket.some(p => p != null))) {
        const polymarket = document.querySelector('input[name="price-source"][value="polymarket"]');
        polymarket.checked = true;
        polymarket.dispatchEvent(new Event("change"));
        $("source-note").textContent = `${shortSeries(series)} has no Kalshi observations. Switched to Polymarket to show available markets.`;
      }
      input.value = "";
      input.focus();
      update();
    });
    $("clear-markets").addEventListener("click", () => { selectedMarkets.length = 0; marketSlots.clear(); close(); renderTimeSeries(); input.focus(); });
    $("full-season").addEventListener("change", () => { if (selectedMarkets.length) { drawChart(); drawTable(); } });
  }

  function addMarket(id) {
    if (selectedMarkets.includes(id)) {
      $("selection-status").textContent = `${selectedMarkets.length}/8 selected · Market already selected`;
      return false;
    }
    if (selectedMarkets.length >= MAX_LINES) {
      $("selection-status").textContent = `${DATA.markets.find(m => m.id === id).name} not added · 8/8 selected; remove a market first`;
      return false;
    }
    const used = new Set(marketSlots.values());
    marketSlots.set(id, SERIES_COLORS.findIndex((_, slot) => !used.has(slot)));
    selectedMarkets.push(id);
    renderTimeSeries();
    return true;
  }

  function removeMarket(id) {
    const i = selectedMarkets.indexOf(id);
    if (i >= 0) selectedMarkets.splice(i, 1);
    marketSlots.delete(id);
    renderTimeSeries();
    $("ts-market-search").focus();
  }

  function renderTimeSeries() {
    $("selection-status").textContent = `${selectedMarkets.length}/8 selected${selectedMarkets.length === 8 ? " · Remove a market to add another" : ""}`;
    $("clear-markets").disabled = !selectedMarkets.length;
    const chips = $("ts-chips");
    chips.innerHTML = "";
    selectedMarkets.forEach((id, i) => {
      const m = DATA.markets.find((x) => x.id === id);
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.innerHTML = `${lineKey(id)}
        <span>${esc(m.name)} <span class="chip-series">· ${esc(shortSeries(m.series))}</span></span>`;
      const x = document.createElement("button");
      x.type = "button";
      x.textContent = "✕";
      x.setAttribute("aria-label", `Remove ${m.name}`);
      x.addEventListener("click", () => removeMarket(id));
      chip.append(x);
      chips.append(chip);
    });

    const empty = selectedMarkets.length === 0;
    $("ts-empty").style.display = empty ? "" : "none";
    $("ts-chart-wrap").style.display = empty ? "none" : "";
    $("ts-table-wrap").innerHTML = "";
    $("data-details").hidden = empty;
    if (empty) { $("chart-range").textContent = ""; return; }

    drawChart();
    drawTable();
  }

  function drawTable() {
    const wrap = $("ts-table-wrap");
    const indices = DATA.snapshots.map((_, i) => i).filter(i => i >= chartStart()).reverse();
    const head = indices.map(i => DATA.snapshots[i]).map((s) => `<th title="${esc(s.time)}">${esc(snapLabel(s))}</th>`).join("");
    const body = selectedMarkets
      .map((id) => {
        const m = DATA.markets.find((x) => x.id === id);
        const cells = indices.map(i => pricesFor(m)[i]).map((p) => `<td>${fmt(p)}</td>`).join("");
        return `<tr><th scope="row">${esc(m.name)}</th>${cells}</tr>`;
      })
      .join("");
    wrap.innerHTML = `<table><thead><tr><th>Market (%)</th>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }

  function chartStart() {
    const starts = selectedMarkets.map(id => pricesFor(DATA.markets.find(m => m.id === id)).findIndex(p => p != null)).filter(i => i >= 0);
    return $("full-season").checked || !starts.length ? 0 : Math.min(...starts);
  }

  function drawChart() {
    const svg = $("ts-chart");
    const wrap = $("ts-chart-wrap");
    const W = Math.max(320, wrap.clientWidth - 10);
    const H = window.innerWidth <= 720 ? 340 : 420;
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.innerHTML = "";

    const markets = selectedMarkets.map((id) => DATA.markets.find((x) => x.id === id));
    const n = DATA.snapshots.length;
    const start = chartStart();
    $("ts-tooltip").hidden = true;
    $("chart-range").textContent = `${sourceLabel()} · ${DATA.snapshots[start].label} – ${DATA.snapshots[n - 1].label} · Probabilities (%) · Hover or tap to inspect`;
    svg.setAttribute("aria-label", `Market probabilities, ${DATA.snapshots[start].label} to ${DATA.snapshots[n-1].label}. Exact values in the data table below.`);
    const pad = { top: 18, right: 66, bottom: 34, left: 44 };
    const iw = W - pad.left - pad.right;
    const ih = H - pad.top - pad.bottom;

    const allVals = markets.flatMap((m) => pricesFor(m)).filter((v) => v != null);
    let yMax = Math.min(100, Math.ceil((Math.max(5, ...allVals) * 1.12) / 5) * 5);
    const yMin = 0;

    const xPos = (i) => pad.left + (n - start === 1 ? iw / 2 : ((i - start) / (n - 1 - start)) * iw);
    const yPos = (v) => pad.top + ih - ((v - yMin) / (yMax - yMin)) * ih;

    const NS = "http://www.w3.org/2000/svg";
    const el = (tag, attrs, text) => {
      const e = document.createElementNS(NS, tag);
      for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
      if (text != null) e.textContent = text;
      svg.append(e);
      return e;
    };

    // gridlines + y ticks
    const step = yMax <= 25 ? 5 : yMax <= 50 ? 10 : 20;
    for (let v = yMin; v <= yMax; v += step) {
      const y = yPos(v);
      el("line", { x1: pad.left, x2: W - pad.right, y1: y, y2: y, class: v === 0 ? "axisline" : "gridline" });
      el("text", { x: pad.left - 8, y: y + 4, "text-anchor": "end", class: "ticktext" }, v + "%");
    }
    // Allow room for NFL labels such as "Post Week 7", counted back from latest.
    const every = n > 1 ? Math.max(1, Math.ceil(80 / (iw / (n - 1 - start)))) : 1;
    for (let i = n - 1; i >= start; i -= every) {
      el("text", { x: xPos(i), y: H - pad.bottom + 18, "text-anchor": "middle", class: "ticktext" }, DATA.snapshots[i].label);
    }

    // lines + points
    markets.forEach((m, mi) => {
      const color = colorFor(m.id);
      let dPath = "";
      let started = false;
      pricesFor(m).forEach((p, i) => {
        if (i < start || p == null) { started = false; return; }
        dPath += `${started ? "L" : "M"}${xPos(i)},${yPos(p)}`;
        started = true;
      });
      if (dPath) el("path", { d: dPath, stroke: color, "stroke-dasharray": dashFor(m.id), class: "series-line" });
      pricesFor(m).forEach((p, i) => {
        if (i < start || p == null) return;
        el("circle", { cx: xPos(i), cy: yPos(p), r: 4, fill: color, class: "series-pt" });
      });
    });

    // direct end labels, collision-shifted
    const labels = markets
      .map((m, mi) => {
        const lastIdx = pricesFor(m).map((p, i) => (p != null ? i : -1)).reduce((a, b) => Math.max(a, b), -1);
        return lastIdx < 0 ? null : { mi, id: m.id, x: xPos(lastIdx), endpointY: yPos(pricesFor(m)[lastIdx]), y: yPos(pricesFor(m)[lastIdx]), v: pricesFor(m)[lastIdx], name: m.name };
      })
      .filter(Boolean)
      .sort((a, b) => a.y - b.y);
    for (let i = 1; i < labels.length; i++) {
      if (labels[i].y - labels[i - 1].y < 14) labels[i].y = labels[i - 1].y + 14;
    }
    for (let i = labels.length - 1; i >= 0; i--) {
      labels[i].y = Math.min(labels[i].y, i === labels.length - 1 ? H - pad.bottom - 8 : labels[i + 1].y - 14);
    }
    labels.forEach((L) => {
      const labelX = W - pad.right + 20;
      el("path", {d: `M${L.x},${L.endpointY}L${labelX - 4},${L.y}`, fill: "none", stroke: colorFor(L.id), "stroke-width": 1, "stroke-dasharray": dashFor(L.id), class: "label-leader"});
      const label = el("text", { x: labelX, y: L.y + 4, fill: colorFor(L.id), class: "end-label" }, `${L.v.toFixed(1)}%`);
      const title = document.createElementNS(NS, "title");
      title.textContent = `${L.name}: ${L.v.toFixed(1)}%`;
      label.append(title);
    });

    // hover crosshair + tooltip
    const tooltip = $("ts-tooltip");
    const cross = el("line", { x1: 0, x2: 0, y1: pad.top, y2: H - pad.bottom, class: "crosshair", visibility: "hidden" });
    const overlay = el("rect", { x: pad.left, y: pad.top, width: iw, height: ih, fill: "transparent" });

    const inspect = (ev) => {
      const rect = svg.getBoundingClientRect();
      const mx = ((ev.clientX - rect.left) / rect.width) * W;
      let idx = 0;
      let best = Infinity;
      for (let i = start; i < n; i++) {
        const d = Math.abs(xPos(i) - mx);
        if (d < best) { best = d; idx = i; }
      }
      cross.setAttribute("x1", xPos(idx));
      cross.setAttribute("x2", xPos(idx));
      cross.setAttribute("visibility", "visible");
      const rowsHtml = markets
        .map((m, mi) => ({ m, mi, v: pricesFor(m)[idx] }))
        .filter((r) => r.v != null)
        .sort((a, b) => b.v - a.v)
        .map((r) => `<div class="tt-row">${lineKey(r.m.id)}
             <span>${esc(truncate(r.m.name, 22))}</span><span class="v">${r.v.toFixed(1)}%</span></div>`)
        .join("");
      tooltip.innerHTML = `<div class="tt-date">${esc(snapFull(DATA.snapshots[idx]))}</div>${rowsHtml || "No observations for this date"}`;
      tooltip.hidden = false;
      const wr = wrap.getBoundingClientRect();
      tooltip.style.left = Math.max(0, Math.min(ev.clientX - wr.left + 12, wr.width - tooltip.offsetWidth - 8)) + "px";
      tooltip.style.top = Math.max(8, Math.min(ev.clientY - wr.top - 30, wr.height - tooltip.offsetHeight - 8)) + "px";
    };
    overlay.addEventListener("pointermove", inspect);
    overlay.addEventListener("pointerdown", inspect);
    overlay.addEventListener("pointerleave", () => {
      tooltip.hidden = true;
      cross.setAttribute("visibility", "hidden");
    });
  }

  window.addEventListener("resize", () => {
    if (selectedMarkets.length && $("view-series").classList.contains("active")) drawChart();
  });

  /* ---------------- utils ---------------- */

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function truncate(s, len) {
    return s.length > len ? s.slice(0, len - 1) + "…" : s;
  }
})();
