/* ============================================================
   app.js — SPA Módulo Acciones — P4 FinPUC
   Vanilla JS + Plotly.js (CDN)
   ============================================================ */
"use strict";

const PAGE_SIZE = 100;

// ---- Estado global ----
const State = {
  sectors: [],
  sectorStocks: {},     // {sector: [stockObj, ...]} — lazy cache
  currentSector: null,
  currentTicker: null,
  currentPage: 1,
  sortKey: null,
  sortAsc: true,
  filterText: "",
};

// ---- Plotly config base ----
const PLOTLY_LAYOUT_BASE = {
  paper_bgcolor: "#161b22",
  plot_bgcolor:  "#161b22",
  font:          { color: "#e6edf3", size: 11 },
  margin:        { t: 8, r: 10, b: 40, l: 60 },
  xaxis: { gridcolor: "#30363d", linecolor: "#30363d", zerolinecolor: "#30363d" },
  yaxis: { gridcolor: "#30363d", linecolor: "#30363d", zerolinecolor: "#30363d" },
};

const PLOTLY_CONFIG = { displayModeBar: false, responsive: true };

// ============================================================
// Init
// ============================================================

async function init() {
  await waitForDB();

  const data = await apiFetch("/api/sectors");
  State.sectors = data;
  renderSidebar(data);

  handleHash();
  window.addEventListener("hashchange", handleHash);
}

async function waitForDB() {
  const msgEl = document.getElementById("loading-msg");
  const barEl = document.getElementById("loading-bar");
  const pctEl = document.getElementById("loading-pct");

  while (true) {
    try {
      const st = await apiFetch("/api/status");
      if (st.ready) {
        barEl.style.width = "100%";
        pctEl.textContent = "100%";
        await sleep(300);
        break;
      }
      const msg = st.message || "Construyendo base de datos...";
      msgEl.textContent = msg;
      const match = msg.match(/\((\d+)%\)/);
      if (match) {
        const pct = parseInt(match[1]);
        barEl.style.width = pct + "%";
        pctEl.textContent = pct + "%";
      } else if (msg.includes("Metadatos")) {
        barEl.style.width = "5%";
        pctEl.textContent = "";
      }
    } catch (_) {
      msgEl.textContent = "Conectando al servidor...";
    }
    await sleep(1000);
  }
  document.getElementById("loading-screen").style.display = "none";
}

// ============================================================
// Routing hash
// ============================================================

function handleHash() {
  const hash  = window.location.hash.replace("#", "");
  const parts = hash.split("/").filter(Boolean);

  if (parts.length === 0 || (parts.length === 1 && parts[0] === "")) {
    goHome();
  } else if (parts[0] === "sector" && parts[1]) {
    selectSector(decodeURIComponent(parts[1]));
  } else if (parts[0] === "stock" && parts[1]) {
    selectStock(parts[1].toUpperCase());
  }
}

function goHome() {
  State.currentSector = null;
  State.currentTicker = null;
  State.sortKey = null;
  State.sortAsc = true;
  State.filterText = "";
  State.currentPage = 1;
  setActiveSector(null);
  setNavState("home");
  showContent(`
    <div class="welcome">
      <div class="welcome-icon"></div>
      <h3>Bienvenido al módulo Acciones</h3>
      <p>Selecciona un sector en el panel izquierdo para explorar las acciones disponibles.</p>
    </div>
  `);
  window.location.hash = "#/";
}

function goSector() {
  if (State.currentSector) {
    window.location.hash = `#/sector/${encodeURIComponent(State.currentSector)}`;
  }
}

// ============================================================
// Sidebar
// ============================================================

function renderSidebar(sectors) {
  const list = document.getElementById("sector-list");
  list.innerHTML = sectors.map(s => `
    <div class="sector-item" data-sector="${esc(s.sector)}"
         onclick="window.location.hash='#/sector/${encodeURIComponent(s.sector)}'">
      <span>${esc(s.sector)}</span>
      <span class="sector-badge">${s.count}</span>
    </div>
  `).join("");
}

function setActiveSector(sector) {
  document.querySelectorAll(".sector-item").forEach(el => {
    el.classList.toggle("active", el.dataset.sector === sector);
  });
}

// ============================================================
// Estado de navegación (topbar)
// ============================================================

function setNavState(view) {
  const btnHome   = document.getElementById("btn-home");
  const btnSector = document.getElementById("btn-sector");
  const sep       = document.getElementById("topbar-sep");
  const current   = document.getElementById("breadcrumb-current");

  if (view === "home") {
    btnHome.style.display   = "none";
    btnSector.style.display = "none";
    sep.style.display       = "none";
    current.textContent     = "Selecciona un sector";
  } else if (view === "sector") {
    btnHome.style.display   = "flex";
    btnSector.style.display = "none";
    sep.style.display       = "none";
    current.textContent     = State.currentSector || "";
  } else if (view === "stock") {
    btnHome.style.display   = "flex";
    btnSector.style.display = "flex";
    sep.style.display       = "inline";
    document.getElementById("btn-sector-label").textContent = State.currentSector || "Sector";
    current.textContent = State.currentTicker || "";
  }
}

// ============================================================
// Vista: lista de acciones del sector
// ============================================================

async function selectSector(sector) {
  if (State.currentSector !== sector) {
    // Resetear estado al cambiar sector
    State.sortKey    = null;
    State.sortAsc    = true;
    State.filterText = "";
    State.currentPage = 1;
  }
  State.currentSector  = sector;
  State.currentTicker  = null;
  setActiveSector(sector);
  setNavState("sector");

  if (!State.sectorStocks[sector]) {
    showSkeletonTable();
    try {
      const stocks = await apiFetch(`/api/sectors/${encodeURIComponent(sector)}/stocks`);
      State.sectorStocks[sector] = stocks;
    } catch (e) {
      showContent(`<p style="color:var(--red);padding:40px;text-align:center">Error cargando el sector. Intenta nuevamente.</p>`);
      return;
    }
  }

  renderStockList();
}

// ---- Helpers de filtro y sort ----

function applyFilter(stocks) {
  const q = State.filterText.trim().toLowerCase();
  if (!q) return stocks;
  return stocks.filter(s =>
    (s.ticker    || "").toLowerCase().includes(q) ||
    (s.short_name|| "").toLowerCase().includes(q) ||
    (s.industry  || "").toLowerCase().includes(q)
  );
}

function applySort(stocks) {
  const key = State.sortKey;
  if (!key) return stocks;
  return [...stocks].sort((a, b) => {
    const nullVal = State.sortAsc ? Infinity : -Infinity;
    const va = a[key] ?? nullVal;
    const vb = b[key] ?? nullVal;
    if (va === vb) return 0;
    return State.sortAsc ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
  });
}

// ---- Render principal ----

function renderStockList() {
  const sector = State.currentSector;
  const stocks = State.sectorStocks[sector] || [];

  const filtered   = applyFilter(stocks);
  const sorted     = applySort(filtered);
  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  State.currentPage = Math.min(Math.max(State.currentPage, 1), totalPages);

  const start = (State.currentPage - 1) * PAGE_SIZE;
  const slice = sorted.slice(start, start + PAGE_SIZE);

  const rows = slice.length === 0
    ? `<tr class="empty-row"><td colspan="10">${State.filterText ? `Sin resultados para "${esc(State.filterText)}"` : "Sin acciones en este sector."}</td></tr>`
    : slice.map(s => {
        const price = s.current_price != null ? `$${s.current_price.toFixed(2)}` : '<span class="val-na">—</span>';
        const cap   = fmtCap(s.market_cap);
        const cagr  = fmtPct(s.cagr, true);
        const vol   = fmtPct(s.ann_volatility);
        const beta  = s.beta != null ? s.beta.toFixed(2) : '<span class="val-na">—</span>';
        const pe    = s.trailing_pe != null ? s.trailing_pe.toFixed(1) : '<span class="val-na">—</span>';
        const dy    = s.dividend_yield != null ? fmtPct(s.dividend_yield) : '<span class="val-na">—</span>';
        return `
          <tr onclick="window.location.hash='#/stock/${esc(s.ticker)}'">
            <td><span class="ticker-badge">${esc(s.ticker)}</span></td>
            <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis">${esc(s.short_name || "—")}</td>
            <td style="max-width:150px;overflow:hidden;text-overflow:ellipsis;color:var(--text-muted)">${esc(s.industry || "—")}</td>
            <td class="num">${price}</td>
            <td class="num">${cap}</td>
            <td class="num">${cagr}</td>
            <td class="num">${vol}</td>
            <td class="num">${beta}</td>
            <td class="num">${pe}</td>
            <td class="num">${dy}</td>
          </tr>`;
      }).join("");

  const filterBadge = State.filterText
    ? `<span class="results-badge">${filtered.length} resultado${filtered.length !== 1 ? "s" : ""}</span>`
    : "";

  const sortHdr = (label, key, cls = "") => {
    const isSorted = State.sortKey === key;
    const dirCls   = isSorted ? (State.sortAsc ? "sort-asc" : "sort-desc") : "";
    return `<th class="sortable ${cls} ${dirCls}" onclick="sortTable('${key}')">${label}<span class="sort-icon"></span></th>`;
  };

  // Controles de paginación reutilizables (arriba y abajo)
  const paginationControls = totalPages <= 1 ? "" : `
    <div class="pagination-controls">
      <button class="page-btn" onclick="changePage(${State.currentPage - 1})"
        ${State.currentPage <= 1 ? "disabled" : ""}>← Ant.</button>
      <span class="page-current">${State.currentPage} / ${totalPages}</span>
      <button class="page-btn" onclick="changePage(${State.currentPage + 1})"
        ${State.currentPage >= totalPages ? "disabled" : ""}>Sig. →</button>
    </div>
  `;

  const rangeInfo = totalPages > 1
    ? `<span class="page-info" style="margin-left:8px">${start + 1}–${Math.min(start + PAGE_SIZE, sorted.length)} de ${sorted.length}</span>`
    : `<span style="color:var(--text-muted);font-size:12px;margin-left:8px">${sorted.length} acciones</span>`;

  showContent(`
    <div class="section-header">
      <div>
        <div class="section-title">${esc(sector)}${filterBadge}</div>
        <div class="section-subtitle">${stocks.length} acciones totales · ordenadas por capitalización</div>
      </div>
      <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <input type="text" id="table-search" placeholder="Buscar ticker, empresa o industria..."
               autocomplete="off" value="${esc(State.filterText)}"
               oninput="onTableSearch(this.value)" />
        ${paginationControls}
        ${rangeInfo}
      </div>
    </div>
    <table class="stocks-table">
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Empresa</th>
          <th>Industria</th>
          ${sortHdr("Precio", "current_price", "num")}
          ${sortHdr("Mkt Cap", "market_cap", "num")}
          ${sortHdr("CAGR", "cagr", "num")}
          ${sortHdr("Volatilidad", "ann_volatility", "num")}
          ${sortHdr("Beta", "beta", "num")}
          ${sortHdr("P/E", "trailing_pe", "num")}
          ${sortHdr("Div Yield", "dividend_yield", "num")}
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    ${totalPages > 1 ? `
    <div class="pagination">
      <span class="page-info">${start + 1}–${Math.min(start + PAGE_SIZE, sorted.length)} de ${sorted.length} acciones</span>
      <div class="pagination-controls">
        <button class="page-btn" onclick="changePage(${State.currentPage - 1})"
          ${State.currentPage <= 1 ? "disabled" : ""}>← Anterior</button>
        <span class="page-current">Página ${State.currentPage} de ${totalPages}</span>
        <button class="page-btn" onclick="changePage(${State.currentPage + 1})"
          ${State.currentPage >= totalPages ? "disabled" : ""}>Siguiente →</button>
      </div>
    </div>` : ""}
  `);
}

function onTableSearch(val) {
  State.filterText  = val;
  State.currentPage = 1;   // resetear a pág 1 al filtrar
  renderStockList();
  // Mantener foco y posición del cursor
  const el = document.getElementById("table-search");
  if (el) { el.focus(); el.setSelectionRange(val.length, val.length); }
}

function sortTable(key) {
  if (State.sortKey === key) {
    State.sortAsc = !State.sortAsc;
  } else {
    State.sortKey = key;
    State.sortAsc = false;  // primera vez: descendente
  }
  State.currentPage = 1;   // resetear a pág 1 al ordenar
  renderStockList();
}

function changePage(page) {
  State.currentPage = page;
  renderStockList();
  // Scroll al top del contenido
  document.getElementById("content").scrollTop = 0;
}

// ============================================================
// Vista: detalle de acción
// ============================================================

async function selectStock(ticker) {
  ticker = ticker.toUpperCase();
  State.currentTicker = ticker;

  // Intentar deducir sector desde caché
  if (!State.currentSector) {
    for (const [sec, stocks] of Object.entries(State.sectorStocks)) {
      if (stocks.find(s => s.ticker === ticker)) {
        State.currentSector = sec;
        break;
      }
    }
  }

  setActiveSector(State.currentSector);
  setNavState("stock");
  showSkeletonDetail();

  try {
    const [info, chart] = await Promise.all([
      apiFetch(`/api/stocks/${ticker}`),
      apiFetch(`/api/stocks/${ticker}/chart`),
    ]);

    if (info.sector && !State.currentSector) {
      State.currentSector = info.sector;
      setActiveSector(info.sector);
      setNavState("stock");
    }

    renderStockDetail(info, chart);
  } catch (e) {
    showContent(`<p style="color:var(--red);padding:40px;text-align:center">Error cargando datos de ${ticker}.</p>`);
  }
}

function renderStockDetail(info, chart) {
  const priceStr = info.current_price != null ? `$${info.current_price.toFixed(2)}` : "—";
  const wkRange  = (info.week52_low != null && info.week52_high != null)
    ? `$${info.week52_low.toFixed(2)} — $${info.week52_high.toFixed(2)}`
    : "—";

  const stats = [
    { label: "Precio actual",     value: priceStr },
    { label: "Market Cap",        value: fmtCap(info.market_cap) },
    { label: "Rango 52 sem.",     value: wkRange },
    { label: "CAGR hist.",        value: fmtPct(info.cagr, true) },
    { label: "Volatilidad anual", value: fmtPct(info.ann_volatility) },
    { label: "Beta",              value: info.beta != null ? info.beta.toFixed(2) : "—" },
    { label: "P/E Trailing",      value: info.trailing_pe != null ? info.trailing_pe.toFixed(1) : "—" },
    { label: "Dividend Yield",    value: fmtPct(info.dividend_yield) },
  ];

  const statsHtml = stats.map(s => `
    <div class="stat-card">
      <div class="stat-label">${s.label}</div>
      <div class="stat-value">${s.value}</div>
    </div>`).join("");

  const summaryHtml = info.summary ? `
    <div class="summary-wrap">
      <div class="summary-title">Descripción</div>
      <div class="summary-text" id="summary-text">${esc(info.summary)}</div>
      <span class="summary-toggle" id="summary-toggle" onclick="toggleSummary()">Mostrar más ▾</span>
    </div>` : "";

  const resBadge = chart.resolution && chart.resolution !== "daily"
    ? `<span class="resolution-badge">${chart.resolution === "weekly" ? "semanal" : "mensual"}</span>`
    : "";

  showContent(`
    <div class="stock-header">
      <h2>${esc(info.ticker)}</h2>
      <span class="stock-name">${esc(info.short_name || info.ticker)}</span>
    </div>
    <div class="stock-meta">
      ${esc(info.sector || "")}${info.industry ? " › " + esc(info.industry) : ""}
      ${info.n_rows ? ` · ${info.n_rows.toLocaleString()} días de historia` : ""}
      ${resBadge}
    </div>

    <div class="stats-grid">${statsHtml}</div>

    ${summaryHtml}

    <div class="chart-wrap">
      <div class="chart-title">Precio de Cierre ${resBadge}</div>
      <div id="chart-price" style="height:320px"></div>
    </div>

    <div class="chart-wrap">
      <div class="chart-title">Volumen</div>
      <div id="chart-volume" style="height:150px"></div>
    </div>

    <div class="chart-wrap">
      <div class="chart-title">Dividendos</div>
      <div id="chart-dividends" style="height:150px"></div>
    </div>
  `);

  requestAnimationFrame(() => {
    buildPriceChart(chart);
    buildVolumeChart(chart);
    buildDividendChart(chart);
  });
}

function toggleSummary() {
  const el  = document.getElementById("summary-text");
  const btn = document.getElementById("summary-toggle");
  if (el.classList.toggle("expanded")) {
    btn.textContent = "Mostrar menos ▴";
  } else {
    btn.textContent = "Mostrar más ▾";
  }
}

// ============================================================
// Skeleton loaders
// ============================================================

function showSkeletonTable() {
  showContent(`
    <div class="section-header">
      <div>
        <div class="skeleton skeleton-line w40" style="height:22px;margin-bottom:6px"></div>
        <div class="skeleton skeleton-line w60" style="height:12px"></div>
      </div>
    </div>
    ${Array(8).fill('<div class="skeleton" style="height:38px;margin-bottom:4px;border-radius:4px"></div>').join("")}
  `);
}

function showSkeletonDetail() {
  showContent(`
    <div class="skeleton skeleton-header"></div>
    <div class="skeleton skeleton-line w40" style="height:13px;margin-bottom:20px"></div>
    <div class="skeleton-grid">
      ${Array(8).fill('<div class="skeleton skeleton-card"></div>').join("")}
    </div>
    <div class="skeleton skeleton-chart" style="margin-bottom:14px"></div>
    <div class="skeleton" style="height:150px;border-radius:8px;margin-bottom:14px"></div>
    <div class="skeleton" style="height:150px;border-radius:8px"></div>
  `);
}

// ============================================================
// Búsqueda global (usa endpoint /api/search)
// ============================================================

let _searchTimer = null;

function onGlobalSearch(val) {
  const resultsEl = document.getElementById("search-results");
  const q = val.trim();

  if (q.length < 1) {
    resultsEl.style.display = "none";
    return;
  }

  // Debounce 250ms para no spamear requests
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(async () => {
    try {
      const matches = await apiFetch(`/api/search?q=${encodeURIComponent(q)}`);
      if (matches.length === 0) {
        resultsEl.innerHTML = `<div class="sr-item" style="color:var(--text-muted)">Sin resultados</div>`;
      } else {
        resultsEl.innerHTML = matches.map(s => `
          <div class="sr-item" onmousedown="pickGlobalResult('${esc(s.ticker)}')">
            <span class="ticker-badge">${esc(s.ticker)}</span>
            <span class="sr-item-name">${esc(s.short_name || "")}</span>
          </div>
        `).join("");
      }
      resultsEl.style.display = "block";
    } catch (_) {
      resultsEl.style.display = "none";
    }
  }, 250);
}

function pickGlobalResult(ticker) {
  document.getElementById("search-global").value = "";
  document.getElementById("search-results").style.display = "none";
  window.location.hash = `#/stock/${ticker}`;
}

function hideSearchResults() {
  setTimeout(() => {
    document.getElementById("search-results").style.display = "none";
  }, 150);
}

// ============================================================
// Plotly charts
// ============================================================

function buildPriceChart(chart) {
  const el = document.getElementById("chart-price");
  if (!el) return;

  Plotly.newPlot(el, [{
    x: chart.dates,
    y: chart.close,
    type: "scatter",
    mode: "lines",
    name: "Cierre",
    fill: "tozeroy",
    fillcolor: "rgba(0,120,191,0.08)",
    line: { color: "#0078bf", width: 1.5 },
    hovertemplate: "%{x}<br><b>$%{y:.2f}</b><extra></extra>",
  }], {
    ...PLOTLY_LAYOUT_BASE,
    margin: { t: 8, r: 10, b: 60, l: 70 },
    xaxis: {
      ...PLOTLY_LAYOUT_BASE.xaxis,
      rangeselector: {
        bgcolor: "#1c2230",
        activecolor: "#003865",
        bordercolor: "#30363d",
        font: { color: "#e6edf3", size: 11 },
        buttons: [
          { count: 1,  label: "1A",  step: "year",  stepmode: "backward" },
          { count: 5,  label: "5A",  step: "year",  stepmode: "backward" },
          { count: 10, label: "10A", step: "year",  stepmode: "backward" },
          { step: "all", label: "Todo" },
        ],
      },
      rangeslider: { visible: true, bgcolor: "#0d1117", thickness: 0.04 },
      type: "date",
    },
    yaxis: {
      ...PLOTLY_LAYOUT_BASE.yaxis,
      title: { text: "USD", font: { size: 10 } },
      tickprefix: "$",
    },
  }, PLOTLY_CONFIG);
}

function buildVolumeChart(chart) {
  const el = document.getElementById("chart-volume");
  if (!el) return;

  Plotly.newPlot(el, [{
    x: chart.dates,
    y: chart.volume,
    type: "bar",
    name: "Volumen",
    marker: { color: "#0078bf", opacity: 0.5 },
    hovertemplate: "%{x}<br><b>%{y:,.0f}</b><extra></extra>",
  }], {
    ...PLOTLY_LAYOUT_BASE,
    bargap: 0,
    yaxis: {
      ...PLOTLY_LAYOUT_BASE.yaxis,
      title: { text: "Vol.", font: { size: 10 } },
    },
  }, PLOTLY_CONFIG);
}

function buildDividendChart(chart) {
  const el = document.getElementById("chart-dividends");
  if (!el) return;

  const divDates = [], divVals = [];
  for (let i = 0; i < chart.dates.length; i++) {
    if (chart.dividends[i] > 0) {
      divDates.push(chart.dates[i]);
      divVals.push(chart.dividends[i]);
    }
  }

  if (divDates.length === 0) {
    el.innerHTML = '<p style="color:var(--text-muted);font-size:13px;padding:16px 0;">Sin dividendos en el historial.</p>';
    return;
  }

  Plotly.newPlot(el, [{
    x: divDates,
    y: divVals,
    type: "bar",
    name: "Dividendo",
    marker: { color: "#c49b25", opacity: 0.8 },
    hovertemplate: "%{x}<br><b>$%{y:.4f}</b><extra></extra>",
  }], {
    ...PLOTLY_LAYOUT_BASE,
    bargap: 0.2,
    yaxis: {
      ...PLOTLY_LAYOUT_BASE.yaxis,
      title: { text: "USD/acción", font: { size: 10 } },
      tickprefix: "$",
    },
  }, PLOTLY_CONFIG);
}

function renderEfficientFrontierChart(result, targetId = "frontier-chart") {
  if (typeof Plotly === "undefined") return;
  if (!result || !(result.efficient_frontier || []).length) return;
  const el = document.getElementById(targetId);
  if (!el) return;

  const points = result.efficient_frontier || [];
  const x = points.map(p => (p?.volatility_pct ?? p?.[0]));
  const y = points.map(p => (p?.expected_return_pct ?? p?.[1]));
  const metrics = result.metrics || {};

  const traces = [
    {
      x,
      y,
      type: "scatter",
      mode: "lines+markers",
      name: "Frontera eficiente",
      line: { color: "#0078bf", width: 2 },
      marker: { size: 6 },
      hovertemplate: "Vol: %{x:.2f}%<br>Ret: %{y:.2f}%<extra></extra>",
    },
  ];

  if (metrics.volatility_pct != null && metrics.expected_return_pct != null) {
    traces.push({
      x: [metrics.volatility_pct],
      y: [metrics.expected_return_pct],
      type: "scatter",
      mode: "markers",
      name: "Portafolio",
      marker: { size: 12, color: "#c49b25", line: { color: "#0d1117", width: 2 } },
      hovertemplate: "Portafolio<br>Vol: %{x:.2f}%<br>Ret: %{y:.2f}%<extra></extra>",
    });
  }

  Plotly.newPlot(el, traces, {
    ...PLOTLY_LAYOUT_BASE,
    margin: { t: 12, r: 20, b: 60, l: 70 },
    xaxis: { ...PLOTLY_LAYOUT_BASE.xaxis, title: { text: "Volatilidad (%)", font: { size: 11 } } },
    yaxis: { ...PLOTLY_LAYOUT_BASE.yaxis, title: { text: "Retorno esperado (%)", font: { size: 11 } } },
    legend: { orientation: "h", y: -0.25 },
  }, PLOTLY_CONFIG);
}

// ============================================================
// Helpers
// ============================================================

async function apiFetch(url, options) {
  const res = options ? await fetch(url, options) : await fetch(url);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `API ${res.status}: ${url}`);
  }
  return res.json();
}

function showContent(html) {
  document.getElementById("content").innerHTML = html;
}

function esc(str) {
  if (str == null) return "";
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function fmtCap(n) {
  if (n == null) return '<span class="val-na">—</span>';
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9)  return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6)  return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toLocaleString()}`;
}

function fmtPct(n, colored = false) {
  if (n == null) return '<span class="val-na">—</span>';
  const pct = (n * 100).toFixed(1) + "%";
  if (!colored) return pct;
  const cls  = n >= 0 ? "val-pos" : "val-neg";
  const sign = n >= 0 ? "+" : "";
  return `<span class="${cls}">${sign}${pct}</span>`;
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

// ============================================================
// Arranque
// ============================================================
document.addEventListener("DOMContentLoaded", init);

// ============================================================
// MÓDULO PORTAFOLIOS
// ============================================================

// ---- Helpers específicos del módulo ----
function fmtUSD(n) {
  if (n == null) return "—";
  return "$" + Math.round(n).toLocaleString("en-US");
}

// ---- Estado del módulo portafolios ----
const PF = {
  activeNav: "nuevo",        // "nuevo" | "benchmark" | "simulate"
  currentModule: "acciones", // "acciones" | "portafolios"
  lastResult: null,          // última respuesta de /api/portfolio/optimize
  lastBenchmark: null,       // última respuesta de /api/portfolio/benchmark
  lastSimulation: null,      // última respuesta de /api/portfolio/simulate
  recommendations: [],       // [{id, date, status, items}]
  selectedModel: "simple",   // "simple" | "markowitz" | "propio"
};

// ---- Definición de los tres modelos de recomendación ----
const MODEL_DEFS = {
  simple: {
    name: "Modelo Simple",
    sub: "Selección por mayor retorno histórico",
    icon: "",
    desc: "Selecciona las acciones con mayor CAGR histórico distribuidas en pesos iguales. Caso base de referencia.",
    apiMethod: "benchmark",
  },
  markowitz: {
    name: "Modelo Markowitz",
    sub: "Maximización de retorno ajustado al riesgo",
    icon: "",
    desc: "Frontera eficiente que maximiza el ratio de Sharpe según tu perfil de riesgo.",
    apiMethod: "markowitz",
  },
  propio: {
    name: "Mínima Varianza",
    sub: "Metodología Propia — Mínimo riesgo absoluto",
    icon: "",
    desc: "Portafolio de mínima varianza en la frontera eficiente, priorizando la estabilidad del capital sobre el retorno.",
    apiMethod: "markowitz",
    forcedMaxLoss: 0.10,
  },
};

function selectModel(modelId) {
  PF.selectedModel = modelId;
  ["simple", "markowitz", "propio"].forEach(id => {
    document.getElementById("mc-" + id)?.classList.toggle("active", id === modelId);
  });
}

// ---- Cambio de módulo (Acciones / Portafolios) ----
function switchModule(mod) {
  PF.currentModule = mod;
  const tabA = document.getElementById("tab-acciones");
  const tabP = document.getElementById("tab-portafolios");
  const sectorLabel = document.getElementById("sector-label");
  const sectorList  = document.getElementById("sector-list");
  const portNav     = document.getElementById("portfolio-nav");

  if (mod === "portafolios") {
    tabA.classList.remove("active");
    tabP.classList.add("active");
    sectorLabel.style.display = "none";
    sectorList.style.display  = "none";
    portNav.style.display     = "block";
    pfNavGo(PF.activeNav);
  } else {
    tabP.classList.remove("active");
    tabA.classList.add("active");
    sectorLabel.style.display = "";
    sectorList.style.display  = "";
    portNav.style.display     = "none";
    // Restore acciones home
    State.currentSector = null;
    State.currentTicker = null;
    renderWelcome();
    updateNav();
  }
}

// ---- Nav lateral del módulo portafolios ----
function pfNavGo(section) {
  PF.activeNav = section;
  ["nuevo","benchmark","simulate"].forEach(id => {
    document.getElementById("pnav-" + id)?.classList.remove("active");
  });
  document.getElementById("pnav-" + section)?.classList.add("active");

  switch (section) {
    case "nuevo":     renderPfForm();      break;
    case "benchmark": renderBenchmark();   break;
    case "simulate":  renderSimulation();  break;
  }
}

// ============================================================
// FORMULARIO DE PERFILAMIENTO
// ============================================================
function renderPfForm() {
  const riskLabel = (v) => {
    if (v <= 0.15) return ["conservador","#3fb950"];
    if (v <= 0.35) return ["moderado","#c49b25"];
    return ["agresivo","#f85149"];
  };

  const m = PF.selectedModel || "simple";
  const contentEl = document.getElementById("content");
  contentEl.innerHTML = `
    <div class="pf-section">

      <!-- Selector de modelo de recomendación -->
      <div class="pf-card">
        <div class="pf-card-title">Modelo de Recomendación</div>
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px">
          Elige el modelo de optimización para construir tu portafolio personalizado.
        </p>
        <div class="model-selector">
          <div class="model-card ${m === 'simple' ? 'active' : ''}" id="mc-simple" onclick="selectModel('simple')">
            <div class="model-card-check">✓</div>
            <div class="model-card-icon"></div>
            <div class="model-card-name">Modelo Simple</div>
            <div class="model-card-sub">Selección por mayor retorno histórico</div>
            <div class="model-card-desc">Acciones con mayor CAGR histórico distribuidas en pesos iguales. Caso base de referencia.</div>
          </div>
          <div class="model-card ${m === 'markowitz' ? 'active' : ''}" id="mc-markowitz" onclick="selectModel('markowitz')">
            <div class="model-card-check">✓</div>
            <div class="model-card-icon"></div>
            <div class="model-card-name">Modelo Markowitz</div>
            <div class="model-card-sub">Maximización de retorno ajustado al riesgo</div>
            <div class="model-card-desc">Frontera eficiente que maximiza el ratio de Sharpe según tu perfil de riesgo.</div>
          </div>
          <div class="model-card ${m === 'propio' ? 'active' : ''}" id="mc-propio" onclick="selectModel('propio')">
            <div class="model-card-check">✓</div>
            <div class="model-card-icon"></div>
            <div class="model-card-name">Mínima Varianza</div>
            <div class="model-card-sub">Metodología Propia — Mínimo riesgo absoluto</div>
            <div class="model-card-desc">Portafolio de mínima varianza en la frontera eficiente, priorizando la estabilidad del capital sobre el retorno.</div>
          </div>
        </div>
      </div>

      <!-- Perfil de riesgo -->
      <div class="pf-card">
        <div class="pf-card-title">Definir Perfil de Riesgo</div>
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:20px">
          Define tu tolerancia máxima de pérdida para recibir un portafolio
          adaptado a tu perfil de inversión.
        </p>

        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Capital inicial (USD)</label>
            <input id="pf-capital" class="form-input" type="number" min="1000" step="1000" value="100000" placeholder="100000">
          </div>
          <div class="form-group">
            <label class="form-label">Número de acciones</label>
            <input id="pf-nstocks" class="form-input" type="number" min="3" max="20" value="10">
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">
            Pérdida máxima tolerable:
            <strong id="pf-loss-pct-val">20%</strong>
          </label>
          <div class="risk-row">
            <input id="pf-loss-pct" class="risk-slider" type="range" min="5" max="80" value="20"
                   oninput="onRiskSlider(this.value)" style="width:100%">
            <span id="pf-risk-badge" class="risk-badge moderado">moderado</span>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted);margin-top:4px">
            <span>5% — Conservador</span><span>80% — Agresivo</span>
          </div>
        </div>

        <div style="display:flex;gap:10px;align-items:center">
          <button class="btn-primary" id="pf-submit-btn" onclick="submitPortfolioForm()">
            Generar portafolio
          </button>
          <span id="pf-loading" style="font-size:13px;color:var(--text-muted);display:none">
            Optimizando...
          </span>
        </div>
      </div>

      <div id="pf-result"></div>
    </div>`;
}

function onRiskSlider(val) {
  const v = parseInt(val) / 100;
  document.getElementById("pf-loss-pct-val").textContent = val + "%";
  const badge = document.getElementById("pf-risk-badge");
  if (v <= 0.15) { badge.textContent = "conservador"; badge.className = "risk-badge conservador"; }
  else if (v <= 0.35) { badge.textContent = "moderado"; badge.className = "risk-badge moderado"; }
  else { badge.textContent = "agresivo"; badge.className = "risk-badge agresivo"; }
}

async function submitPortfolioForm() {
  const capital    = parseFloat(document.getElementById("pf-capital").value) || 100000;
  const nstocks    = parseInt(document.getElementById("pf-nstocks").value)   || 10;
  const maxLossPct = parseInt(document.getElementById("pf-loss-pct").value) / 100;

  const modelDef   = MODEL_DEFS[PF.selectedModel] || MODEL_DEFS.simple;
  const apiMaxLoss = modelDef.forcedMaxLoss ?? maxLossPct;

  const btn     = document.getElementById("pf-submit-btn");
  const loading = document.getElementById("pf-loading");
  btn.disabled  = true;
  loading.style.display = "inline";

  try {
    const result = await apiFetch("/api/portfolio/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        initial_capital: capital,
        max_loss_pct:    apiMaxLoss,
        n_stocks:        nstocks,
        method:          modelDef.apiMethod,
      }),
    });
    PF.lastResult = result;
    // Generate a pending recommendation
    PF.recommendations = [{
      id: Date.now(),
      date: new Date().toLocaleDateString("es-CL"),
      status: "pendiente",
      items: result.portfolio,
      metrics: result.metrics,
    }];
    renderPfResult(result, capital, maxLossPct);
  } catch (e) {
    document.getElementById("pf-result").innerHTML =
      `<div class="pf-card" style="color:var(--red)">Error: ${e.message}</div>`;
  } finally {
    btn.disabled = false;
    loading.style.display = "none";
  }
}

// ============================================================
// RESULTADOS DEL PORTAFOLIO
// ============================================================
function renderPfResult(r, capital, maxLossPct) {
  const riskColors = { conservador: "var(--green)", moderado: "var(--dorado)", agresivo: "var(--red)" };
  const riskColor  = riskColors[r.risk_level] || "var(--azul-claro)";

  // Scenario returns for year 3 (display)
  const sc = r.scenarios;
  const yr = "3";

  // Modelo seleccionado
  const modelDef = MODEL_DEFS[PF.selectedModel] || MODEL_DEFS.simple;

  // Indicador de compatibilidad con el perfil de riesgo del cliente
  // Verifica si el escenario desfavorable anual cabe dentro de la tolerancia del cliente
  const worstAnnual = r.scenarios.desfavorable.annual_return_pct / 100;
  const isCompatible = worstAnnual >= -maxLossPct;
  const compatHtml = `
    <div class="risk-compat ${isCompatible ? "compatible" : "incompatible"}">
      ${isCompatible ? "Compatible con tu perfil de riesgo" : "Puede superar tu tolerancia de pérdida"}
      <span style="font-size:11px;font-weight:400;margin-left:6px;opacity:.85">
        Escenario desfavorable: ${r.scenarios.desfavorable.annual_return_pct}%/año &nbsp;·&nbsp; Tolerancia: −${(maxLossPct * 100).toFixed(0)}%
      </span>
    </div>`;

  const validHtml = r.validation
    ? `<div class="validation-pill">
         Validación (${r.validation.period}):
         retorno portafolio = <strong style="margin-left:4px">${r.validation.total_return_pct > 0 ? "+" : ""}${r.validation.total_return_pct}%</strong>
         (anualizado: ${r.validation.annualized_return_pct > 0 ? "+" : ""}${r.validation.annualized_return_pct}%)
       </div>`
    : "";

  const html = `
    <!-- Banner del modelo seleccionado -->
    <div class="model-result-banner">
      <span style="font-size:22px">${modelDef.icon}</span>
      <div>
        <span class="model-badge">${modelDef.name}</span>
        <span style="color:var(--text-muted);margin-left:8px;font-size:12px">${modelDef.sub}</span>
      </div>
    </div>

    <!-- Perfil de riesgo y compatibilidad -->
    <div class="pf-card">
      <div class="pf-card-title">Perfil de riesgo detectado</div>
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
        <span style="font-size:28px;font-weight:800;color:${riskColor}">${r.risk_level.toUpperCase()}</span>
        <div>
          <div style="font-size:13px;color:var(--text-muted)">Pérdida máxima tolerada: <strong>${(r.max_loss_pct * 100).toFixed(0)}%</strong></div>
          <div style="font-size:13px;color:var(--text-muted)">Capital inicial: <strong>${fmtUSD(capital)}</strong></div>
          <div style="font-size:13px;color:var(--text-muted)">Método: <strong>${r.metrics.method}</strong> | Comisión: <strong>${r.commission_rate_pct}% anual</strong></div>
        </div>
      </div>
      ${compatHtml}
      ${validHtml}
      <div style="font-size:11px;color:var(--text-muted)">
        Calibración: ${r.data_split.calibration_start} → ${r.data_split.calibration_end} &nbsp;|&nbsp;
        Validación: ${r.data_split.validation_start} → ${r.data_split.validation_end}
      </div>
    </div>

    <!-- Métricas -->
    <div class="pf-section-title">Métricas del portafolio optimizado</div>
    <div class="metrics-grid">
      <div class="metric-card">
        <div class="metric-label">Retorno esperado</div>
        <div class="metric-value" style="color:${r.metrics.expected_return_pct >= 0 ? 'var(--green)' : 'var(--red)'}">
          ${r.metrics.expected_return_pct > 0 ? "+" : ""}${r.metrics.expected_return_pct}%
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Volatilidad anual</div>
        <div class="metric-value">${r.metrics.volatility_pct}%</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Ratio Sharpe</div>
        <div class="metric-value">${r.metrics.sharpe_ratio}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Capital año 3 (neutro)</div>
        <div class="metric-value">${fmtUSD(sc.neutro.capital_by_year[yr])}</div>
      </div>
    </div>

    <!-- Escenarios (Épica 1) -->
    <div class="pf-section-title">Escenarios de retorno estimado (5 años)</div>
    <div class="scenario-grid">
      <div class="scenario-card favorable">
        <div class="scenario-label">Favorable</div>
        <div class="scenario-ret" style="color:var(--green)">
          ${sc.favorable.annual_return_pct > 0 ? "+" : ""}${sc.favorable.annual_return_pct}%/año
        </div>
        <div class="scenario-cap">Año 5: ${fmtUSD(sc.favorable.capital_by_year["5"])}</div>
        <div class="scenario-cap">Retorno total: ${sc.favorable.total_return_pct > 0 ? "+" : ""}${sc.favorable.total_return_pct}%</div>
      </div>
      <div class="scenario-card neutro">
        <div class="scenario-label">Neutro</div>
        <div class="scenario-ret" style="color:var(--azul-claro)">
          ${sc.neutro.annual_return_pct > 0 ? "+" : ""}${sc.neutro.annual_return_pct}%/año
        </div>
        <div class="scenario-cap">Año 5: ${fmtUSD(sc.neutro.capital_by_year["5"])}</div>
        <div class="scenario-cap">Retorno total: ${sc.neutro.total_return_pct > 0 ? "+" : ""}${sc.neutro.total_return_pct}%</div>
      </div>
      <div class="scenario-card desfavorable">
        <div class="scenario-label">Desfavorable</div>
        <div class="scenario-ret" style="color:var(--red)">
          ${sc.desfavorable.annual_return_pct > 0 ? "+" : ""}${sc.desfavorable.annual_return_pct}%/año
        </div>
        <div class="scenario-cap">Año 5: ${fmtUSD(sc.desfavorable.capital_by_year["5"])}</div>
        <div class="scenario-cap">Retorno total: ${sc.desfavorable.total_return_pct > 0 ? "+" : ""}${sc.desfavorable.total_return_pct}%</div>
      </div>
    </div>

    <!-- Gráfico de escenarios -->
    <div class="chart-wrap">
      <div class="pf-section-title" style="border:none;padding:0;margin-bottom:8px">Proyección de capital por escenario</div>
      <div id="pf-scenario-chart" style="height:280px"></div>
    </div>

    <!-- Posiciones del portafolio -->
    <div class="pf-section-title">Composición del portafolio (${r.portfolio.length} acciones)</div>
    <div class="pf-card" style="padding:0;overflow:hidden">
      <table class="pf-table">
        <thead>
          <tr>
            <th>Ticker</th><th>Empresa</th><th>Sector</th>
            <th style="text-align:right">Peso</th>
            <th style="text-align:right">CAGR hist.</th>
            <th style="text-align:right">Volatilidad</th>
          </tr>
        </thead>
        <tbody>
          ${r.portfolio.map(p => `
            <tr>
              <td><strong>${p.ticker}</strong></td>
              <td style="color:var(--text-muted)">${p.short_name || "—"}</td>
              <td style="color:var(--text-muted);font-size:12px">${p.sector || "—"}</td>
              <td style="text-align:right">
                <span class="weight-bar" style="width:${Math.round(p.weight*120)}px"></span>
                ${(p.weight*100).toFixed(1)}%
              </td>
              <td style="text-align:right;color:${(p.cagr_pct||0)>=0?'var(--green)':'var(--red)'}">
                ${p.cagr_pct != null ? (p.cagr_pct > 0 ? "+" : "") + p.cagr_pct + "%" : "—"}
              </td>
              <td style="text-align:right">${p.volatility_pct != null ? p.volatility_pct + "%" : "—"}</td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>

    <!-- Recomendación de rebalanceo (Épica 2) -->
    <div class="pf-section-title" style="margin-top:24px">Recomendación de portafolio inicial</div>
    <div id="pf-recs"></div>

    <!-- Botón retiro (Épica 1) -->
    <div class="pf-card" style="background:rgba(248,81,73,.05);border-color:rgba(248,81,73,.3)">
      <div class="pf-card-title" style="color:var(--red)">Derecho a retiro</div>
      <p style="font-size:13px;color:var(--text-muted);margin-bottom:12px">
        Si las pérdidas de tu portafolio superan tu tolerancia máxima (${(maxLossPct*100).toFixed(0)}%),
        puedes retirar tu inversión en cualquier momento.
      </p>
      <button class="btn-secondary" style="border-color:var(--red);color:var(--red)"
              id="btn-withdrawal"
              data-capital="${capital}"
              data-maxloss="${maxLossPct}">
        Simular escenario de retiro
      </button>
    </div>`;

  document.getElementById("pf-result").innerHTML = html;
  // Attach event listener for withdrawal button (avoids inline onclick with interpolated values)
  const withdrawBtn = document.getElementById("btn-withdrawal");
  if (withdrawBtn) {
    withdrawBtn.addEventListener("click", () => {
      const cap  = parseFloat(withdrawBtn.dataset.capital);
      const loss = parseFloat(withdrawBtn.dataset.maxloss);
      simulateWithdrawal(cap, loss);
    });
  }
  renderScenarioChart(r.scenario_timeseries);
  renderRecommendations();
}

function renderScenarioChart(ts) {
  if (!ts || !ts.months || typeof Plotly === "undefined") return;
  const traces = [
    { x: ts.months.map(m => `Mes ${m}`), y: ts.favorable, name: "Favorable", line: { color: "#3fb950" }, mode: "lines" },
    { x: ts.months.map(m => `Mes ${m}`), y: ts.neutro,    name: "Neutro",    line: { color: "#0078bf" }, mode: "lines" },
    { x: ts.months.map(m => `Mes ${m}`), y: ts.desfavorable, name: "Desfavorable", line: { color: "#f85149", dash: "dot" }, mode: "lines" },
  ];
  const layout = {
    ...PLOTLY_LAYOUT_BASE,
    margin: { t: 10, r: 20, b: 50, l: 80 },
    yaxis: { ...PLOTLY_LAYOUT_BASE.yaxis, title: "Capital (USD)", tickformat: ",.0f" },
    legend: { orientation: "h", y: -0.2 },
    showlegend: true,
  };
  Plotly.newPlot("pf-scenario-chart", traces, layout, PLOTLY_CONFIG);
}

// ---- Recomendaciones de rebalanceo (Épica 2) ----
function renderRecommendations() {
  const el = document.getElementById("pf-recs");
  if (!el) return;
  if (!PF.recommendations.length) {
    el.innerHTML = `<div class="pf-card" style="color:var(--text-muted);font-size:13px">No hay recomendaciones pendientes.</div>`;
    return;
  }
  el.innerHTML = PF.recommendations.map(rec => `
    <div class="rec-card" id="rec-${rec.id}">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <div>
          <strong>Propuesta de portafolio</strong>
          <span style="font-size:12px;color:var(--text-muted);margin-left:8px">${rec.date}</span>
        </div>
        <div id="rec-status-${rec.id}">
          ${rec.status === "pendiente"
            ? `<button class="accept-btn" data-rec="${rec.id}" data-action="accept">✓ Aceptar</button>
               <button class="reject-btn"  data-rec="${rec.id}" data-action="reject">✗ Rechazar</button>`
            : `<span class="rec-status ${rec.status}">${rec.status}</span>`}
        </div>
      </div>
      <div style="font-size:12px;color:var(--text-muted)">
        ${rec.items.slice(0, 5).map(p =>
          `<span style="margin-right:12px"><strong>${p.ticker}</strong> ${(p.weight*100).toFixed(1)}%</span>`
        ).join("")}${rec.items.length > 5 ? `<span>+${rec.items.length - 5} más</span>` : ""}
      </div>
    </div>`).join("");

  // Attach event listeners to recommendation buttons
  el.querySelectorAll("[data-rec]").forEach(btn => {
    btn.addEventListener("click", () => {
      const id     = parseInt(btn.dataset.rec, 10);
      const accept = btn.dataset.action === "accept";
      respondRec(id, accept);
    });
  });
}

function respondRec(id, accept) {
  const rec = PF.recommendations.find(r => r.id === id);
  if (!rec) return;
  rec.status = accept ? "aceptada" : "rechazada";
  const statusEl = document.getElementById("rec-status-" + id);
  if (statusEl) {
    statusEl.innerHTML = `<span class="rec-status ${rec.status}">${rec.status}</span>`;
  }
  // Visual feedback
  const card = document.getElementById("rec-" + id);
  if (card) {
    card.style.borderColor = accept ? "var(--green)" : "var(--red)";
    const msg = accept
      ? "✓ Recomendación aceptada — portafolio actualizado según propuesta."
      : "✗ Recomendación rechazada — el portafolio anterior se mantiene.";
    card.insertAdjacentHTML("beforeend",
      `<div style="margin-top:8px;font-size:12px;color:${accept?'var(--green)':'var(--red)'}">${msg}</div>`);
  }
}

function simulateWithdrawal(capital, maxLoss) {
  if (!PF.lastResult) return;
  const r = PF.lastResult;
  pfNavGo("simulate");
  // Pre-fill simulation with current portfolio parameters
  setTimeout(() => {
    const el = document.getElementById("sim-capital");
    if (el) { el.value = capital; }
    const lossEl = document.getElementById("sim-loss-pct");
    if (lossEl) { lossEl.value = Math.round(maxLoss * 100); onSimLossSlider(lossEl.value); }
    const retEl = document.getElementById("sim-exp-ret");
    if (retEl) retEl.value = r.metrics.expected_return_pct;
    const volEl = document.getElementById("sim-vol");
    if (volEl) volEl.value = r.metrics.volatility_pct;
    submitSimulation();
  }, 100);
}

// ============================================================
// BENCHMARK SIMPLE (Épica 3)
// ============================================================
async function renderBenchmark() {
  const contentEl = document.getElementById("content");
  contentEl.innerHTML = `<div class="pf-section">
    <div class="pf-card">
      <div class="pf-card-title">Benchmark Simple — Top CAGR</div>
      <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px">
        Selección de las N acciones con mayor CAGR histórico con pesos iguales.
        Sirve como caso base de comparación frente al modelo de Markowitz.
      </p>
      <div class="form-row">
        <div class="form-group">
          <label class="form-label">Número de acciones</label>
          <input id="bm-n" class="form-input" type="number" min="3" max="30" value="10">
        </div>
      </div>
      <button class="btn-primary" onclick="fetchBenchmark()">Calcular benchmark</button>
    </div>
    <div id="bm-result"></div>
  </div>`;
}

async function fetchBenchmark() {
  const n = parseInt(document.getElementById("bm-n").value) || 10;
  try {
    const r = await apiFetch(`/api/portfolio/benchmark?n=${n}`);
    PF.lastBenchmark = r;
    renderBenchmarkResult(r);
  } catch (e) {
    document.getElementById("bm-result").innerHTML =
      `<div class="pf-card" style="color:var(--red)">Error: ${e.message}</div>`;
  }
}

function renderBenchmarkResult(r) {
  const html = `
    <div class="metrics-grid">
      <div class="metric-card">
        <div class="metric-label">Retorno esperado</div>
        <div class="metric-value" style="color:var(--green)">
          ${r.metrics.expected_return_pct > 0 ? "+" : ""}${r.metrics.expected_return_pct}%
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Volatilidad</div>
        <div class="metric-value">${r.metrics.volatility_pct}%</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Método</div>
        <div class="metric-value" style="font-size:13px">Top CAGR</div>
      </div>
    </div>
    <div class="pf-card" style="padding:0;overflow:hidden">
      <table class="pf-table">
        <thead>
          <tr>
            <th>Rank</th><th>Ticker</th><th>Empresa</th><th>Sector</th>
            <th style="text-align:right">Peso</th>
            <th style="text-align:right">CAGR hist.</th>
            <th style="text-align:right">Volatilidad</th>
          </tr>
        </thead>
        <tbody>
          ${r.portfolio.map((p, i) => `
            <tr>
              <td style="color:var(--text-muted)">#${i+1}</td>
              <td><strong>${p.ticker}</strong></td>
              <td style="color:var(--text-muted)">${p.short_name || "—"}</td>
              <td style="color:var(--text-muted);font-size:12px">${p.sector || "—"}</td>
              <td style="text-align:right">${(p.weight*100).toFixed(1)}%</td>
              <td style="text-align:right;color:var(--green)">${p.cagr_pct != null ? "+" + p.cagr_pct + "%" : "—"}</td>
              <td style="text-align:right">${p.volatility_pct != null ? p.volatility_pct + "%" : "—"}</td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>`;
  document.getElementById("bm-result").innerHTML = html;
}

// ============================================================
// SIMULACIÓN MONTE CARLO (Épica 3)
// ============================================================
function renderSimulation() {
  const prefill = PF.lastResult ? PF.lastResult.metrics : null;
  const capital  = prefill ? 100000 : 100000;
  const expRet   = prefill ? prefill.expected_return_pct : 10;
  const vol      = prefill ? prefill.volatility_pct : 20;

  const contentEl = document.getElementById("content");
  contentEl.innerHTML = `
    <div class="pf-section">
      <div class="pf-card">
        <div class="pf-card-title">Simulación de Comportamiento del Cliente</div>
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:16px">
          Simula probabilísticamente cómo evoluciona el capital considerando recomendaciones
          periódicas de rebalanceo, probabilidad de aceptación y retiro ante pérdidas extremas.
        </p>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Capital inicial (USD)</label>
            <input id="sim-capital" class="form-input" type="number" value="${capital}">
          </div>
          <div class="form-group">
            <label class="form-label">Retorno esperado anual (%)</label>
            <input id="sim-exp-ret" class="form-input" type="number" step="0.1" value="${expRet}">
          </div>
          <div class="form-group">
            <label class="form-label">Volatilidad anual (%)</label>
            <input id="sim-vol" class="form-input" type="number" step="0.1" value="${vol}">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Horizonte (años)</label>
            <input id="sim-years" class="form-input" type="number" min="1" max="10" value="3">
          </div>
          <div class="form-group">
            <label class="form-label">Simulaciones</label>
            <input id="sim-n" class="form-input" type="number" min="100" max="2000" step="100" value="500">
          </div>
          <div class="form-group">
            <label class="form-label">Pérdida máx. tolerable: <strong id="sim-loss-pct-val">20%</strong></label>
            <input id="sim-loss-pct" class="risk-slider" type="range" min="5" max="80" value="20"
                   oninput="onSimLossSlider(this.value)">
          </div>
        </div>
        <div style="display:flex;gap:10px;align-items:center">
          <button class="btn-primary" id="sim-btn" onclick="submitSimulation()">Ejecutar simulación</button>
          <span id="sim-loading" style="font-size:13px;color:var(--text-muted);display:none">Simulando...</span>
        </div>
      </div>
      <div id="sim-result"></div>
    </div>`;
}

function onSimLossSlider(v) {
  const el = document.getElementById("sim-loss-pct-val");
  if (el) el.textContent = v + "%";
}

async function submitSimulation() {
  const capital  = parseFloat(document.getElementById("sim-capital")?.value)  || 100000;
  const expRet   = parseFloat(document.getElementById("sim-exp-ret")?.value)   || 10;
  const vol      = parseFloat(document.getElementById("sim-vol")?.value)       || 20;
  const years    = parseInt(document.getElementById("sim-years")?.value)       || 3;
  const nsim     = parseInt(document.getElementById("sim-n")?.value)           || 500;
  const maxLoss  = parseInt(document.getElementById("sim-loss-pct")?.value)    || 20;

  const btn     = document.getElementById("sim-btn");
  const loading = document.getElementById("sim-loading");
  if (btn)     btn.disabled = true;
  if (loading) loading.style.display = "inline";

  try {
    const result = await apiFetch("/api/portfolio/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        initial_capital: capital,
        expected_return: expRet / 100,
        volatility:      vol / 100,
        max_loss_pct:    maxLoss / 100,
        years:           years,
        n_simulations:   nsim,
      }),
    });
    PF.lastSimulation = result;
    renderSimResult(result, capital);
  } catch (e) {
    document.getElementById("sim-result").innerHTML =
      `<div class="pf-card" style="color:var(--red)">Error: ${e.message}</div>`;
  } finally {
    if (btn)     btn.disabled = false;
    if (loading) loading.style.display = "none";
  }
}

function renderSimResult(r, capital) {
  const html = `
    <!-- Métricas clave -->
    <div class="pf-section-title">Resultados de la simulación (${r.total_recommendations} recomendaciones emitidas)</div>
    <div class="metrics-grid" style="grid-template-columns:repeat(auto-fill,minmax(160px,1fr))">
      <div class="metric-card">
        <div class="metric-label">Capital final promedio</div>
        <div class="metric-value" style="color:${r.final_capital_mean >= capital ? 'var(--green)' : 'var(--red)'}">
          ${fmtUSD(r.final_capital_mean)}
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Capital P10</div>
        <div class="metric-value">${fmtUSD(r.final_capital_p10)}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Capital P90</div>
        <div class="metric-value">${fmtUSD(r.final_capital_p90)}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Comisiones cobradas</div>
        <div class="metric-value">${fmtUSD(r.total_commissions_mean)}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Tasa de retiro</div>
        <div class="metric-value" style="color:${r.withdrawal_rate>30?'var(--red)':'var(--text)'}">
          ${r.withdrawal_rate}%
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-label">Recs. aceptadas (prom.)</div>
        <div class="metric-value">${r.accepted_recommendations_mean}</div>
      </div>
    </div>

    <!-- Gráfico de trayectorias -->
    <div class="chart-wrap">
      <div class="pf-section-title" style="border:none;padding:0;margin-bottom:8px">
        Distribución de capital — Media ± P10/P90
      </div>
      <div id="sim-chart" style="height:300px"></div>
    </div>`;

  document.getElementById("sim-result").innerHTML = html;
  renderSimChart(r, capital);
}

function renderSimChart(r, capital) {
  if (typeof Plotly === "undefined") return;
  const xLabels = r.periods.map(p => `Semana ${p}`);
  const traces = [
    {
      x: xLabels, y: r.capital_p90, name: "P90",
      fill: "tonexty", fillcolor: "rgba(63,185,80,0.12)",
      line: { color: "rgba(63,185,80,0.4)", width: 1 }, mode: "lines",
    },
    {
      x: xLabels, y: r.capital_mean, name: "Media",
      line: { color: "#0078bf", width: 2 }, mode: "lines",
    },
    {
      x: xLabels, y: r.capital_p10, name: "P10",
      fill: "tonexty", fillcolor: "rgba(248,81,73,0.08)",
      line: { color: "rgba(248,81,73,0.4)", width: 1 }, mode: "lines",
    },
    {
      x: xLabels, y: Array(xLabels.length).fill(capital), name: "Capital inicial",
      line: { color: "#c49b25", width: 1, dash: "dot" }, mode: "lines",
    },
  ];
  const layout = {
    ...PLOTLY_LAYOUT_BASE,
    margin: { t: 10, r: 20, b: 50, l: 80 },
    yaxis: { ...PLOTLY_LAYOUT_BASE.yaxis, title: "Capital (USD)", tickformat: ",.0f" },
    legend: { orientation: "h", y: -0.2 },
    showlegend: true,
  };
  Plotly.newPlot("sim-chart", traces, layout, PLOTLY_CONFIG);
}

// ============================================================
// OVERRIDES - SISTEMA RECOMENDADOR FINPUC
// ============================================================

PLOTLY_LAYOUT_BASE.paper_bgcolor = "#fffaf2";
PLOTLY_LAYOUT_BASE.plot_bgcolor = "#fffaf2";
PLOTLY_LAYOUT_BASE.font = { color: "#1c2733", size: 11 };
PLOTLY_LAYOUT_BASE.xaxis = { gridcolor: "#d8d2c8", linecolor: "#d8d2c8", zerolinecolor: "#d8d2c8" };
PLOTLY_LAYOUT_BASE.yaxis = { gridcolor: "#d8d2c8", linecolor: "#d8d2c8", zerolinecolor: "#d8d2c8" };

PF.activeNav = "recommendation";
PF.currentModule = "acciones";
PF.selectedProfile = "neutro";
PF.lastInputs = {
  capital: 100000,
  targetHoldings: 10,
  candidatePoolSize: "",
  sector: "",
};

const PF_PROFILES = {
  muy_conservador: {
    label: "Muy conservador",
    alpha: "0%",
    alphaNum: 0.00,
    desc: "No admite perdidas sobre el capital.",
    universe: "30-50 acciones, Utilities y Consumer Defensive, sesgo a dividendos.",
    method: "Minima varianza global",
    cvar: "99%",
  },
  conservador: {
    label: "Conservador",
    alpha: "5%",
    alphaNum: 0.05,
    desc: "Tolera perdidas minimas y privilegia estabilidad.",
    universe: "50-80 acciones con sesgo a dividendos y menor volatilidad.",
    method: "Minima varianza global",
    cvar: "95%",
  },
  neutro: {
    label: "Neutro",
    alpha: "15%",
    alphaNum: 0.15,
    desc: "Equilibra retorno esperado y riesgo.",
    universe: "80-120 acciones sobre el universo F5.",
    method: "Media-varianza de Markowitz",
    cvar: "90%",
  },
  arriesgado: {
    label: "Arriesgado",
    alpha: "30%",
    alphaNum: 0.30,
    desc: "Acepta mas volatilidad para capturar crecimiento.",
    universe: "100-150 acciones con mas exposicion a sectores de crecimiento.",
    method: "Media-varianza de Markowitz",
    cvar: "85%",
  },
  muy_arriesgado: {
    label: "Muy arriesgado",
    alpha: "40%",
    alphaNum: 0.40,
    desc: "Opera sobre el universo F5 completo.",
    universe: "Universo F5 completo, con holdings finales recortados al objetivo.",
    method: "Maximo retorno esperado",
    cvar: "80%",
  },
};

function goHome() {
  State.currentSector = null;
  State.currentTicker = null;
  State.sortKey = null;
  State.sortAsc = true;
  State.filterText = "";
  State.currentPage = 1;
  setActiveSector(null);
  setNavState("home");
  showContent(`
    <div class="welcome">
      <div class="welcome-panel">
        <div class="welcome-kicker">Universo F5</div>
        <h3>Exploracion del universo operativo</h3>
        <p>Selecciona un sector para revisar acciones, metricas historicas y antecedentes del universo filtrado que alimenta el sistema FinPUC.</p>
      </div>
    </div>
  `);
  window.location.hash = "#/";
}

function setNavState(view) {
  const btnHome = document.getElementById("btn-home");
  const btnSector = document.getElementById("btn-sector");
  const sep = document.getElementById("topbar-sep");
  const current = document.getElementById("breadcrumb-current");

  if (view === "home") {
    btnHome.style.display = "none";
    btnSector.style.display = "none";
    sep.style.display = "none";
    current.textContent = PF.currentModule === "portafolios" ? "Sistema recomendador FinPUC" : "Selecciona un sector del universo F5";
  } else if (view === "sector") {
    btnHome.style.display = "flex";
    btnSector.style.display = "none";
    sep.style.display = "none";
    current.textContent = State.currentSector || "";
  } else if (view === "stock") {
    btnHome.style.display = "flex";
    btnSector.style.display = "flex";
    sep.style.display = "inline";
    document.getElementById("btn-sector-label").textContent = State.currentSector || "Sector";
    current.textContent = State.currentTicker || "";
  }
}

function switchModule(mod) {
  PF.currentModule = mod;
  const tabUniverse = document.getElementById("tab-acciones");
  const tabFinpuc = document.getElementById("tab-portafolios");
  const sectorLabel = document.getElementById("sector-label");
  const sectorList = document.getElementById("sector-list");
  const portNav = document.getElementById("portfolio-nav");

  if (mod === "portafolios") {
    tabUniverse.classList.remove("active");
    tabFinpuc.classList.add("active");
    sectorLabel.style.display = "none";
    sectorList.style.display = "none";
    portNav.style.display = "block";
    setNavState("home");
    pfNavGo(PF.activeNav);
    return;
  }

  tabFinpuc.classList.remove("active");
  tabUniverse.classList.add("active");
  sectorLabel.style.display = "";
  sectorList.style.display = "";
  portNav.style.display = "none";
  goHome();
}

function pfNavGo(section) {
  PF.activeNav = section;
  ["recommendation", "scenarios", "simulate", "methodology"].forEach(id => {
    document.getElementById("pnav-" + id)?.classList.remove("active");
  });
  document.getElementById("pnav-" + section)?.classList.add("active");
  setNavState("home");

  switch (section) {
    case "recommendation":
      renderPfForm();
      break;
    case "scenarios":
      renderScenarioView();
      break;
    case "simulate":
      renderSimulation();
      break;
    case "methodology":
      renderMethodology();
      break;
  }
}

function pfSelectProfile(key) {
  PF.selectedProfile = key;
  Object.keys(PF_PROFILES).forEach(profileKey => {
    document.getElementById("pf-card-" + profileKey)?.classList.toggle("selected", key === profileKey);
  });
  renderMethodologySummary(key);
}

function renderMethodologySummary(profileKey) {
  const profile = PF_PROFILES[profileKey];
  const box = document.getElementById("pf-methodology-summary");
  if (!profile || !box) return;

  box.innerHTML = `
    <div class="methodology-chip-row">
      <span class="methodology-chip">Motor activo: Modelo base FinPUC</span>
      <span class="methodology-chip">Constructor: ${profile.method}</span>
      <span class="methodology-chip">CVaR beta = ${profile.cvar}</span>
      <span class="methodology-chip">alpha_p = ${profile.alpha}</span>
    </div>
    <div class="methodology-copy">
      El backend resuelve automaticamente la estrategia segun el perfil, aplica filtros F5,
      calcula CVaR historico, genera escenarios y reporta validacion out-of-sample.
      Black-Litterman queda declarado como fase futura del informe.
    </div>
    <div class="methodology-copy methodology-copy-muted">Subuniverso recomendado: ${profile.universe}</div>
  `;
}

function renderPfForm() {
  const profileCards = Object.entries(PF_PROFILES).map(([key, profile]) => `
    <button class="profile-card ${key === PF.selectedProfile ? "selected" : ""}" type="button"
            id="pf-card-${key}" onclick="pfSelectProfile('${key}')">
      <div class="profile-card-alpha">${profile.alpha}</div>
      <div class="profile-card-name">${profile.label}</div>
      <div class="profile-card-desc">${profile.desc}</div>
      <div class="profile-card-foot">${profile.method}</div>
    </button>
  `).join("");

  const sectorOptions = (State.sectors || [])
    .map(sector => `<option value="${esc(sector.sector)}">${esc(sector.sector)}</option>`)
    .join("");

  const contentEl = document.getElementById("content");
  contentEl.innerHTML = `
    <div class="pf-section">
      <div class="hero-card">
        <div class="hero-eyebrow">Sistema recomendador FinPUC</div>
        <h2 class="hero-title">Recomendacion de portafolio</h2>
        <p class="hero-copy">
          Flujo principal para perfilar al cliente, construir la cartera base, revisar escenarios
          y dejar la simulacion del cliente como paso operacional siguiente.
        </p>
      </div>

      <div class="pf-card">
        <div class="step-header">
          <div class="step-index">1</div>
          <div>
            <div class="pf-card-title">Perfil de riesgo</div>
            <div class="step-copy">Cinco perfiles del informe con alpha_p y CVaR diferenciados.</div>
          </div>
        </div>
        <div class="profile-grid">${profileCards}</div>
      </div>

      <div class="pf-card">
        <div class="step-header">
          <div class="step-index">2</div>
          <div>
            <div class="pf-card-title">Parametros del portafolio</div>
            <div class="step-copy">Separacion entre holdings finales y universo evaluado.</div>
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Capital inicial (USD)</label>
            <input id="pf-capital" class="form-input" type="number" min="1000" step="1000" value="${PF.lastInputs.capital}">
          </div>
          <div class="form-group">
            <label class="form-label">Holdings finales</label>
            <select id="pf-target-holdings" class="form-select">
              ${[5, 8, 10, 12, 15, 20, 25, 30].map(v => `<option value="${v}" ${PF.lastInputs.targetHoldings === v ? "selected" : ""}>${v} acciones</option>`).join("")}
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Universo evaluado</label>
            <select id="pf-candidate-pool" class="form-select">
              <option value="" ${PF.lastInputs.candidatePoolSize === "" ? "selected" : ""}>Automatico por perfil</option>
              <option value="40">40 acciones</option>
              <option value="65">65 acciones</option>
              <option value="100">100 acciones</option>
              <option value="125">125 acciones</option>
              <option value="150">150 acciones</option>
              <option value="300">300 acciones</option>
              <option value="636">Universo F5 completo</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Sector focal (opcional)</label>
            <select id="pf-sector" class="form-select">
              <option value="">Todos los sectores</option>
              ${sectorOptions}
            </select>
          </div>
        </div>
      </div>

      <div class="pf-card">
        <div class="step-header">
          <div class="step-index">3</div>
          <div>
            <div class="pf-card-title">Resumen metodologico</div>
            <div class="step-copy">Se explicita el motor activo y las limitaciones de la version actual.</div>
          </div>
        </div>
        <div id="pf-methodology-summary" class="methodology-summary"></div>
      </div>

      <div class="pf-card">
        <div class="step-header">
          <div class="step-index">4</div>
          <div>
            <div class="pf-card-title">Generar recomendacion</div>
            <div class="step-copy">La estrategia se resuelve automaticamente en backend a partir del perfil.</div>
          </div>
        </div>
        <div class="action-row">
          <button class="btn-primary" id="pf-submit-btn" onclick="submitPortfolioForm()">Generar recomendacion</button>
          <span id="pf-loading" class="subtle-status" style="display:none">Ejecutando optimizacion y escenarios...</span>
        </div>
      </div>

      <div id="pf-result"></div>
    </div>
  `;

  const sectorEl = document.getElementById("pf-sector");
  if (sectorEl) sectorEl.value = PF.lastInputs.sector || "";
  renderMethodologySummary(PF.selectedProfile);
}

async function submitPortfolioForm() {
  const capital = parseFloat(document.getElementById("pf-capital")?.value) || 100000;
  const targetHoldings = parseInt(document.getElementById("pf-target-holdings")?.value, 10) || 10;
  const candidatePoolValue = document.getElementById("pf-candidate-pool")?.value || "";
  const sector = document.getElementById("pf-sector")?.value || "";
  const btn = document.getElementById("pf-submit-btn");
  const loading = document.getElementById("pf-loading");

  PF.lastInputs = {
    capital,
    targetHoldings,
    candidatePoolSize: candidatePoolValue,
    sector,
  };

  const payload = {
    initial_capital: capital,
    profile: PF.selectedProfile,
    strategy: "auto",
    target_holdings: targetHoldings,
  };
  if (candidatePoolValue) payload.candidate_pool_size = parseInt(candidatePoolValue, 10);
  if (sector) payload.sector = sector;

  if (btn) btn.disabled = true;
  if (loading) loading.style.display = "inline";

  try {
    const result = await apiFetch("/api/portfolio/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    PF.lastResult = result;
    renderPfResult(result, capital);
  } catch (e) {
    document.getElementById("pf-result").innerHTML = `<div class="pf-card callout callout-danger">Error al generar la recomendacion: ${esc(e.message)}</div>`;
  } finally {
    if (btn) btn.disabled = false;
    if (loading) loading.style.display = "none";
  }
}

function renderPfResult(result, capital) {
  const validationHtml = result.validation ? `
    <div class="validation-pill">
      Validacion out-of-sample ${esc(result.validation.period)}:
      <strong>${result.validation.total_return_pct > 0 ? "+" : ""}${result.validation.total_return_pct}%</strong>
      anualizado ${result.validation.annualized_return_pct > 0 ? "+" : ""}${result.validation.annualized_return_pct}%
    </div>
  ` : "";

  const methodology = result.methodology || {};
  const universe = result.universe || {};
  const weeklyCycle = result.weekly_cycle || {};
  const scenarios = result.scenarios || {};

  document.getElementById("pf-result").innerHTML = `
    <div class="pf-card result-hero">
      <div class="hero-eyebrow">Resultado activo</div>
      <div class="result-hero-grid">
        <div>
          <div class="result-title">${esc(result.profile_label || result.risk_level || "")}</div>
          <div class="result-copy">${esc(result.profile_description || "")}</div>
          <div class="result-copy result-copy-muted">${esc(methodology.engine_label || "")}</div>
        </div>
        <div class="result-meta">
          <div><span>Capital</span><strong>${fmtUSD(capital)}</strong></div>
          <div><span>Constructor</span><strong>${esc(result.metrics?.method_label || methodology.constructor_label || "—")}</strong></div>
          <div><span>Comision</span><strong>${result.commission_rate_pct}% anual</strong></div>
          <div><span>CVaR beta</span><strong>${result.cvar_level_pct || "—"}%</strong></div>
        </div>
      </div>
      ${validationHtml}
    </div>

    <div class="summary-grid">
      <div class="summary-card">
        <div class="summary-label">Retorno esperado</div>
        <div class="summary-value">${result.metrics.expected_return_pct > 0 ? "+" : ""}${result.metrics.expected_return_pct}%</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Volatilidad anual</div>
        <div class="summary-value">${result.metrics.volatility_pct}%</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Sharpe</div>
        <div class="summary-value">${result.metrics.sharpe_ratio}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">CVaR</div>
        <div class="summary-value">${result.cvar_pct != null ? result.cvar_pct + "%" : "—"}</div>
      </div>
    </div>

    <div class="detail-grid">
      <div class="pf-card">
        <div class="pf-section-title">Origen metodologico</div>
        <div class="methodology-chip-row">
          <span class="methodology-chip">alpha_p = ${Math.round((result.alpha_p || 0) * 100)}%</span>
          <span class="methodology-chip">CVaR beta = ${result.cvar_level_pct}%</span>
          <span class="methodology-chip">Holdings = ${universe.target_holdings || "—"}</span>
          <span class="methodology-chip">Universo operativo = ${methodology.optimizer_universe_size || "—"}</span>
        </div>
        <div class="data-list">
          <div><span>Universo</span><strong>${esc(universe.name || "Universo F5")}</strong></div>
          <div><span>F5 disponible</span><strong>${universe.total_f5_count || "—"} acciones</strong></div>
          <div><span>Candidatas evaluadas</span><strong>${universe.candidate_pool_size || "—"}</strong></div>
          <div><span>Calibracion</span><strong>${esc(result.data_split.calibration_start)} a ${esc(result.data_split.calibration_end)}</strong></div>
          <div><span>Validacion</span><strong>${esc(result.data_split.validation_start)} a ${esc(result.data_split.validation_end)}</strong></div>
          <div><span>Filtro sectorial</span><strong>${esc(universe.sector_filter || "Sin filtro manual")}</strong></div>
        </div>
      </div>
      <div class="pf-card">
        <div class="pf-section-title">Ciclo semanal y supuestos</div>
        <div class="data-list">
          <div><span>Cadencia</span><strong>${esc(weeklyCycle.cadence || "Semanal")}</strong></div>
          <div><span>Recomendacion</span><strong>${esc(weeklyCycle.rebalancing || "—")}</strong></div>
          <div><span>Aceptacion cliente</span><strong>${esc(weeklyCycle.client_acceptance || "—")}</strong></div>
          <div><span>Retiro</span><strong>${esc(weeklyCycle.client_withdrawal || "—")}</strong></div>
          <div><span>Dividendos</span><strong>${esc(weeklyCycle.dividends || "—")}</strong></div>
        </div>
      </div>
    </div>

    <div class="pf-card">
      <div class="pf-section-title">Escenarios resumidos</div>
      <div class="scenario-grid">
        <div class="scenario-card favorable">
          <div class="scenario-label">Favorable (p90)</div>
          <div class="scenario-ret">${scenarios.favorable?.annual_return_pct > 0 ? "+" : ""}${scenarios.favorable?.annual_return_pct ?? "—"}%</div>
          <div class="scenario-cap">Ano 5: <strong>${fmtUSD(scenarios.favorable?.capital_by_year?.["5"])}</strong></div>
        </div>
        <div class="scenario-card neutro">
          <div class="scenario-label">Neutro (p50)</div>
          <div class="scenario-ret">${scenarios.neutro?.annual_return_pct > 0 ? "+" : ""}${scenarios.neutro?.annual_return_pct ?? "—"}%</div>
          <div class="scenario-cap">Ano 5: <strong>${fmtUSD(scenarios.neutro?.capital_by_year?.["5"])}</strong></div>
        </div>
        <div class="scenario-card desfavorable">
          <div class="scenario-label">Desfavorable (p10)</div>
          <div class="scenario-ret">${scenarios.desfavorable?.annual_return_pct > 0 ? "+" : ""}${scenarios.desfavorable?.annual_return_pct ?? "—"}%</div>
          <div class="scenario-cap">Ano 5: <strong>${fmtUSD(scenarios.desfavorable?.capital_by_year?.["5"])}</strong></div>
        </div>
      </div>
      <div class="action-row">
        <button class="btn-secondary" type="button" onclick="pfNavGo('scenarios')">Abrir vista de escenarios</button>
        <button class="btn-secondary" type="button" onclick="fetchBenchmarkComparison()">Cargar caso base + benchmark</button>
      </div>
      <div id="benchmark-comparison"></div>
    </div>

    <div class="pf-card" style="padding:0;overflow:hidden">
      <div class="table-header-inline">
        <div class="pf-section-title" style="margin:0;border:none">Composicion del portafolio</div>
        <div class="table-header-copy">${result.portfolio.length} posiciones finales</div>
      </div>
      <table class="pf-table">
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Empresa</th>
            <th>Sector</th>
            <th style="text-align:right">Peso</th>
            <th style="text-align:right">CAGR</th>
            <th style="text-align:right">Volatilidad</th>
            <th style="text-align:right">Dividend yield</th>
          </tr>
        </thead>
        <tbody>
          ${result.portfolio.map(item => `
            <tr>
              <td><strong>${esc(item.ticker)}</strong></td>
              <td>${esc(item.short_name || "—")}</td>
              <td>${esc(item.sector || "—")}</td>
              <td style="text-align:right">${(item.weight * 100).toFixed(1)}%</td>
              <td style="text-align:right">${item.cagr_pct != null ? (item.cagr_pct > 0 ? "+" : "") + item.cagr_pct + "%" : "—"}</td>
              <td style="text-align:right">${item.volatility_pct != null ? item.volatility_pct + "%" : "—"}</td>
              <td style="text-align:right">${item.dividend_yield_pct != null ? item.dividend_yield_pct + "%" : "—"}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
  queueMathTypeset();
}

async function fetchBenchmarkComparison(targetId = "benchmark-comparison") {
  if (!PF.lastResult) return;

  const getLastInputValue = (keys, fallback) => {
    for (const key of keys) {
      const value = PF.lastInputs?.[key];
      if (value !== undefined && value !== null && value !== "") return value;
    }
    return fallback;
  };

  const holdings = parseInt(String(getLastInputValue(["target_holdings", "targetHoldings"], 10)), 10) || 10;
  const candidatePool = getLastInputValue(["candidate_pool_size", "candidatePoolSize"], "");
  const sector = getLastInputValue(["sector"], "");

  const benchParams = new URLSearchParams({ target_holdings: String(holdings) });
  if (candidatePool) benchParams.set("candidate_pool_size", String(candidatePool));
  if (sector) benchParams.set("sector", String(sector));

  const baseParams = new URLSearchParams({ n: String(holdings) });
  if (sector) baseParams.set("sector", String(sector));

  try {
    const [baseCase, benchmark] = await Promise.all([
      apiFetch(`/api/portfolio/base_case?${baseParams.toString()}`),
      apiFetch(`/api/portfolio/benchmark?${benchParams.toString()}`),
    ]);
    PF.lastBaseCase = baseCase;
    PF.lastBenchmark = benchmark;
    renderBenchmarkComparison(benchmark, baseCase, targetId);
  } catch (e) {
    const target = document.getElementById(targetId);
    if (target) {
      target.innerHTML = `<div class="callout callout-danger">No fue posible cargar las comparaciones: ${esc(e.message)}</div>`;
    }
  }
}

function renderBenchmarkComparison(benchmark, baseCase, targetId = "benchmark-comparison") {
  const target = document.getElementById(targetId);
  if (!target || !PF.lastResult) return;

  const base = PF.lastResult.metrics || {};
  const simId = `${targetId}-base-sim`;
  target.innerHTML = `
    <div class="comparison-card">
      <div class="pf-section-title" style="margin-bottom:8px;border:none;padding:0">Comparacion academica</div>
      <table class="comparison-table">
        <thead>
          <tr>
            <th>Medida</th>
            <th>${esc(PF.lastResult.methodology?.label || "Modelo FinPUC")}</th>
            <th>${esc(baseCase?.metrics?.method_label || "Caso base")}</th>
            <th>${esc(benchmark?.metrics?.method_label || "Benchmark")}</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Retorno esperado</td>
            <td>${base.expected_return_pct > 0 ? "+" : ""}${base.expected_return_pct}%</td>
            <td>${baseCase?.metrics?.expected_return_pct > 0 ? "+" : ""}${baseCase?.metrics?.expected_return_pct ?? "—"}%</td>
            <td>${benchmark?.metrics?.expected_return_pct > 0 ? "+" : ""}${benchmark?.metrics?.expected_return_pct ?? "—"}%</td>
          </tr>
          <tr>
            <td>Volatilidad anual</td>
            <td>${base.volatility_pct ?? "—"}%</td>
            <td>${baseCase?.metrics?.volatility_pct ?? "—"}%</td>
            <td>${benchmark?.metrics?.volatility_pct ?? "—"}%</td>
          </tr>
          <tr>
            <td>Constructor</td>
            <td>${esc(base.method_label || base.method || "—")}</td>
            <td>${esc(baseCase?.metrics?.rebalance_policy || baseCase?.metrics?.method_label || "—")}</td>
            <td>${esc(benchmark?.metrics?.method_label || benchmark?.metrics?.method || "—")}</td>
          </tr>
        </tbody>
      </table>
      <div class="action-row" style="margin-top:12px">
        <button class="btn-secondary" type="button" onclick="simulateBaseCaseComparison('${targetId}')">Simular caso base</button>
      </div>
      <div id="${simId}"></div>
    </div>
  `;
}

async function simulateBaseCaseComparison(targetId = "benchmark-comparison") {
  const target = document.getElementById(`${targetId}-base-sim`);
  const baseCase = PF.lastBaseCase;
  if (!target || !baseCase) return;
  target.innerHTML = `<div class="callout">Simulando caso base...</div>`;

  const defaults = baseCase.simulation_defaults || {};
  const payload = {
    initial_capital: defaults.initial_capital ?? 100000,
    max_loss_pct: ((defaults.max_loss_pct ?? 15.0) / 100.0),
    expected_return: ((defaults.expected_return_pct ?? 0.0) / 100.0),
    volatility: ((defaults.volatility_pct ?? 0.0) / 100.0),
    years: defaults.years ?? 3,
    n_simulations: 500,
    commission_rate_pct: defaults.commission_rate_pct ?? 1.0,
    p2_acceptance_prob_pct: defaults.p2_acceptance_prob_pct ?? 70.0,
    rebalance_freq_weeks: defaults.rebalance_freq_weeks ?? 4,
    rebalance_return_boost_pct: defaults.rebalance_return_boost_pct ?? 0.0,
  };

  try {
    const result = await apiFetch("/api/portfolio/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    target.innerHTML = `
      <div class="data-list" style="margin-top:12px">
        <div><span>Capital final (media)</span><strong>${fmtUSD(result.final_capital_mean)}</strong></div>
        <div><span>P10</span><strong>${fmtUSD(result.final_capital_p10)}</strong></div>
        <div><span>P90</span><strong>${fmtUSD(result.final_capital_p90)}</strong></div>
        <div><span>Tasa de retiro</span><strong>${result.withdrawal_rate}%</strong></div>
      </div>
    `;
  } catch (error) {
    target.innerHTML = `<div class="callout callout-danger">No fue posible simular el caso base: ${esc(error.message)}</div>`;
  }
}

async function fetchReturnDiagnostics(targetId = "returns-diagnostics") {
  const target = document.getElementById(targetId);
  if (target) target.innerHTML = `<div class="callout">Calculando distribuciones de retornos...</div>`;

  const getLastInputValue = (keys, fallback) => {
    for (const key of keys) {
      const value = PF.lastInputs?.[key];
      if (value !== undefined && value !== null && value !== "") return value;
    }
    return fallback;
  };

  const sector = getLastInputValue(["sector"], "");
  const params = new URLSearchParams({ n: "30", order: "market_cap", bins: "30" });
  if (sector) params.set("sector", String(sector));

  try {
    const result = await apiFetch(`/api/portfolio/diagnostics/returns?${params.toString()}`);
    renderReturnDiagnosticsBySector(result, targetId);
  } catch (error) {
    if (target) {
      target.innerHTML = `<div class="callout callout-danger">No fue posible calcular distribuciones: ${esc(error.message)}</div>`;
    }
  }
}

function renderReturnDiagnostics(result, targetId = "returns-diagnostics") {
  const target = document.getElementById(targetId);
  if (!target) return;
  const summary = result.summary || {};
  const pooled = result.pooled || {};
  const assets = Array.isArray(result.assets) ? result.assets.slice() : [];
  assets.sort((a, b) => (a.jarque_bera_p ?? 1) - (b.jarque_bera_p ?? 1));
  const worst = assets.slice(0, 10);

  target.innerHTML = `
    <div class="comparison-card">
      <div class="data-list" style="margin-bottom:14px">
        <div><span>Ventana calibracion</span><strong>${esc(result.calibration_window?.start || "—")} → ${esc(result.calibration_window?.end || "—")}</strong></div>
        <div><span>Activos analizados</span><strong>${summary.n_assets ?? worst.length}</strong></div>
        <div><span>JB (p≥0.05)</span><strong>${summary.jarque_bera_pass_rate_5pct != null ? Math.round(summary.jarque_bera_pass_rate_5pct * 100) + "%" : "—"}</strong></div>
        <div><span>Normaltest (p≥0.05)</span><strong>${summary.normaltest_pass_rate_5pct != null ? Math.round(summary.normaltest_pass_rate_5pct * 100) + "%" : "—"}</strong></div>
        <div><span>Pooled skew</span><strong>${pooled.skew ?? "—"}</strong></div>
        <div><span>Pooled kurtosis</span><strong>${pooled.kurtosis_excess ?? "—"}</strong></div>
      </div>

      <div class="pf-section-title" style="margin-bottom:8px;border:none;padding:0">Peores p-values (JB)</div>
      <table class="comparison-table">
        <thead>
          <tr>
            <th>Ticker</th>
            <th style="text-align:right">n</th>
            <th style="text-align:right">mean</th>
            <th style="text-align:right">std</th>
            <th style="text-align:right">JB p</th>
            <th style="text-align:right">Normaltest p</th>
          </tr>
        </thead>
        <tbody>
          ${worst.map(a => `
            <tr>
              <td><strong>${esc(a.ticker)}</strong></td>
              <td style="text-align:right">${esc(String(a.n ?? "—"))}</td>
              <td style="text-align:right">${a.mean_daily_pct != null ? a.mean_daily_pct.toFixed(4) + "%" : "—"}</td>
              <td style="text-align:right">${a.std_daily_pct != null ? a.std_daily_pct.toFixed(4) + "%" : "—"}</td>
              <td style="text-align:right">${a.jarque_bera_p != null ? a.jarque_bera_p.toFixed(6) : "—"}</td>
              <td style="text-align:right">${a.normaltest_p != null ? a.normaltest_p.toFixed(6) : "—"}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
      <div class="methodology-copy" style="margin-top:12px">${esc(summary.notes || "")}</div>
    </div>
  `;
}

function _histogramToPlotlyBars(histogram) {
  const edges = Array.isArray(histogram?.bin_edges_pct) ? histogram.bin_edges_pct : [];
  const counts = Array.isArray(histogram?.counts) ? histogram.counts : [];
  if (edges.length < 2 || counts.length < 1) return null;
  const x = [];
  for (let i = 0; i < Math.min(counts.length, edges.length - 1); i++) {
    x.push((edges[i] + edges[i + 1]) / 2.0);
  }
  const binWidth = (edges[1] - edges[0]) || null;
  const totalCount = counts.reduce((acc, v) => acc + (Number.isFinite(v) ? v : 0), 0);
  return { x, y: counts, binWidth, totalCount };
}

function _logGamma(z) {
  // Lanczos approximation (Numerical Recipes / common JS implementations)
  const p = [
    676.5203681218851,
    -1259.1392167224028,
    771.3234287776531,
    -176.6150291621406,
    12.507343278686905,
    -0.13857109526572012,
    9.984369578019572e-6,
    1.5056327351493116e-7,
  ];

  if (z < 0.5) {
    return Math.log(Math.PI) - Math.log(Math.sin(Math.PI * z)) - _logGamma(1 - z);
  }

  z -= 1;
  let x = 0.99999999999980993;
  for (let i = 0; i < p.length; i++) {
    x += p[i] / (z + i + 1);
  }
  const t = z + p.length - 0.5;
  return 0.5 * Math.log(2 * Math.PI) + (z + 0.5) * Math.log(t) - t + Math.log(x);
}

function _studentTPdf(x, df, loc, scale) {
  const v = df;
  const s = scale;
  if (!isFinite(v) || !isFinite(loc) || !isFinite(s) || s <= 0 || v <= 0) return NaN;
  const z = (x - loc) / s;
  const logCoeff = _logGamma((v + 1) / 2) - _logGamma(v / 2) - 0.5 * Math.log(v * Math.PI) - Math.log(Math.abs(s));
  const logKernel = -((v + 1) / 2) * Math.log(1 + (z * z) / v);
  return Math.exp(logCoeff + logKernel);
}

function _fitLabel(fit) {
  const best = fit?.best_by_bic;
  if (!best) return "N/A";
  if (best === "normal") return "Normal";
  if (best === "student_t") {
    const cand = Array.isArray(fit?.candidates) ? fit.candidates.find(c => c.name === "student_t") : null;
    const df = cand?.params?.df;
    return df != null ? `Student-t (df=${Number(df).toFixed(2)})` : "Student-t";
  }
  if (best === "johnsonsu") return "Johnson SU (asimetria + colas)";
  return String(best);
}

function _extractStudentTParams(fit) {
  const cand = Array.isArray(fit?.candidates) ? fit.candidates.find(c => c.name === "student_t") : null;
  const p = cand?.params || null;
  if (!p) return null;
  const df = Number(p.df);
  const loc = Number(p.loc_pct);
  const scale = Number(p.scale_pct);
  if (!isFinite(df) || !isFinite(loc) || !isFinite(scale) || scale <= 0) return null;
  return { df, loc, scale };
}

function renderHistogramChart(containerId, histogram, title, normalFit) {
  if (typeof Plotly === "undefined") return;
  const bars = _histogramToPlotlyBars(histogram);
  if (!bars) return;
  const barTrace = {
    type: "bar",
    x: bars.x,
    y: bars.y,
    marker: { color: "#0f4c81" },
    opacity: 0.75,
    hovertemplate: "Retorno: %{x:.3f}%<br>Cuenta: %{y}<extra></extra>",
  };

  const traces = [barTrace];
  const mean = typeof normalFit?.mean === "number" ? normalFit.mean : null;
  const std = typeof normalFit?.std === "number" ? normalFit.std : null;
  if (mean != null && std != null && std > 0 && bars.binWidth && bars.totalCount > 0) {
    const inv = 1.0 / (std * Math.sqrt(2.0 * Math.PI));
    const yNorm = bars.x.map(x => inv * Math.exp(-0.5 * Math.pow((x - mean) / std, 2.0)) * bars.totalCount * bars.binWidth);
    traces.push({
      type: "scatter",
      mode: "lines",
      x: bars.x,
      y: yNorm,
      name: "Normal ajustada (μ,σ)",
      line: { color: "#b48a2c", width: 2 },
      hovertemplate: "Normal ajustada<br>Retorno: %{x:.3f}%<br>Frecuencia: %{y:.1f}<extra></extra>",
    });
  }

  const tFit = normalFit?.student_t;
  if (tFit && bars.binWidth && bars.totalCount > 0) {
    const yT = bars.x.map(x => {
      const pdf = _studentTPdf(x, tFit.df, tFit.loc, tFit.scale);
      if (!isFinite(pdf)) return NaN;
      return pdf * bars.totalCount * bars.binWidth;
    });
    traces.push({
      type: "scatter",
      mode: "lines",
      x: bars.x,
      y: yT,
      name: "Student-t ajustada",
      line: { color: "#1f6f52", width: 2 },
      hovertemplate: "Student-t ajustada<br>Retorno: %{x:.3f}%<br>Frecuencia: %{y:.1f}<extra></extra>",
    });
  }
  const layout = {
    ...PLOTLY_LAYOUT_BASE,
    title: title ? { text: title, x: 0, xanchor: "left", font: { size: 12 } } : undefined,
    margin: { t: title ? 30 : 12, r: 20, b: 50, l: 60 },
    xaxis: { ...PLOTLY_LAYOUT_BASE.xaxis, title: "Retorno diario (%)" },
    yaxis: { ...PLOTLY_LAYOUT_BASE.yaxis, title: "Frecuencia" },
    legend: traces.length > 1 ? { orientation: "h", y: -0.25 } : undefined,
  };
  Plotly.newPlot(containerId, traces, layout, PLOTLY_CONFIG);
}

async function loadTickerReturnDiagnostics(ticker, targetId) {
  const target = document.getElementById(targetId);
  if (!target) return;
  const t = String(ticker || "").toUpperCase();
  target.innerHTML = `<div class="callout">Cargando diagnostico de ${esc(t)}...</div>`;

  try {
    const result = await apiFetch(`/api/portfolio/diagnostics/returns/${encodeURIComponent(t)}?bins=50`);
    const summary = result.summary || {};
    const asset = result.asset || {};
    const histId = `${targetId}-hist`;
    const qqId = `${targetId}-qq`;
    const qqFit = result.qq_plot?.fit || {};
    const jb = summary.jarque_bera_p;
    const nt = summary.normaltest_p;
    const normaltestAvailable = nt !== null && nt !== undefined;
    const passesNormality = (jb !== null && jb !== undefined && jb >= 0.05) && (!normaltestAvailable || nt >= 0.05);
    const normalityLabel = (jb === null || jb === undefined) ? "N/A" : (passesNormality ? "No rechazada (alpha 5%)" : "Rechazada (alpha 5%)");
    const distFit = summary.fit || {};
    const bestFitLabel = _fitLabel(distFit);
    const studentTFit = _extractStudentTParams(distFit);

    target.innerHTML = `
      <div class="pf-card" style="margin-top:14px">
        <div class="pf-section-title">Estudio individual: ${esc(asset.ticker || t)}</div>
        <div style="color:var(--text-muted);font-size:13px;margin:-6px 0 10px">
          ${esc(asset.short_name || "")}${asset.sector ? ` | ${esc(asset.sector)}` : ""}${asset.industry ? ` | ${esc(asset.industry)}` : ""}
        </div>
        <div class="methodology-copy" style="margin-bottom:12px">
          <strong>Que es:</strong> retornos diarios (%) en la ventana de calibracion. El histograma muestra la frecuencia de retornos.
          <br><strong>Como leer:</strong> la linea naranja es una Normal ajustada con la misma media y desviacion estandar.
          <br><strong>Por que puede verse \"normal\":</strong> con bins anchos o mezcla de activos, la forma puede parecer campana; los tests detectan desviaciones pequenas cuando n es grande.
        </div>
        <div class="data-list" style="margin-bottom:14px">
          <div><span>Ventana calibracion</span><strong>${esc(result.calibration_window?.start || "N/A")} -> ${esc(result.calibration_window?.end || "N/A")}</strong></div>
          <div><span>Normalidad</span><strong>${esc(normalityLabel)}</strong></div>
          <div><span>Mejor ajuste (BIC)</span><strong>${esc(bestFitLabel)}</strong></div>
          <div><span>Mean</span><strong>${summary.mean_daily_pct != null ? summary.mean_daily_pct.toFixed(4) + "%" : "N/A"}</strong></div>
          <div><span>Std</span><strong>${summary.std_daily_pct != null ? summary.std_daily_pct.toFixed(4) + "%" : "N/A"}</strong></div>
          <div><span>Skew</span><strong>${summary.skew ?? "N/A"}</strong></div>
          <div><span>Kurtosis</span><strong>${summary.kurtosis_excess ?? "N/A"}</strong></div>
        </div>
        ${distFit?.notes ? `<div style="color:var(--text-muted);font-size:12px;margin-top:-6px;margin-bottom:12px">${esc(distFit.notes)}</div>` : ""}
        <details style="margin:-4px 0 12px">
          <summary style="cursor:pointer;color:var(--text-muted);font-size:12px">Ver p-values y n</summary>
          <div class="data-list" style="margin-top:10px">
            <div><span>n</span><strong>${esc(String(summary.n ?? "N/A"))}</strong></div>
            <div><span>Jarque-Bera p</span><strong>${summary.jarque_bera_p != null ? summary.jarque_bera_p.toFixed(6) : "N/A"}</strong></div>
            <div><span>D'Agostino p</span><strong>${summary.normaltest_p != null ? summary.normaltest_p.toFixed(6) : "N/A"}</strong></div>
          </div>
        </details>

        <div class="detail-grid">
          <div class="chart-wrap">
            <div class="pf-section-title" style="margin-bottom:8px;border:none;padding:0">Histograma de retornos</div>
            <div id="${histId}" style="height:260px"></div>
          </div>
          <div class="chart-wrap">
            <div class="pf-section-title" style="margin-bottom:8px;border:none;padding:0">QQ-plot vs Normal</div>
            <div id="${qqId}" style="height:260px"></div>
          </div>
        </div>

        <div class="action-row" style="margin-top:12px">
          <button class="btn-secondary" type="button" onclick="selectStock('${esc(t)}')">Abrir ficha (F5)</button>
        </div>

        <div style="color:var(--text-muted);font-size:12px;margin-top:10px">
          Ajuste QQ: y = ${esc(String(qqFit.slope ?? "N/A"))}x + ${esc(String(qqFit.intercept ?? "N/A"))}, r=${esc(String(qqFit.r ?? "N/A"))}.
        </div>
      </div>
    `;

    requestAnimationFrame(() => {
      renderHistogramChart(histId, result.histogram, "", { mean: summary.mean_daily_pct, std: summary.std_daily_pct, student_t: studentTFit });
      if (typeof Plotly === "undefined") return;
      const theoretical = Array.isArray(result.qq_plot?.theoretical) ? result.qq_plot.theoretical : [];
      const sample = Array.isArray(result.qq_plot?.sample) ? result.qq_plot.sample : [];
      if (!theoretical.length || !sample.length) return;
      const minX = Math.min(...theoretical);
      const maxX = Math.max(...theoretical);
      const slope = typeof qqFit.slope === "number" ? qqFit.slope : null;
      const intercept = typeof qqFit.intercept === "number" ? qqFit.intercept : null;

      const traces = [
        { type: "scatter", mode: "markers", x: theoretical, y: sample, name: "Cuantiles", marker: { size: 5, color: "#0f4c81" } },
      ];
      if (slope != null && intercept != null && isFinite(minX) && isFinite(maxX)) {
        traces.push({
          type: "scatter",
          mode: "lines",
          x: [minX, maxX],
          y: [slope * minX + intercept, slope * maxX + intercept],
          name: "Ajuste",
          line: { color: "#b48a2c", width: 2 },
        });
      }

      const layout = {
        ...PLOTLY_LAYOUT_BASE,
        margin: { t: 12, r: 20, b: 50, l: 60 },
        xaxis: { ...PLOTLY_LAYOUT_BASE.xaxis, title: "Cuantil teorico (Normal)" },
        yaxis: { ...PLOTLY_LAYOUT_BASE.yaxis, title: "Cuantil muestral" },
        showlegend: false,
      };
      Plotly.newPlot(qqId, traces, layout, PLOTLY_CONFIG);
    });
  } catch (error) {
    target.innerHTML = `<div class="callout callout-danger">No fue posible cargar el diagnostico de ${esc(t)}: ${esc(error.message)}</div>`;
  }
}

function renderReturnDiagnosticsBySector(result, targetId = "returns-diagnostics", selectedSector = "__all__") {
  const target = document.getElementById(targetId);
  if (!target) return;
  const summary = result.summary || {};
  const pooled = result.pooled || {};
  const sectors = Array.isArray(result.sectors) ? result.sectors.slice() : [];
  const tickerDetailId = `${targetId}-ticker-detail`;
  const pooledFitLabel = _fitLabel(pooled?.fit);

  const sectorOptions = sectors
    .map(item => `<option value="${esc(item.sector)}" ${item.sector === selectedSector ? "selected" : ""}>${esc(item.sector)} (${item.summary?.n_assets ?? item.assets?.length ?? 0})</option>`)
    .join("");
  const selected = selectedSector === "__all__" ? sectors : sectors.filter(item => item.sector === selectedSector);

  target.innerHTML = `
    <div class="comparison-card">
      <div class="data-list" style="margin-bottom:14px">
        <div><span>Ventana calibracion</span><strong>${esc(result.calibration_window?.start || "N/A")} -> ${esc(result.calibration_window?.end || "N/A")}</strong></div>
        <div><span>Activos analizados</span><strong>${summary.n_assets ?? "N/A"}</strong></div>
        <div><span>JB (p>=0.05)</span><strong>${summary.jarque_bera_pass_rate_5pct != null ? Math.round(summary.jarque_bera_pass_rate_5pct * 100) + "%" : "N/A"}</strong></div>
        <div><span>Normaltest (p>=0.05)</span><strong>${summary.normaltest_pass_rate_5pct != null ? Math.round(summary.normaltest_pass_rate_5pct * 100) + "%" : "N/A"}</strong></div>
        <div><span>Pooled skew</span><strong>${pooled.skew ?? "N/A"}</strong></div>
        <div><span>Pooled kurtosis</span><strong>${pooled.kurtosis_excess ?? "N/A"}</strong></div>
        <div><span>Mejor ajuste pooled (BIC)</span><strong>${esc(pooledFitLabel)}</strong></div>
      </div>

      <div class="pf-card" style="margin-bottom:12px">
        <div class="pf-section-title">Como interpretar estos graficos</div>
        <div class="methodology-copy">
          <strong>Que se grafica:</strong> histograma de retornos diarios (%) "pooled" por sector (mezcla de activos + dias).
          <br><strong>Linea naranja:</strong> Normal ajustada con la misma media y desviacion estandar. Si hay colas pesadas, veras mas masa en extremos y kurtosis_excess > 0.
          <br><strong>Tests:</strong> p &lt; 0.05 rechaza normalidad. Es comun que se rechace aun cuando el histograma parezca campana (n grande => tests sensibles).
          <br><strong>Ajuste sugerido:</strong> ${esc(pooledFitLabel)}. ${esc(pooled?.fit?.notes || "")}
          <br>${esc(summary.notes || "")}
        </div>
      </div>

      <div class="action-row" style="margin:6px 0 10px">
        <label style="font-size:13px;color:var(--text-muted)">Sector</label>
        <select onchange="renderReturnDiagnosticsBySector(PF.lastReturnDiagnostics, '${esc(targetId)}', this.value)">
          <option value="__all__" ${selectedSector === "__all__" ? "selected" : ""}>Todos los sectores</option>
          ${sectorOptions}
        </select>
      </div>

      <div id="${targetId}-sectors">
        ${selected.map((sec, idx) => `
          <div class="pf-card" style="margin-top:12px">
            <div class="pf-section-title">Sector: ${esc(sec.sector)}</div>
            <div class="data-list" style="margin-bottom:12px">
              <div><span>Activos</span><strong>${esc(String(sec.summary?.n_assets ?? sec.assets?.length ?? "N/A"))}</strong></div>
              <div><span>Normalidad</span><strong>${esc(sec.summary?.jarque_bera_p == null ? "N/A" : ((sec.summary.jarque_bera_p >= 0.05 && (sec.summary.normaltest_p == null || sec.summary.normaltest_p >= 0.05)) ? "No rechazada (alpha 5%)" : "Rechazada (alpha 5%)"))}</strong></div>
              <div><span>Mejor ajuste (BIC)</span><strong>${esc(_fitLabel(sec.summary?.fit))}</strong></div>
              <div><span>Mean pooled</span><strong>${sec.summary?.mean_daily_pct != null ? sec.summary.mean_daily_pct.toFixed(4) + "%" : "N/A"}</strong></div>
              <div><span>Std pooled</span><strong>${sec.summary?.std_daily_pct != null ? sec.summary.std_daily_pct.toFixed(4) + "%" : "N/A"}</strong></div>
              <div><span>Skew</span><strong>${sec.summary?.skew ?? "N/A"}</strong></div>
              <div><span>Kurtosis</span><strong>${sec.summary?.kurtosis_excess ?? "N/A"}</strong></div>
            </div>
            <details style="margin:-6px 0 12px">
              <summary style="cursor:pointer;color:var(--text-muted);font-size:12px">Ver p-values sector</summary>
              <div class="data-list" style="margin-top:10px">
                <div><span>Jarque-Bera p</span><strong>${sec.summary?.jarque_bera_p != null ? sec.summary.jarque_bera_p.toFixed(6) : "N/A"}</strong></div>
                <div><span>D'Agostino p</span><strong>${sec.summary?.normaltest_p != null ? sec.summary.normaltest_p.toFixed(6) : "N/A"}</strong></div>
              </div>
            </details>
            <div class="chart-wrap">
              <div id="${targetId}-sector-hist-${idx}" style="height:260px"></div>
            </div>
            <div style="margin-top:10px">
              <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px">Estudiar una accion del sector</div>
              <div class="reference-chip-row">
                ${(Array.isArray(sec.assets) ? sec.assets.slice().sort((a, b) => (a.jarque_bera_p ?? 1) - (b.jarque_bera_p ?? 1)).slice(0, 16) : []).map(a => `
                  <button class="reference-chip" type="button" onclick="loadTickerReturnDiagnostics('${esc(a.ticker)}', '${esc(tickerDetailId)}')">${esc(a.ticker)}</button>
                `).join("")}
              </div>
              <div style="font-size:12px;color:var(--text-muted);margin-top:6px">Tip: se muestran hasta 16 tickers (peores JB p primero). Use el selector de sector para explorar el resto.</div>
            </div>
          </div>
        `).join("")}
      </div>

      <div id="${tickerDetailId}"></div>
      <div class="methodology-copy" style="margin-top:12px">${esc(summary.notes || "")}</div>
    </div>
  `;

  PF.lastReturnDiagnostics = result;

  requestAnimationFrame(() => {
    selected.forEach((sec, idx) => {
      renderHistogramChart(
        `${targetId}-sector-hist-${idx}`,
        sec.summary?.histogram,
        `Histograma pooled - ${sec.sector}`,
        { mean: sec.summary?.mean_daily_pct, std: sec.summary?.std_daily_pct, student_t: _extractStudentTParams(sec.summary?.fit) }
      );
    });
  });
}

function renderScenarioView() {
  const contentEl = document.getElementById("content");
  if (!PF.lastResult) {
    contentEl.innerHTML = `
      <div class="pf-section">
        <div class="hero-card">
          <div class="hero-eyebrow">Escenarios</div>
          <h2 class="hero-title">Proyecciones del portafolio</h2>
          <p class="hero-copy">Ejecuta primero una recomendacion para construir los escenarios favorable, neutro y desfavorable.</p>
          <div class="action-row">
            <button class="btn-primary" type="button" onclick="pfNavGo('recommendation')">Ir a recomendacion</button>
          </div>
        </div>
      </div>
    `;
    return;
  }

  const result = PF.lastResult;
  const sc = result.scenarios;
  contentEl.innerHTML = `
    <div class="pf-section">
      <div class="hero-card">
        <div class="hero-eyebrow">Escenarios p10 / p50 / p90</div>
        <h2 class="hero-title">Escenarios de retorno y capital</h2>
        <p class="hero-copy">Los escenarios reportan trayectorias netas de comision usando las metricas del portafolio recomendado.</p>
      </div>
      <div class="scenario-grid">
        <div class="scenario-card favorable">
          <div class="scenario-label">Favorable (p90)</div>
          <div class="scenario-ret">${sc.favorable.annual_return_pct > 0 ? "+" : ""}${sc.favorable.annual_return_pct}%</div>
          <div class="scenario-cap">Ano 1: <strong>${fmtUSD(sc.favorable.capital_by_year["1"])}</strong></div>
          <div class="scenario-cap">Ano 5: <strong>${fmtUSD(sc.favorable.capital_by_year["5"])}</strong></div>
          <div class="scenario-cap">Retorno total: ${sc.favorable.total_return_pct > 0 ? "+" : ""}${sc.favorable.total_return_pct}%</div>
        </div>
        <div class="scenario-card neutro">
          <div class="scenario-label">Neutro (p50)</div>
          <div class="scenario-ret">${sc.neutro.annual_return_pct > 0 ? "+" : ""}${sc.neutro.annual_return_pct}%</div>
          <div class="scenario-cap">Ano 1: <strong>${fmtUSD(sc.neutro.capital_by_year["1"])}</strong></div>
          <div class="scenario-cap">Ano 5: <strong>${fmtUSD(sc.neutro.capital_by_year["5"])}</strong></div>
          <div class="scenario-cap">Retorno total: ${sc.neutro.total_return_pct > 0 ? "+" : ""}${sc.neutro.total_return_pct}%</div>
        </div>
        <div class="scenario-card desfavorable">
          <div class="scenario-label">Desfavorable (p10)</div>
          <div class="scenario-ret">${sc.desfavorable.annual_return_pct > 0 ? "+" : ""}${sc.desfavorable.annual_return_pct}%</div>
          <div class="scenario-cap">Ano 1: <strong>${fmtUSD(sc.desfavorable.capital_by_year["1"])}</strong></div>
          <div class="scenario-cap">Ano 5: <strong>${fmtUSD(sc.desfavorable.capital_by_year["5"])}</strong></div>
          <div class="scenario-cap">Retorno total: ${sc.desfavorable.total_return_pct > 0 ? "+" : ""}${sc.desfavorable.total_return_pct}%</div>
        </div>
      </div>
      <div class="chart-wrap">
        <div class="pf-section-title" style="margin-bottom:8px;border:none;padding:0">Proyeccion mensual del capital</div>
        <div id="pf-scenario-chart" style="height:320px"></div>
      </div>
      <div class="detail-grid">
        <div class="pf-card">
          <div class="pf-section-title">Parametros reportados</div>
          <div class="data-list">
            <div><span>Retorno esperado</span><strong>${result.metrics.expected_return_pct}%</strong></div>
            <div><span>Volatilidad anual</span><strong>${result.metrics.volatility_pct}%</strong></div>
            <div><span>Comision</span><strong>${result.commission_rate_pct}% anual</strong></div>
            <div><span>CVaR</span><strong>${result.cvar_pct != null ? result.cvar_pct + "%" : "—"}</strong></div>
          </div>
        </div>
        <div class="pf-card">
          <div class="pf-section-title">Lectura academica</div>
          <div class="methodology-copy">Esta vista expone el componente de escenarios del modelo base. La simulacion del cliente queda disponible en el modulo siguiente.</div>
        </div>
      </div>
    </div>
  `;
  renderScenarioChart(result.scenario_timeseries);
}

function renderScenarioChart(ts) {
  if (!ts || !ts.months || typeof Plotly === "undefined") return;
  const x = ts.months.map(month => `Mes ${month}`);
  const traces = [
    { x, y: ts.favorable, name: "Favorable", mode: "lines", line: { color: "#1f6f52", width: 2 } },
    { x, y: ts.neutro, name: "Neutro", mode: "lines", line: { color: "#0f4c81", width: 2 } },
    { x, y: ts.desfavorable, name: "Desfavorable", mode: "lines", line: { color: "#b34a3c", width: 2, dash: "dot" } },
  ];
  const layout = {
    ...PLOTLY_LAYOUT_BASE,
    margin: { t: 12, r: 20, b: 48, l: 80 },
    yaxis: { ...PLOTLY_LAYOUT_BASE.yaxis, title: "Capital (USD)", tickformat: ",.0f" },
    legend: { orientation: "h", y: -0.2 },
  };
  Plotly.newPlot("pf-scenario-chart", traces, layout, PLOTLY_CONFIG);
}

function renderSimulation() {
  const capital = PF.lastInputs.capital || 100000;
  const expectedReturn = PF.lastResult ? PF.lastResult.metrics.expected_return_pct : 10;
  const volatility = PF.lastResult ? PF.lastResult.metrics.volatility_pct : 20;
  const maxLoss = PF.lastResult ? Math.round((PF.lastResult.alpha_p || 0.15) * 100) : 15;

  const contentEl = document.getElementById("content");
  contentEl.innerHTML = `
    <div class="pf-section">
      <div class="hero-card">
        <div class="hero-eyebrow">Simulacion del cliente</div>
        <h2 class="hero-title">Ciclo semanal de aceptacion, comisiones y retiro</h2>
        <p class="hero-copy">Aproximacion operacional del sistema: recomendacion semanal, aceptacion, cobro de comisiones y retiro por drawdown.</p>
      </div>
      <div class="pf-card">
        <div class="pf-section-title" style="border:none;padding:0;margin-bottom:12px">Parametros de simulacion</div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Capital inicial (USD)</label>
            <input id="sim-capital" class="form-input" type="number" value="${capital}">
          </div>
          <div class="form-group">
            <label class="form-label">Retorno esperado anual (%)</label>
            <input id="sim-exp-ret" class="form-input" type="number" step="0.1" value="${expectedReturn}">
          </div>
          <div class="form-group">
            <label class="form-label">Volatilidad anual (%)</label>
            <input id="sim-vol" class="form-input" type="number" step="0.1" value="${volatility}">
          </div>
        </div>
        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Horizonte (anos)</label>
            <input id="sim-years" class="form-input" type="number" min="3" max="5" value="3">
          </div>
          <div class="form-group">
            <label class="form-label">Numero de simulaciones</label>
            <input id="sim-n" class="form-input" type="number" min="100" max="2000" step="100" value="500">
          </div>
          <div class="form-group">
            <label class="form-label">Tolerancia de perdida (%)</label>
            <input id="sim-loss-pct" class="form-input" type="number" min="0" max="100" step="1" value="${maxLoss}">
          </div>
        </div>
        <div class="action-row">
          <button class="btn-primary" id="sim-btn" onclick="submitSimulation()">Ejecutar simulacion</button>
          <span id="sim-loading" class="subtle-status" style="display:none">Simulando trayectorias y rebalanceos...</span>
        </div>
      </div>
      <div id="sim-result"></div>
    </div>
  `;
}

async function submitSimulation() {
  const capital = parseFloat(document.getElementById("sim-capital")?.value) || 100000;
  const expRet = parseFloat(document.getElementById("sim-exp-ret")?.value) || 10;
  const vol = parseFloat(document.getElementById("sim-vol")?.value) || 20;
  const years = parseInt(document.getElementById("sim-years")?.value, 10) || 3;
  const nSim = parseInt(document.getElementById("sim-n")?.value, 10) || 500;
  const maxLoss = parseFloat(document.getElementById("sim-loss-pct")?.value) || 15;
  const btn = document.getElementById("sim-btn");
  const loading = document.getElementById("sim-loading");

  if (btn) btn.disabled = true;
  if (loading) loading.style.display = "inline";

  try {
    const result = await apiFetch("/api/portfolio/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        initial_capital: capital,
        expected_return: expRet / 100,
        volatility: vol / 100,
        max_loss_pct: maxLoss / 100,
        years,
        n_simulations: nSim,
      }),
    });
    PF.lastSimulation = result;
    renderSimulationResult(result, capital);
  } catch (e) {
    document.getElementById("sim-result").innerHTML = `<div class="pf-card callout callout-danger">Error al simular: ${esc(e.message)}</div>`;
  } finally {
    if (btn) btn.disabled = false;
    if (loading) loading.style.display = "none";
  }
}

function renderSimulationResult(result, initialCapital) {
  document.getElementById("sim-result").innerHTML = `
    <div class="summary-grid">
      <div class="summary-card">
        <div class="summary-label">Capital final promedio</div>
        <div class="summary-value">${fmtUSD(result.final_capital_mean)}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Capital p10</div>
        <div class="summary-value">${fmtUSD(result.final_capital_p10)}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Capital p90</div>
        <div class="summary-value">${fmtUSD(result.final_capital_p90)}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Tasa de retiro</div>
        <div class="summary-value">${result.withdrawal_rate}%</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Comisiones promedio</div>
        <div class="summary-value">${fmtUSD(result.total_commissions_mean)}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Recs. aceptadas</div>
        <div class="summary-value">${result.accepted_recommendations_mean}</div>
      </div>
    </div>
    <div class="chart-wrap">
      <div class="pf-section-title" style="margin-bottom:8px;border:none;padding:0">Trayectorias de capital</div>
      <div id="sim-chart" style="height:320px"></div>
    </div>
    <div class="detail-grid">
      <div class="pf-card">
        <div class="pf-section-title">Lectura operacional</div>
        <div class="data-list">
          <div><span>Recomendaciones emitidas</span><strong>${result.total_recommendations}</strong></div>
          <div><span>Modelo de aceptacion</span><strong>${esc(result.assumptions?.acceptance_model || "—")}</strong></div>
          <div><span>Modelo de retiro</span><strong>${esc(result.assumptions?.withdrawal_model || "—")}</strong></div>
          <div><span>Comision</span><strong>${result.assumptions?.commission_rate_pct || "—"}% anual</strong></div>
        </div>
      </div>
      <div class="pf-card">
        <div class="pf-section-title">Resumen</div>
        <div class="methodology-copy">Capital inicial de referencia: ${fmtUSD(initialCapital)}. La simulacion resume la dinamica semanal, no una implementacion exacta de las funciones logisticas P1 y P2.</div>
      </div>
    </div>
  `;
  renderSimulationChart(result, initialCapital);
}

function renderSimulationChart(result, initialCapital) {
  if (typeof Plotly === "undefined") return;
  const x = result.periods.map(period => `Semana ${period}`);
  const traces = [
    { x, y: result.capital_p90, name: "P90", mode: "lines", line: { color: "#1f6f52", width: 1 } },
    { x, y: result.capital_mean, name: "Media", mode: "lines", line: { color: "#0f4c81", width: 2 } },
    { x, y: result.capital_p10, name: "P10", mode: "lines", line: { color: "#b34a3c", width: 1, dash: "dot" } },
    { x, y: Array(x.length).fill(initialCapital), name: "Capital inicial", mode: "lines", line: { color: "#b48a2c", width: 1, dash: "dash" } },
  ];
  const layout = {
    ...PLOTLY_LAYOUT_BASE,
    margin: { t: 12, r: 20, b: 48, l: 80 },
    yaxis: { ...PLOTLY_LAYOUT_BASE.yaxis, title: "Capital (USD)", tickformat: ",.0f" },
    legend: { orientation: "h", y: -0.2 },
  };
  Plotly.newPlot("sim-chart", traces, layout, PLOTLY_CONFIG);
}

function renderMethodology() {
  const last = PF.lastResult;
  const dynamicSummary = last ? `
    <div class="pf-card">
      <div class="pf-section-title">Ultima corrida</div>
      <div class="data-list">
        <div><span>Perfil</span><strong>${esc(last.profile_label || "—")}</strong></div>
        <div><span>Constructor activo</span><strong>${esc(last.metrics?.method_label || "—")}</strong></div>
        <div><span>Holdings finales</span><strong>${last.universe?.target_holdings || "—"}</strong></div>
        <div><span>Universo operativo</span><strong>${last.methodology?.optimizer_universe_size || "—"}</strong></div>
      </div>
    </div>
  ` : "";

  document.getElementById("content").innerHTML = `
    <div class="pf-section">
      <div class="hero-card">
        <div class="hero-eyebrow">Metodologia visible</div>
        <h2 class="hero-title">Marco tecnico del sistema</h2>
        <p class="hero-copy">La interfaz diferencia el motor base ya implementado de las extensiones del informe que siguen pendientes.</p>
      </div>
      ${dynamicSummary}
      <details class="details-card" open>
        <summary>Universo F5 y filtros operativos</summary>
        <div class="details-body">Historia minima de 10 anos, precio >= 5 USD, market cap >= 2B USD, volatilidad anual entre 5% y 100%, excluyendo sector Unknown y Shell Companies.</div>
      </details>
      <details class="details-card" open>
        <summary>Motor activo de esta version</summary>
        <div class="details-body">Modelo base FinPUC: media-varianza / minima varianza / maximo retorno segun perfil, con CVaR historico, escenarios y simulacion simplificada del cliente.</div>
      </details>
      <details class="details-card">
        <summary>Perfiles, alpha_p y restriccion CVaR</summary>
        <div class="details-body">
          <table class="comparison-table">
            <thead>
              <tr>
                <th>Perfil</th>
                <th>alpha_p</th>
                <th>Constructor</th>
                <th>CVaR beta</th>
              </tr>
            </thead>
            <tbody>
              ${Object.values(PF_PROFILES).map(profile => `
                <tr>
                  <td>${profile.label}</td>
                  <td>${profile.alpha}</td>
                  <td>${profile.method}</td>
                  <td>${profile.cvar}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </details>
      <details class="details-card">
        <summary>Ciclo semanal y comportamiento del cliente</summary>
        <div class="details-body">El sistema emite una recomendacion semanal, cobra comision sobre el capital gestionado y aproxima P1 y P2 en la simulacion del cliente. Los dividendos existen en los datos pero la caja chica no se separa aun dentro del optimizador.</div>
      </details>
      <details class="details-card">
        <summary>Black-Litterman como fase futura</summary>
        <div class="details-body">Avance inicial implementado: el sistema incluye una estimacion mu_BL con parametros τ, Ω (diagonal) y views en JSON. Falta profundizar en calibracion/validacion de Ω y en la integracion completa descrita en el informe.</div>
      </details>
      <div class="pf-card">
        <div class="pf-section-title">Comparacion secundaria</div>
        <div class="action-row">
          <button class="btn-secondary" type="button" onclick="fetchBenchmarkComparisonFromMethodology()">Ejecutar caso base + benchmark</button>
        </div>
        <div id="methodology-benchmark"></div>
      </div>
    </div>
  `;
}

async function fetchBenchmarkComparisonFromMethodology() {
  if (!PF.lastResult) {
    document.getElementById("methodology-benchmark").innerHTML = `<div class="callout">Ejecuta primero una recomendacion para comparar contra el benchmark.</div>`;
    return;
  }
  await fetchBenchmarkComparison("methodology-benchmark");
}



// ============================================================
// Override academico FinPUC
// ============================================================

const PF_NAV_ITEMS = [
  { id: "introduction", label: "Introduccion" },
  { id: "system", label: "Sistema y perfiles" },
  { id: "methodologies", label: "Metodologias" },
  { id: "parameters", label: "Parametros" },
  { id: "results", label: "Resultados" },
  { id: "scenarios", label: "Escenarios" },
  { id: "simulate", label: "Simulacion cliente" },
  { id: "references", label: "Datos y referencias" },
];

Object.assign(PF, {
  activeNav: "introduction",
  currentModule: PF.currentModule || "acciones",
  selectedMethodologyId: PF.selectedMethodologyId || "finpuc_hibrido",
  catalog: null,
  reportOutline: null,
  formState: PF.formState || {},
  bootstrapError: null,
});

let mathTypesetToken = null;
let mathTypesetRetry = 0;

function getPortfolioNavLabel(section) {
  return PF_NAV_ITEMS.find(item => item.id === section)?.label || "Sistema FinPUC";
}

function queueMathTypeset() {
  if (!window.MathJax || typeof window.MathJax.typesetPromise !== "function") {
    // MathJax carga asíncrono; reintenta un número acotado de veces para evitar quedar con LaTeX sin renderizar.
    if (mathTypesetRetry < 40) {
      mathTypesetRetry += 1;
      if (mathTypesetToken) clearTimeout(mathTypesetToken);
      mathTypesetToken = setTimeout(queueMathTypeset, 150);
    }
    return;
  }
  if (mathTypesetToken) clearTimeout(mathTypesetToken);
  mathTypesetToken = setTimeout(() => {
    const container = document.getElementById("content");
    const targets = container ? [container] : undefined;
    window.MathJax.typesetPromise(targets)
      .catch(() => null)
      .finally(() => {
        mathTypesetToken = null;
        mathTypesetRetry = 0;
      });
  }, 0);
}

function renderFormulaBlock(latex, fallback) {
  if (latex) {
    return `
      <div class="formula-box">
        <div class="latex-block">\\[${latex}\\]</div>
        ${fallback ? `<div class="formula-caption">${esc(fallback)}</div>` : ""}
      </div>
    `;
  }
  return `<div class="formula-box">${esc(fallback || "—")}</div>`;
}

function renderFormulaLegend(legend) {
  if (!legend || legend.length === 0) return "";
  const rows = legend.map(item => `
    <div class="formula-legend-row">
      <div class="formula-legend-sym">${esc(item.symbol)}</div>
      <div class="formula-legend-body">
        <div class="formula-legend-name">${esc(item.name)}</div>
        <div class="formula-legend-desc">${esc(item.description)}</div>
        <div class="formula-legend-source">📂 ${esc(item.source)}</div>
      </div>
    </div>
  `).join("");
  return `
    <div class="formula-legend">
      <div class="formula-legend-title">Glosario de simbolos</div>
      ${rows}
    </div>
  `;
}

function renderReportVisuals() {
  const visuals = PF.reportOutline?.visual_assets || [];
  if (!visuals.length) {
    return `<div class="results-empty">No hay vistas previas del informe disponibles en este entorno.</div>`;
  }

  return `
    <div class="report-visual-grid">
      ${visuals.map(asset => `
        <div class="report-preview-card">
          <div class="report-preview-head">
            <span class="report-preview-kind">${esc(asset.kind || "Vista")}</span>
            <span class="report-preview-page">Pagina ${esc(String(asset.page_number || "—"))}</span>
          </div>
          <h4>${esc(asset.label)}</h4>
          <p>${esc(asset.summary || "")}</p>
          <div class="report-preview-image-wrap">
            <img class="report-preview-image" loading="lazy" src="${asset.image_url}" alt="${esc(asset.label)}">
          </div>
          <p>${esc(asset.caption || "")}</p>
          <div class="report-preview-actions">
            <a class="inline-link" href="${asset.image_url}" target="_blank" rel="noopener noreferrer">Abrir vista previa</a>
            <a class="inline-link" href="/api/report/file/pdf" target="_blank" rel="noopener noreferrer">Abrir informe PDF</a>
          </div>
        </div>
      `).join("")}
    </div>
  `;
}

function getCatalogMethod(methodologyId = PF.selectedMethodologyId) {
  return PF.catalog?.methodologies?.find(methodology => methodology.id === methodologyId) || null;
}

function getCatalogProfile(profileId = PF.formState.profile || "neutro") {
  return PF.catalog?.profiles?.find(profile => profile.id === profileId) || null;
}

function getDefaultMethodologyId() {
  return PF.catalog?.default_methodology_id || "finpuc_hibrido";
}

function basePortfolioDefaults() {
  const neutralProfile = getCatalogProfile("neutro");
  return {
    initial_capital: PF.formState.initial_capital || 100000,
    profile: PF.formState.profile || "neutro",
    candidate_pool_size:
      PF.formState.candidate_pool_size !== undefined
        ? PF.formState.candidate_pool_size
        : (neutralProfile?.candidate_pool_default ?? ""),
    target_holdings: PF.formState.target_holdings || 10,
    sector: PF.formState.sector || "",
  };
}

function seedMethodologyState(methodologyId) {
  const methodology = getCatalogMethod(methodologyId);
  if (!methodology) return;
  for (const def of methodology.parameters || []) {
    if (PF.formState[def.key] === undefined) {
      PF.formState[def.key] = def.default ?? "";
    }
  }
}

function seedPortfolioState() {
  Object.assign(PF.formState, basePortfolioDefaults());
  if (!getCatalogMethod(PF.selectedMethodologyId)) {
    PF.selectedMethodologyId = getDefaultMethodologyId();
  }
  seedMethodologyState(PF.selectedMethodologyId);
}

async function ensurePortfolioBootstrap() {
  if (PF.catalog && PF.reportOutline) return;

  try {
    const [catalog, reportOutline] = await Promise.all([
      apiFetch("/api/portfolio/catalog"),
      apiFetch("/api/report/outline"),
    ]);
    PF.catalog = catalog;
    PF.reportOutline = reportOutline;
    PF.selectedMethodologyId = PF.selectedMethodologyId || getDefaultMethodologyId();
    seedPortfolioState();
    PF.bootstrapError = null;
  } catch (error) {
    PF.bootstrapError = error.message;
    throw error;
  }
}

function setPortfolioNavActive(section) {
  for (const item of PF_NAV_ITEMS) {
    document.getElementById("pnav-" + item.id)?.classList.remove("active");
  }
  document.getElementById("pnav-" + section)?.classList.add("active");
}

function setNavState(view) {
  const btnHome = document.getElementById("btn-home");
  const btnSector = document.getElementById("btn-sector");
  const sep = document.getElementById("topbar-sep");
  const current = document.getElementById("breadcrumb-current");

  if (PF.currentModule === "portafolios") {
    btnHome.style.display = "none";
    btnSector.style.display = "none";
    sep.style.display = "none";
    current.textContent = `Sistema FinPUC / ${getPortfolioNavLabel(PF.activeNav)}`;
    return;
  }

  if (view === "home") {
    btnHome.style.display = "none";
    btnSector.style.display = "none";
    sep.style.display = "none";
    current.textContent = "Selecciona un sector del universo F5";
  } else if (view === "sector") {
    btnHome.style.display = "flex";
    btnSector.style.display = "none";
    sep.style.display = "none";
    current.textContent = State.currentSector || "";
  } else if (view === "stock") {
    btnHome.style.display = "flex";
    btnSector.style.display = "flex";
    sep.style.display = "inline";
    document.getElementById("btn-sector-label").textContent = State.currentSector || "Sector";
    current.textContent = State.currentTicker || "";
  }
}

function goHome() {
  if (PF.currentModule === "portafolios") {
    pfNavGo("introduction");
    return;
  }
  State.currentSector = null;
  State.currentTicker = null;
  State.sortKey = null;
  State.sortAsc = true;
  State.filterText = "";
  State.currentPage = 1;
  setActiveSector(null);
  setNavState("home");
  showContent(`
    <div class="welcome">
      <div class="welcome-panel">
        <div class="welcome-kicker">Universo F5</div>
        <h3>Exploracion del universo operativo</h3>
        <p>Selecciona un sector para revisar las acciones disponibles y los insumos que alimentan el sistema recomendador FinPUC.</p>
      </div>
    </div>
  `);
  window.location.hash = "#/";
}

async function switchModule(mod) {
  PF.currentModule = mod;
  const tabUniverse = document.getElementById("tab-acciones");
  const tabFinpuc = document.getElementById("tab-portafolios");
  const sectorLabel = document.getElementById("sector-label");
  const sectorList = document.getElementById("sector-list");
  const portNav = document.getElementById("portfolio-nav");

  if (mod === "portafolios") {
    tabUniverse.classList.remove("active");
    tabFinpuc.classList.add("active");
    sectorLabel.style.display = "none";
    sectorList.style.display = "none";
    portNav.style.display = "block";
    document.getElementById("content").innerHTML = `<div class="results-empty">Cargando estructura academica del sistema FinPUC...</div>`;
    try {
      await ensurePortfolioBootstrap();
      if (!PF.activeNav || !PF_NAV_ITEMS.find(item => item.id === PF.activeNav)) {
        PF.activeNav = "introduction";
      }
      await pfNavGo(PF.activeNav);
    } catch (error) {
      document.getElementById("content").innerHTML = `<div class="callout callout-danger">No fue posible cargar el catalogo academico: ${esc(error.message)}</div>`;
    }
    return;
  }

  tabUniverse.classList.add("active");
  tabFinpuc.classList.remove("active");
  sectorLabel.style.display = "";
  sectorList.style.display = "block";
  portNav.style.display = "none";
  setNavState("home");
  goHome();
}

function updateFormValue(key, value) {
  PF.formState[key] = value;
}

function setMethodology(methodologyId, navigateToParameters = false) {
  PF.selectedMethodologyId = methodologyId;
  seedMethodologyState(methodologyId);
  if (navigateToParameters) {
    pfNavGo("parameters");
  } else {
    renderMethodologies();
  }
}

function updateProfileSelection(profileId) {
  PF.formState.profile = profileId;
  const profile = getCatalogProfile(profileId);
  if (profile && (PF.formState.candidate_pool_size === "" || PF.formState.candidate_pool_size === undefined || PF.formState.candidate_pool_size === null)) {
    PF.formState.candidate_pool_size = profile.candidate_pool_default ?? "";
  }
  renderParametersView();
}

function renderReferenceLinks() {
  return (PF.reportOutline?.assets || []).map(asset => `
    <a class="reference-link" href="${asset.url}" target="_blank" rel="noopener noreferrer">
      ${esc(asset.label)}
      <small>Acceso directo desde la app al documento base del informe.</small>
    </a>
  `).join("");
}

function renderIntroduction() {
  const sections = PF.reportOutline?.sections || [];
  const tables = PF.reportOutline?.tables || [];
  const formulas = PF.reportOutline?.formulae || [];
  const selectedMethod = getCatalogMethod();

  document.getElementById("content").innerHTML = `
    <div class="pf-section">
      <div class="hero-card">
        <div class="hero-eyebrow">Portada academica</div>
        <h2 class="hero-title">Sistema recomendador FinPUC</h2>
        <p class="hero-copy">FinPUC genera recomendaciones semanales de portafolio para cinco perfiles de riesgo, utilizando un universo F5 filtrado, metodologias de optimizacion y una capa de analisis de escenarios y simulacion del cliente. Esta portada resume el funcionamiento del sistema y lo conecta explicitamente con las secciones y tablas del informe.</p>
        <div class="link-row">
          ${renderReferenceLinks()}
        </div>
      </div>

      <div class="academic-grid">
        <div class="academic-card">
          <h4>Proposito del sistema</h4>
          <p>${esc(PF.reportOutline?.summary || "")}</p>
        </div>
        <div class="academic-card">
          <h4>Metodologia recomendada</h4>
          <p>${esc(selectedMethod?.label || "Metodologia hibrida FinPUC")} como flujo principal del sistema, manteniendo visibles las demas tecnicas del informe para comparacion y estudio.</p>
        </div>
        <div class="academic-card">
          <h4>Base documental</h4>
          <p>La navegacion replica la estructura formal del informe: descripcion del sistema, perfiles, formulacion, metodologias, datos, resultados y referencias.</p>
        </div>
      </div>

      <div class="pf-card">
        <div class="pf-section-title">Funcionamiento general del sistema</div>
        <div class="timeline">
          <div class="timeline-step">
            <strong>1. Perfil del cliente y alpha_p</strong>
            <p>El sistema clasifica al cliente en uno de cinco perfiles y fija su tolerancia maxima de perdida. Basado en Seccion 2.2.2 y Tabla 2.1.</p>
          </div>
          <div class="timeline-step">
            <strong>2. Universo operativo F5</strong>
            <p>Se selecciona un sub-universo compatible con el perfil y los filtros F0-F5. Basado en Seccion 2.5, Tabla 2.4 y Tabla 0.10.</p>
          </div>
          <div class="timeline-step">
            <strong>3. Estimacion y optimizacion</strong>
            <p>El usuario elige una metodologia del informe, define parametros y ejecuta la asignacion del portafolio. Basado en Seccion 3, Seccion 4 y Ecuaciones 4.4 a 4.7.</p>
          </div>
          <div class="timeline-step">
            <strong>4. Escenarios y simulacion del cliente</strong>
            <p>El sistema reporta escenarios p10/p50/p90 y modela la aceptacion o abandono del cliente bajo el ciclo semanal. Basado en Seccion 2.2.1 y Ecuaciones 4.5 y 4.6.</p>
          </div>
        </div>
      </div>

      <div class="academic-grid">
        <div class="academic-card">
          <h4>Secciones clave del informe</h4>
          <div class="reference-chip-row">
            ${sections.map(section => `<span class="reference-chip">${esc(section.label)}</span>`).join("")}
          </div>
        </div>
        <div class="academic-card">
          <h4>Tablas clave</h4>
          <div class="reference-chip-row">
            ${tables.map(table => `<span class="reference-chip">${esc(table.label)}</span>`).join("")}
          </div>
        </div>
        <div class="academic-card">
          <h4>Formulas visibles</h4>
          <div class="reference-chip-row">
            ${formulas.map(formula => `<span class="reference-chip">${esc(formula.label)}</span>`).join("")}
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderSystemProfiles() {
  const profiles = PF.catalog?.profiles || [];
  const lastCycle = PF.lastResult?.weekly_cycle;

  document.getElementById("content").innerHTML = `
    <div class="pf-section">
      <div class="hero-card">
        <div class="hero-eyebrow">Sistema y perfiles</div>
        <h2 class="hero-title">Ciclo operacional y tolerancia de perdida</h2>
        <p class="hero-copy">Esta vista resume el funcionamiento semanal del sistema y la relacion entre cada perfil de riesgo, alpha_p y el sub-universo sugerido por el informe.</p>
      </div>

      <div class="pf-card">
        <div class="pf-section-title">Ciclo operacional semanal</div>
        <div class="timeline">
          <div class="timeline-step">
            <strong>Recomendacion semanal</strong>
            <p>El optimizador genera un portafolio recomendado cada semana para el perfil seleccionado. Referencia: Seccion 2.2.1.</p>
          </div>
          <div class="timeline-step">
            <strong>Aceptacion o rechazo</strong>
            <p>El cliente puede aceptar la recomendacion con una probabilidad operacional asociada a P2(x2). Referencia: Ecuacion 4.6.</p>
          </div>
          <div class="timeline-step">
            <strong>Comision y evolucion del capital</strong>
            <p>Si hay rebalanceo, el sistema cobra una comision k y luego el capital evoluciona con precios y dividendos. Referencia: Seccion 2.2.1 y Tabla 0.9.</p>
          </div>
          <div class="timeline-step">
            <strong>Abandono por perdida excedida</strong>
            <p>Si el drawdown supera la tolerancia del perfil, el cliente puede salir de la plataforma via P1(x1). Referencia: Ecuacion 4.5.</p>
          </div>
        </div>
      </div>

      <div class="pf-card">
        <div class="pf-section-title">Perfiles de riesgo FinPUC</div>
        <table class="profile-table">
          <thead>
            <tr>
              <th>Perfil</th>
              <th>alpha_p</th>
              <th>Descripcion</th>
              <th>Sub-universo sugerido</th>
            </tr>
          </thead>
          <tbody>
            ${profiles.map(profile => `
              <tr>
                <td><strong>${esc(profile.label)}</strong></td>
                <td>${profile.alpha_pct}%</td>
                <td>${esc(profile.description || "—")}</td>
                <td>${esc(profile.candidate_pool_range || "—")}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>

      ${lastCycle ? `
        <div class="pf-card">
          <div class="pf-section-title">Lectura operacional de la ultima corrida</div>
          <div class="data-list">
            <div><span>Cadencia</span><strong>${esc(lastCycle.cadence || "Semanal")}</strong></div>
            <div><span>Aceptacion</span><strong>${esc(lastCycle.client_acceptance || "—")}</strong></div>
            <div><span>Retiro</span><strong>${esc(lastCycle.client_withdrawal || "—")}</strong></div>
            <div><span>Comisiones</span><strong>${esc(lastCycle.commissions || "—")}</strong></div>
          </div>
        </div>
      ` : ""}
    </div>
  `;
}

function renderMethodologies() {
  const methods = PF.catalog?.methodologies || [];

  document.getElementById("content").innerHTML = `
    <div class="pf-section">
      <div class="hero-card">
        <div class="hero-eyebrow">Metodologias del informe</div>
        <h2 class="hero-title">Catalogo metodologico seleccionable</h2>
        <p class="hero-copy">Cada metodologia expone su formulacion resumida, su rol dentro del informe y los parametros que el usuario debe entregar antes de ejecutar el portafolio.</p>
      </div>

      <div class="method-grid">
        ${methods.map(method => {
          const isWip = !!method.wip;
          const cardClass = [
            method.id === PF.selectedMethodologyId ? "selected" : "",
            isWip ? "wip" : "",
          ].filter(Boolean).join(" ");
          const badgeClass = method.recommended ? "recommended" : isWip ? "wip" : "";
          const badgeText = method.recommended ? "Recomendada" : isWip ? "En desarrollo" : "Activa";
          const chipClass = isWip ? "note-chip wip" : "note-chip";
          return `
          <div class="method-card ${cardClass}" onclick="setMethodology('${esc(method.id)}')">
            <div class="method-head">
              <div>
                <div class="method-family">${esc(method.family)}</div>
                <div class="method-title">${esc(method.label)}</div>
              </div>
              <span class="method-badge ${badgeClass}">${badgeText}</span>
            </div>
            <p>${esc(method.description)}</p>
            ${renderFormulaBlock(method.formula_latex, method.formula_summary)}
            ${renderFormulaLegend(method.formula_legend)}
            <div class="reference-chip-row">
              ${(method.report_references || []).map(ref => `<span class="reference-chip">${esc(ref)}</span>`).join("")}
            </div>
            <div class="note-chip-row">
              <span class="${chipClass}">${esc(method.implementation_status || "Operativa")}</span>
              ${isWip ? `<span class="note-chip wip">Trabajo en paralelo</span>` : ""}
            </div>
            <div class="action-row" style="margin-top:14px">
              <button class="btn-secondary" type="button" onclick="event.stopPropagation(); setMethodology('${esc(method.id)}', true)">${isWip ? "Ver avance" : "Configurar parametros"}</button>
            </div>
          </div>`;
        }).join("")}
      </div>
    </div>
  `;
  queueMathTypeset();
}

function parameterRoleText(key, methodologyId) {
  const k = String(key || "");
  switch (k) {
    case "initial_capital":
      return "Escala escenarios y simulaciones (no cambia los pesos óptimos).";
    case "profile":
      return "Determina α_p (tolerancia de pérdida) y el sub-universo sugerido por perfil.";
    case "candidate_pool_size":
      return "Controla el tamaño del sub-universo operativo para reducir dimensionalidad y tiempo de cómputo.";
    case "target_holdings":
      return "Fija la cardinalidad final del portafolio; el sistema recorta y renormaliza los pesos.";
    case "sector":
      return "Restringe el universo F5 a un sector para análisis o escenarios específicos.";
    case "risk_free_rate_pct":
      return "Se usa como r_f en CAPM y en el exceso de retorno del ratio de Sharpe en Markowitz.";
    case "market_return_pct":
      return "Se usa como E[r_m] para construir la prima de riesgo (E[r_m] − r_f) en CAPM/Fama-French.";
    case "smb_premium_pct":
      return "Prima SMB en el modelo de factores: captura el efecto tamaño (small minus big) en el retorno esperado.";
    case "hml_premium_pct":
      return "Prima HML en el modelo de factores: captura el efecto valor (high minus low) en el retorno esperado.";
    case "cvar_beta_pct":
      return "Define β (nivel de confianza) para medir CVaR y reportar cumplimiento frente a α_p.";
    case "lambda_risk_aversion":
      return "Parámetro λ de Black-Litterman: aversión al riesgo usada para derivar la prior de equilibrio π del mercado.";
    case "tau":
      return "Parámetro τ de Black-Litterman: controla cuánto pesa la prior del mercado vs. las views del analista.";
    case "omega_diag":
      return "Parámetro Ω (diagonal) de Black-Litterman: controla la confianza en las views; Ω mayor ⇒ views pesan menos.";
    case "views_json":
      return "Define las views Q por ticker para ajustar μ_BL (input clave del avance Black-Litterman).";
    case "prob_desfavorable_pct":
    case "prob_neutro_pct":
    case "prob_favorable_pct":
      return "Define las probabilidades π_s de escenarios para ponderar el retorno esperado en el modelo estocástico.";
    case "commission_rate_pct":
      return "Comisión anual k: descuenta el retorno neto en escenarios/simulación y modela costo operacional.";
    case "p1_withdrawal_drawdown_pct":
      return "Umbral de drawdown usado para aproximar P1 (retiro) en el ciclo operacional.";
    case "p2_acceptance_prob_pct":
      return "Probabilidad base usada para aproximar P2 (aceptación) de recomendaciones/rebalanceos.";
    case "cash_buffer_pct":
      return "Reserva operacional referencial asociada a dividendos/caja chica.";
    default:
      if (methodologyId === "finpuc_hibrido") {
        return "Parámetro de entrada que ajusta calibración, riesgo o dinámica cliente dentro del flujo híbrido.";
      }
      return "Parámetro de entrada usado para calibrar/validar la metodología.";
  }
}

function renderBaseFieldCards(method) {
  const profiles = PF.catalog?.profiles || [];
  const selectedProfile = PF.formState.profile || "neutro";
  const methodId = method?.id || PF.selectedMethodologyId || "";

  return `
    <div class="field-grid">
      <div class="field-card">
        <label>Capital inicial</label>
        <input type="number" min="1000" step="1000" value="${esc(String(PF.formState.initial_capital ?? 100000))}" oninput="updateFormValue('initial_capital', this.value)">
        <div class="field-help">Monto base sobre el cual se construye la recomendacion y se proyectan los escenarios.</div>
        <div class="field-help">Funcion en el metodo: ${parameterRoleText("initial_capital", methodId)}</div>
        <span class="field-ref">Basado en Seccion 2.3.1</span>
      </div>
      <div class="field-card">
        <label>Perfil de riesgo</label>
        <select onchange="updateProfileSelection(this.value)">
          ${profiles.map(profile => `<option value="${esc(profile.id)}" ${profile.id === selectedProfile ? "selected" : ""}>${esc(profile.label)} (${profile.alpha_pct}%)</option>`).join("")}
        </select>
        <div class="field-help">Define alpha_p, la tolerancia maxima de perdida del cliente.</div>
        <div class="field-help">Funcion en el metodo: ${parameterRoleText("profile", methodId)}</div>
        <span class="field-ref">Tabla 2.1 / Seccion 2.2.2</span>
      </div>
      <div class="field-card">
        <label>Tamano del sub-universo</label>
        <input type="number" min="10" max="636" step="1" value="${esc(String(PF.formState.candidate_pool_size ?? ""))}" oninput="updateFormValue('candidate_pool_size', this.value)">
        <div class="field-help">Cantidad de activos candidatos que pasan al universo operativo previo a la optimizacion.</div>
        <div class="field-help">Funcion en el metodo: ${parameterRoleText("candidate_pool_size", methodId)}</div>
        <span class="field-ref">Tabla 0.10 / Tabla 2.4</span>
      </div>
      <div class="field-card">
        <label>Holdings finales</label>
        <input type="number" min="3" max="30" step="1" value="${esc(String(PF.formState.target_holdings ?? 10))}" oninput="updateFormValue('target_holdings', this.value)">
        <div class="field-help">Numero de posiciones visibles en el portafolio final.</div>
        <div class="field-help">Funcion en el metodo: ${parameterRoleText("target_holdings", methodId)}</div>
        <span class="field-ref">Seccion 2.3.1</span>
      </div>
      <div class="field-card">
        <label>Filtro sectorial opcional</label>
        <input type="text" value="${esc(PF.formState.sector || "")}" placeholder="Technology, Utilities..." oninput="updateFormValue('sector', this.value)">
        <div class="field-help">Restringe el universo a un sector del F5 cuando el analisis lo requiere.</div>
        <div class="field-help">Funcion en el metodo: ${parameterRoleText("sector", methodId)}</div>
        <span class="field-ref">Anexo 1 / Tabla 0.3</span>
      </div>
    </div>
  `;
}

function renderMethodField(definition, method) {
  const value = PF.formState[definition.key] ?? definition.default ?? "";
  const isTextArea = definition.input_type === "textarea";
  const inputHtml = isTextArea
    ? `<textarea oninput="updateFormValue('${esc(definition.key)}', this.value)">${esc(String(value))}</textarea>`
    : definition.input_type === "text"
      ? `<input type="text" value="${esc(String(value))}" placeholder="${esc(definition.placeholder || "")}" oninput="updateFormValue('${esc(definition.key)}', this.value)">`
      : `<input type="number"
                 ${definition.min != null ? `min="${definition.min}"` : ""}
                 ${definition.max != null ? `max="${definition.max}"` : ""}
                 ${definition.step != null ? `step="${definition.step}"` : ""}
                 value="${esc(String(value))}"
                 oninput="updateFormValue('${esc(definition.key)}', this.value)">`;

  return `
    <div class="field-card">
      <label>${esc(definition.label)}${definition.required ? " *" : ""}</label>
      ${inputHtml}
      <div class="field-help">${esc(definition.meaning)}${definition.unit ? ` Unidad: ${esc(definition.unit)}.` : ""}</div>
      <div class="field-help">Funcion en el metodo: ${parameterRoleText(definition.key, method?.id || "")}</div>
      <span class="field-ref">Basado en ${esc(definition.report_reference)}</span>
    </div>
  `;
}

function renderParametersView() {
  const method = getCatalogMethod();
  if (!method) {
    document.getElementById("content").innerHTML = `<div class="callout callout-danger">No hay una metodologia seleccionada.</div>`;
    return;
  }

  seedMethodologyState(method.id);
  const groups = ["Estimacion", "Riesgo y escenarios", "Cliente y negocio"];

  document.getElementById("content").innerHTML = `
    <div class="pf-section">
      <div class="hero-card">
        <div class="hero-eyebrow">Parametros</div>
        <h2 class="hero-title">${esc(method.label)}</h2>
        <p class="hero-copy">${esc(method.description)}</p>
        ${renderFormulaBlock(method.formula_latex, method.formula_summary)}
        <div class="reference-chip-row">
          ${(method.report_references || []).map(ref => `<span class="reference-chip">${esc(ref)}</span>`).join("")}
        </div>
      </div>

      <div class="parameter-group">
        <h3>Perfil y universo</h3>
        <p>Estos parametros fijan el capital inicial, el perfil de riesgo, el tamano del universo operativo y la cardinalidad final del portafolio.</p>
        ${renderBaseFieldCards(method)}
      </div>

      ${groups.map(group => {
        const defs = (method.parameters || []).filter(def => def.group === group);
        if (!defs.length) return "";
        return `
          <div class="parameter-group">
            <h3>${esc(group)}</h3>
            <p>Cada campo indica su significado financiero, la unidad de medida y la referencia documental dentro del informe.</p>
            <div class="field-grid">
              ${defs.map(def => renderMethodField(def, method)).join("")}
            </div>
          </div>
        `;
      }).join("")}

      <div class="pf-card">
        <div class="pf-section-title">Ejecucion de la metodologia</div>
        <div class="action-row">
          <button class="btn-primary" type="button" id="run-method-btn" onclick="submitMethodologyRun()">Ejecutar metodologia</button>
          <button class="btn-secondary" type="button" onclick="pfNavGo('methodologies')">Volver al catalogo</button>
          <span id="method-run-status" class="subtle-status"></span>
        </div>
      </div>
    </div>
  `;
  queueMathTypeset();
}

function buildOptimizationPayload() {
  const method = getCatalogMethod();
  const parameterValues = {};
  for (const definition of method.parameters || []) {
    parameterValues[definition.key] = PF.formState[definition.key];
  }
  return {
    initial_capital: parseFloat(PF.formState.initial_capital || 100000),
    methodology_id: method.id,
    profile: PF.formState.profile || "neutro",
    candidate_pool_size: PF.formState.candidate_pool_size === "" ? null : parseInt(PF.formState.candidate_pool_size, 10),
    target_holdings: parseInt(PF.formState.target_holdings || 10, 10),
    sector: PF.formState.sector || null,
    parameter_values: parameterValues,
  };
}

async function submitMethodologyRun() {
  const payload = buildOptimizationPayload();
  const runBtn = document.getElementById("run-method-btn");
  const statusEl = document.getElementById("method-run-status");
  if (runBtn) runBtn.disabled = true;
  if (statusEl) statusEl.textContent = "Ejecutando metodologia y construyendo portafolio...";

  try {
    const result = await apiFetch("/api/portfolio/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    PF.lastResult = result;
    PF.lastInputs = payload;
    PF.lastBenchmark = null;
    if (statusEl) statusEl.textContent = "Portafolio generado correctamente.";
    await pfNavGo("results");
  } catch (error) {
    if (statusEl) statusEl.textContent = "";
    const errorBox = `<div class="callout callout-danger">No fue posible ejecutar la metodologia: ${esc(error.message)}</div>`;
    const contentEl = document.getElementById("content");
    const runStatus = document.getElementById("method-run-status");
    if (runStatus) runStatus.insertAdjacentHTML("afterend", errorBox);
    else if (contentEl) contentEl.insertAdjacentHTML("afterbegin", errorBox);
  } finally {
    if (runBtn) runBtn.disabled = false;
  }
}

function renderParameterSummary(groups) {
  return groups.map(group => `
    <div class="parameter-group">
      <h3>${esc(group.group)}</h3>
      <table class="result-table">
        <thead>
          <tr>
            <th>Parametro</th>
            <th>Valor</th>
            <th>Significado</th>
            <th>Referencia</th>
          </tr>
        </thead>
        <tbody>
          ${group.items.map(item => `
            <tr>
              <td><strong>${esc(item.label)}</strong></td>
              <td>${esc(item.value_display || "—")}</td>
              <td>${esc(item.meaning || "—")}</td>
              <td>${esc(item.report_reference || "—")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `).join("");
}

function renderResultsView() {
  if (!PF.lastResult) {
    document.getElementById("content").innerHTML = `
      <div class="pf-section">
        <div class="results-empty">
          Todavia no existe una corrida metodologica. Selecciona una metodologia del informe, configura sus parametros y ejecuta el portafolio para ver resultados.
          <div class="action-row" style="margin-top:14px">
            <button class="btn-primary" type="button" onclick="pfNavGo('methodologies')">Ir a metodologias</button>
            <button class="btn-secondary" type="button" onclick="pfNavGo('parameters')">Ir a parametros</button>
          </div>
        </div>
      </div>
    `;
    return;
  }

  const result = PF.lastResult;
  const methodology = result.methodology || {};
  const metrics = result.metrics || {};
  const universe = result.universe || {};
  const weeklyCycle = result.weekly_cycle || {};

  document.getElementById("content").innerHTML = `
    <div class="pf-section">
      <div class="hero-card">
        <div class="hero-eyebrow">Resultados</div>
        <h2 class="hero-title">${esc(methodology.label || result.methodology_id || "Metodo ejecutado")}</h2>
        <p class="hero-copy">${esc(methodology.description || "Resultado de la metodologia seleccionada.")}</p>
        ${renderFormulaBlock(methodology.formula_latex, methodology.formula_summary)}
        <div class="reference-chip-row">
          ${(methodology.report_references || []).map(ref => `<span class="reference-chip">${esc(ref)}</span>`).join("")}
        </div>
      </div>

      <div class="summary-grid">
        <div class="summary-card">
          <div class="summary-label">Retorno esperado</div>
          <div class="summary-value">${metrics.expected_return_pct > 0 ? "+" : ""}${metrics.expected_return_pct}%</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">Volatilidad anual</div>
          <div class="summary-value">${metrics.volatility_pct}%</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">Sharpe</div>
          <div class="summary-value">${metrics.sharpe_ratio}</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">CVaR</div>
          <div class="summary-value">${result.cvar_pct}%</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">alpha_p</div>
          <div class="summary-value">${(result.alpha_p * 100).toFixed(0)}%</div>
        </div>
        <div class="summary-card">
          <div class="summary-label">Caja chica</div>
          <div class="summary-value">${metrics.cash_weight_pct != null ? metrics.cash_weight_pct + "%" : "0%"}</div>
        </div>
      </div>

      <div class="detail-grid">
        <div class="pf-card">
          <div class="pf-section-title">Lectura metodologica</div>
          <div class="data-list">
            <div><span>Perfil</span><strong>${esc(result.profile_label || "—")}</strong></div>
            <div><span>Universo F5 total</span><strong>${universe.total_f5_count || "—"}</strong></div>
            <div><span>Sub-universo operativo</span><strong>${universe.optimizer_universe_size || "—"}</strong></div>
            <div><span>Holdings finales</span><strong>${universe.target_holdings || "—"}</strong></div>
            <div><span>Comision k</span><strong>${result.commission_rate_pct}% anual</strong></div>
          </div>
        </div>
        <div class="pf-card">
          <div class="pf-section-title">Ciclo semanal reportado</div>
          <div class="data-list">
            <div><span>Cadencia</span><strong>${esc(weeklyCycle.cadence || "Semanal")}</strong></div>
            <div><span>Aceptacion</span><strong>${esc(weeklyCycle.client_acceptance || "—")}</strong></div>
            <div><span>Retiro</span><strong>${esc(weeklyCycle.client_withdrawal || "—")}</strong></div>
            <div><span>Dividendos</span><strong>${esc(weeklyCycle.dividends || "—")}</strong></div>
          </div>
        </div>
      </div>

      <div class="pf-card">
        <div class="pf-section-title">Portafolio recomendado</div>
        <table class="result-table">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Empresa</th>
              <th>Sector</th>
              <th>Peso</th>
              <th>CAGR</th>
              <th>Volatilidad</th>
              <th>Dividend yield</th>
            </tr>
          </thead>
          <tbody>
            ${result.portfolio.map(item => `
              <tr>
                <td><strong>${esc(item.ticker)}</strong></td>
                <td>${esc(item.short_name || "—")}</td>
                <td>${esc(item.sector || "—")}</td>
                <td>${(item.weight * 100).toFixed(2)}%</td>
                <td>${item.cagr_pct != null ? item.cagr_pct + "%" : "—"}</td>
                <td>${item.volatility_pct != null ? item.volatility_pct + "%" : "—"}</td>
                <td>${item.dividend_yield_pct != null ? item.dividend_yield_pct + "%" : "—"}</td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>

      ${methodology.solver_details ? `
        <div class="pf-card">
          <div class="pf-section-title">Motor de resolucion</div>
          <div class="data-list">
            <div><span>Solver</span><strong>${esc(methodology.solver_details.solver_used || "—")}</strong></div>
            <div><span>Estado</span><strong>${esc(methodology.solver_details.status || "—")}</strong></div>
            <div><span>Mensaje</span><strong>${esc(methodology.solver_details.message || "—")}</strong></div>
            <div><span>Tiempo</span><strong>${methodology.solver_details.solve_time_s != null ? methodology.solver_details.solve_time_s.toFixed(3) + " s" : "—"}</strong></div>
          </div>
        </div>
      ` : ""}

      ${renderParameterSummary(result.parameters_used || [])}

      ${(result.efficient_frontier || []).length ? `
        <div class="pf-card">
          <div class="pf-section-title">Frontera eficiente (Markowitz)</div>
          <p style="font-size:13px;color:var(--text-muted);line-height:1.7;margin-bottom:14px">Se calcula sobre el universo operativo y la ventana de calibracion. La marca destaca el portafolio recomendado.</p>
          <div id="frontier-chart" style="height:340px"></div>
        </div>
      ` : ""}

      <div class="pf-card">
        <div class="pf-section-title">Comparacion secundaria</div>
        <div class="action-row">
          <button class="btn-secondary" type="button" onclick="fetchBenchmarkComparison('benchmark-comparison')">Ejecutar caso base + benchmark</button>
        </div>
        <div id="benchmark-comparison"></div>
      </div>
    </div>
  `;
  renderEfficientFrontierChart(result);
  queueMathTypeset();
}

async function fetchBenchmarkComparison(targetId = "benchmark-comparison") {
  const target = document.getElementById(targetId);
  if (!PF.lastResult) return;
  if (target) target.innerHTML = `<div class="callout">Construyendo caso base y benchmark...</div>`;

  const getLastInputValue = (keys, fallback) => {
    for (const key of keys) {
      const value = PF.lastInputs?.[key];
      if (value !== undefined && value !== null && value !== "") return value;
    }
    return fallback;
  };

  const holdings = parseInt(String(getLastInputValue(["target_holdings", "targetHoldings"], 10)), 10) || 10;
  const candidatePool = getLastInputValue(["candidate_pool_size", "candidatePoolSize"], "");
  const sector = getLastInputValue(["sector"], "");

  const benchParams = new URLSearchParams({ target_holdings: String(holdings) });
  if (candidatePool) benchParams.set("candidate_pool_size", String(candidatePool));
  if (sector) benchParams.set("sector", String(sector));

  const baseParams = new URLSearchParams({ n: String(holdings) });
  if (sector) baseParams.set("sector", String(sector));

  try {
    const [baseCase, benchmark] = await Promise.all([
      apiFetch(`/api/portfolio/base_case?${baseParams.toString()}`),
      apiFetch(`/api/portfolio/benchmark?${benchParams.toString()}`),
    ]);
    PF.lastBaseCase = baseCase;
    PF.lastBenchmark = benchmark;
    renderBenchmarkComparison(benchmark, baseCase, targetId);
  } catch (error) {
    if (target) {
      target.innerHTML = `<div class="callout callout-danger">No fue posible construir las comparaciones: ${esc(error.message)}</div>`;
    }
  }
}

function renderBenchmarkComparison(benchmark, baseCase, targetId = "benchmark-comparison") {
  const target = document.getElementById(targetId);
  if (!target || !PF.lastResult) return;
  const base = PF.lastResult.metrics || {};
  const simId = `${targetId}-base-sim`;
  target.innerHTML = `
    <div class="comparison-card">
      <table class="comparison-table">
        <thead>
          <tr>
            <th>Medida</th>
            <th>${esc(PF.lastResult.methodology?.label || "Modelo FinPUC")}</th>
            <th>${esc(baseCase?.metrics?.method_label || "Caso base")}</th>
            <th>${esc(benchmark?.metrics?.method_label || "Benchmark")}</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Retorno esperado</td>
            <td>${base.expected_return_pct > 0 ? "+" : ""}${base.expected_return_pct}%</td>
            <td>${baseCase?.metrics?.expected_return_pct > 0 ? "+" : ""}${baseCase?.metrics?.expected_return_pct ?? "—"}%</td>
            <td>${benchmark?.metrics?.expected_return_pct > 0 ? "+" : ""}${benchmark?.metrics?.expected_return_pct ?? "—"}%</td>
          </tr>
          <tr>
            <td>Volatilidad</td>
            <td>${base.volatility_pct ?? "—"}%</td>
            <td>${baseCase?.metrics?.volatility_pct ?? "—"}%</td>
            <td>${benchmark?.metrics?.volatility_pct ?? "—"}%</td>
          </tr>
          <tr>
            <td>Constructor</td>
            <td>${esc(base.method_label || "—")}</td>
            <td>${esc(baseCase?.metrics?.rebalance_policy || baseCase?.metrics?.method_label || "—")}</td>
            <td>${esc(benchmark?.metrics?.method_label || "—")}</td>
          </tr>
        </tbody>
      </table>
      <div class="action-row" style="margin-top:12px">
        <button class="btn-secondary" type="button" onclick="simulateBaseCaseComparison('${targetId}')">Simular caso base</button>
      </div>
      <div id="${simId}"></div>
    </div>
  `;
}

function renderScenarioView() {
  const contentEl = document.getElementById("content");
  if (!PF.lastResult) {
    contentEl.innerHTML = `
      <div class="pf-section">
        <div class="results-empty">
          Ejecuta primero una metodologia para construir los escenarios favorable, neutro y desfavorable del informe.
          <div class="action-row" style="margin-top:14px">
            <button class="btn-primary" type="button" onclick="pfNavGo('parameters')">Ir a parametros</button>
          </div>
        </div>
      </div>
    `;
    return;
  }

  const result = PF.lastResult;
  const sc = result.scenarios;
  contentEl.innerHTML = `
    <div class="pf-section">
      <div class="hero-card">
        <div class="hero-eyebrow">Escenarios p10 / p50 / p90</div>
        <h2 class="hero-title">Escenarios del portafolio recomendado</h2>
        <p class="hero-copy">La proyeccion traduce el retorno esperado y la volatilidad del portafolio a escenarios favorable, neutro y desfavorable. Referencia: Seccion 4 y componente de Monte Carlo del informe.</p>
      </div>

      <div class="scenario-grid">
        <div class="scenario-card favorable">
          <div class="scenario-label">Favorable (p90)</div>
          <div class="scenario-ret">${sc.favorable.annual_return_pct > 0 ? "+" : ""}${sc.favorable.annual_return_pct}%</div>
          <div class="scenario-cap">Ano 1: <strong>${fmtUSD(sc.favorable.capital_by_year["1"])}</strong></div>
          <div class="scenario-cap">Ano 5: <strong>${fmtUSD(sc.favorable.capital_by_year["5"])}</strong></div>
        </div>
        <div class="scenario-card neutro">
          <div class="scenario-label">Neutro (p50)</div>
          <div class="scenario-ret">${sc.neutro.annual_return_pct > 0 ? "+" : ""}${sc.neutro.annual_return_pct}%</div>
          <div class="scenario-cap">Ano 1: <strong>${fmtUSD(sc.neutro.capital_by_year["1"])}</strong></div>
          <div class="scenario-cap">Ano 5: <strong>${fmtUSD(sc.neutro.capital_by_year["5"])}</strong></div>
        </div>
        <div class="scenario-card desfavorable">
          <div class="scenario-label">Desfavorable (p10)</div>
          <div class="scenario-ret">${sc.desfavorable.annual_return_pct > 0 ? "+" : ""}${sc.desfavorable.annual_return_pct}%</div>
          <div class="scenario-cap">Ano 1: <strong>${fmtUSD(sc.desfavorable.capital_by_year["1"])}</strong></div>
          <div class="scenario-cap">Ano 5: <strong>${fmtUSD(sc.desfavorable.capital_by_year["5"])}</strong></div>
        </div>
      </div>

      <div class="chart-wrap">
        <div class="pf-section-title" style="margin-bottom:8px;border:none;padding:0">Proyeccion mensual del capital</div>
        <div id="pf-scenario-chart" style="height:320px"></div>
      </div>

      <div class="detail-grid">
        <div class="pf-card">
          <div class="pf-section-title">Parametros reportados</div>
          <div class="data-list">
            <div><span>Retorno esperado</span><strong>${result.metrics.expected_return_pct}%</strong></div>
            <div><span>Volatilidad anual</span><strong>${result.metrics.volatility_pct}%</strong></div>
            <div><span>CVaR</span><strong>${result.cvar_pct}%</strong></div>
            <div><span>Comision k</span><strong>${result.commission_rate_pct}%</strong></div>
          </div>
        </div>
        <div class="pf-card">
          <div class="pf-section-title">Referencia academica</div>
          <div class="methodology-copy">Basado en Seccion 4 del informe y en la construccion de escenarios representativos p10/p50/p90 para interpretar riesgo y retorno del portafolio.</div>
        </div>
      </div>
    </div>
  `;
  renderScenarioChart(result.scenario_timeseries);
}

function renderScenarioChart(ts) {
  if (!ts || !ts.months || typeof Plotly === "undefined") return;
  const x = ts.months.map(month => `Mes ${month}`);
  const traces = [
    { x, y: ts.favorable, name: "Favorable", mode: "lines", line: { color: "#1f6f52", width: 2 } },
    { x, y: ts.neutro, name: "Neutro", mode: "lines", line: { color: "#0f4c81", width: 2 } },
    { x, y: ts.desfavorable, name: "Desfavorable", mode: "lines", line: { color: "#b34a3c", width: 2, dash: "dot" } },
  ];
  const layout = {
    ...PLOTLY_LAYOUT_BASE,
    margin: { t: 12, r: 20, b: 48, l: 80 },
    yaxis: { ...PLOTLY_LAYOUT_BASE.yaxis, title: "Capital (USD)", tickformat: ",.0f" },
    legend: { orientation: "h", y: -0.2 },
  };
  Plotly.newPlot("pf-scenario-chart", traces, layout, PLOTLY_CONFIG);
}

function renderSimulation() {
  const defaults = PF.lastResult?.simulation_defaults || {};
  const commission = defaults.commission_rate_pct ?? 1.0;
  const accept = defaults.p2_acceptance_prob_pct ?? 70.0;
  const contentEl = document.getElementById("content");
  contentEl.innerHTML = `
    <div class="pf-section">
      <div class="hero-card">
        <div class="hero-eyebrow">Simulacion del cliente</div>
        <h2 class="hero-title">P1, P2, comisiones y ciclo semanal</h2>
        <p class="hero-copy">La simulacion operacional resume el comportamiento del cliente frente a recomendaciones semanales, aceptacion, comisiones y abandono por drawdown. Referencia: Seccion 2.2.1 y Ecuaciones 4.5 y 4.6.</p>
      </div>

      <div class="parameter-group">
        <h3>Entradas de simulacion</h3>
        <p>La simulacion utiliza los resultados del portafolio recomendado como base, pero permite ajustar explicitamente P2, la comision k, el horizonte y la frecuencia de rebalanceo.</p>
        <div class="field-grid">
          <div class="field-card">
            <label>Capital inicial</label>
            <input id="sim-capital" type="number" value="${esc(String(defaults.initial_capital ?? 100000))}">
            <div class="field-help">Capital de partida del cliente.</div>
            <span class="field-ref">Seccion 2.2.1</span>
          </div>
          <div class="field-card">
            <label>Retorno esperado anual</label>
            <input id="sim-exp-ret" type="number" step="0.1" value="${esc(String(defaults.expected_return_pct ?? 10))}">
            <div class="field-help">Retorno anual del portafolio que alimenta la simulacion.</div>
            <span class="field-ref">Resultados metodologicos</span>
          </div>
          <div class="field-card">
            <label>Volatilidad anual</label>
            <input id="sim-vol" type="number" step="0.1" value="${esc(String(defaults.volatility_pct ?? 20))}">
            <div class="field-help">Volatilidad anual usada para las trayectorias de capital.</div>
            <span class="field-ref">Resultados metodologicos</span>
          </div>
          <div class="field-card">
            <label>Horizonte</label>
            <input id="sim-years" type="number" min="3" max="5" value="3">
            <div class="field-help">Numero de anos simulados.</div>
            <span class="field-ref">Seccion 2.2.1</span>
          </div>
          <div class="field-card">
            <label>Numero de simulaciones</label>
            <input id="sim-n" type="number" min="100" max="2000" step="100" value="500">
            <div class="field-help">Cantidad de trayectorias Monte Carlo generadas.</div>
            <span class="field-ref">Seccion 4 / Monte Carlo</span>
          </div>
          <div class="field-card">
            <label>Umbral P1 de retiro</label>
            <input id="sim-loss-pct" type="number" min="0" max="100" step="1" value="${esc(String(defaults.max_loss_pct ?? 15))}">
            <div class="field-help">Drawdown porcentual a partir del cual se activa la aproximacion operacional de P1.</div>
            <span class="field-ref">Ecuacion 4.5</span>
          </div>
          <div class="field-card">
            <label>Probabilidad base P2</label>
            <input id="sim-accept-pct" type="number" min="0" max="100" step="1" value="${esc(String(accept))}">
            <div class="field-help">Probabilidad base de aceptar una recomendacion semanal.</div>
            <span class="field-ref">Ecuacion 4.6</span>
          </div>
          <div class="field-card">
            <label>Comision anual k</label>
            <input id="sim-commission-pct" type="number" min="0" max="10" step="0.1" value="${esc(String(commission))}">
            <div class="field-help">Comision anual cobrada sobre el capital gestionado.</div>
            <span class="field-ref">Seccion 2.2.1</span>
          </div>
          <div class="field-card">
            <label>Frecuencia de rebalanceo</label>
            <input id="sim-rebalance-weeks" type="number" min="1" max="52" step="1" value="${esc(String(defaults.rebalance_freq_weeks ?? 1))}">
            <div class="field-help">Cantidad de semanas entre recomendaciones.</div>
            <span class="field-ref">Ciclo semanal FinPUC</span>
          </div>
          <div class="field-card">
            <label>Mejora por rebalanceo</label>
            <input id="sim-rebalance-boost-pct" type="number" min="0" max="5" step="0.1" value="${esc(String(defaults.rebalance_return_boost_pct ?? 0.1))}">
            <div class="field-help">Ajuste adicional en retorno al aceptar un rebalanceo.</div>
            <span class="field-ref">Aproximacion operacional del sistema</span>
          </div>
        </div>
      </div>

      <div class="pf-card">
        <div class="action-row">
          <button class="btn-primary" id="sim-btn" onclick="submitSimulation()">Ejecutar simulacion</button>
          <span id="sim-loading" class="subtle-status" style="display:none">Simulando trayectorias de capital y rebalanceos...</span>
        </div>
      </div>

      <div id="sim-result"></div>
    </div>
  `;
}

async function submitSimulation() {
  const payload = {
    initial_capital: parseFloat(document.getElementById("sim-capital")?.value) || 100000,
    expected_return: (parseFloat(document.getElementById("sim-exp-ret")?.value) || 10) / 100,
    volatility: (parseFloat(document.getElementById("sim-vol")?.value) || 20) / 100,
    max_loss_pct: (parseFloat(document.getElementById("sim-loss-pct")?.value) || 15) / 100,
    years: parseInt(document.getElementById("sim-years")?.value, 10) || 3,
    n_simulations: parseInt(document.getElementById("sim-n")?.value, 10) || 500,
    p2_acceptance_prob_pct: parseFloat(document.getElementById("sim-accept-pct")?.value) || 70,
    commission_rate_pct: parseFloat(document.getElementById("sim-commission-pct")?.value) || 1,
    rebalance_freq_weeks: parseInt(document.getElementById("sim-rebalance-weeks")?.value, 10) || 1,
    rebalance_return_boost_pct: parseFloat(document.getElementById("sim-rebalance-boost-pct")?.value) || 0.1,
  };

  const btn = document.getElementById("sim-btn");
  const loading = document.getElementById("sim-loading");
  if (btn) btn.disabled = true;
  if (loading) loading.style.display = "inline";

  try {
    const result = await apiFetch("/api/portfolio/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    PF.lastSimulation = result;
    renderSimulationResult(result, payload.initial_capital);
  } catch (error) {
    document.getElementById("sim-result").innerHTML = `<div class="callout callout-danger">Error al simular: ${esc(error.message)}</div>`;
  } finally {
    if (btn) btn.disabled = false;
    if (loading) loading.style.display = "none";
  }
}

function renderSimulationResult(result, initialCapital) {
  document.getElementById("sim-result").innerHTML = `
    <div class="summary-grid">
      <div class="summary-card">
        <div class="summary-label">Capital final promedio</div>
        <div class="summary-value">${fmtUSD(result.final_capital_mean)}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Capital p10</div>
        <div class="summary-value">${fmtUSD(result.final_capital_p10)}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Capital p90</div>
        <div class="summary-value">${fmtUSD(result.final_capital_p90)}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Tasa de retiro</div>
        <div class="summary-value">${result.withdrawal_rate}%</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Comisiones promedio</div>
        <div class="summary-value">${fmtUSD(result.total_commissions_mean)}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Aceptaciones promedio</div>
        <div class="summary-value">${result.accepted_recommendations_mean}</div>
      </div>
    </div>

    <div class="chart-wrap">
      <div class="pf-section-title" style="margin-bottom:8px;border:none;padding:0">Trayectorias de capital</div>
      <div id="sim-chart" style="height:320px"></div>
    </div>

    <div class="detail-grid">
      <div class="pf-card">
        <div class="pf-section-title">Supuestos operacionales</div>
        <div class="data-list">
          <div><span>Recomendaciones emitidas</span><strong>${result.total_recommendations}</strong></div>
          <div><span>Aceptacion P2</span><strong>${esc(result.assumptions?.acceptance_model || "—")}</strong></div>
          <div><span>Retiro P1</span><strong>${esc(result.assumptions?.withdrawal_model || "—")}</strong></div>
          <div><span>Comision</span><strong>${result.assumptions?.commission_rate_pct || "—"}% anual</strong></div>
        </div>
      </div>
      <div class="pf-card">
        <div class="pf-section-title">Lectura academica</div>
        <div class="methodology-copy">Capital inicial de referencia: ${fmtUSD(initialCapital)}. La simulacion operacional no reemplaza el modelo teorico completo, pero permite visualizar de forma ejecutable la dinamica semanal del sistema descrita en el informe.</div>
      </div>
    </div>
  `;
  renderSimulationChart(result, initialCapital);
}

function renderSimulationChart(result, initialCapital) {
  if (typeof Plotly === "undefined") return;
  const x = result.periods.map(period => `Semana ${period}`);
  const traces = [
    { x, y: result.capital_p90, name: "P90", mode: "lines", line: { color: "#1f6f52", width: 1 } },
    { x, y: result.capital_mean, name: "Media", mode: "lines", line: { color: "#0f4c81", width: 2 } },
    { x, y: result.capital_p10, name: "P10", mode: "lines", line: { color: "#b34a3c", width: 1, dash: "dot" } },
    { x, y: Array(x.length).fill(initialCapital), name: "Capital inicial", mode: "lines", line: { color: "#b48a2c", width: 1, dash: "dash" } },
  ];
  const layout = {
    ...PLOTLY_LAYOUT_BASE,
    margin: { t: 12, r: 20, b: 48, l: 80 },
    yaxis: { ...PLOTLY_LAYOUT_BASE.yaxis, title: "Capital (USD)", tickformat: ",.0f" },
    legend: { orientation: "h", y: -0.2 },
  };
  Plotly.newPlot("sim-chart", traces, layout, PLOTLY_CONFIG);
}

function renderReferencesView() {
  const sections = PF.reportOutline?.sections || [];
  const tables = PF.reportOutline?.tables || [];
  const formulas = PF.reportOutline?.formulae || [];

  document.getElementById("content").innerHTML = `
    <div class="pf-section">
      <div class="hero-card">
        <div class="hero-eyebrow">Datos y referencias</div>
        <h2 class="hero-title">Trazabilidad documental del sistema</h2>
        <p class="hero-copy">Esta vista concentra los accesos al informe, las tablas estructurales y las formulas que sustentan el comportamiento del sistema recomendador.</p>
      </div>

      <div class="reference-grid">
        ${renderReferenceLinks()}
      </div>

      <div class="pf-card">
        <div class="pf-section-title">Tablas y figuras del informe</div>
        <p style="font-size:13px;color:var(--text-muted);line-height:1.7;margin-bottom:14px">Se muestran vistas previas generadas directamente desde el PDF del informe para mantener trazabilidad documental dentro del sistema.</p>
        ${renderReportVisuals()}
      </div>

      <div class="pf-card">
        <div class="pf-section-title">Secciones del informe</div>
        <div class="academic-list">
          ${sections.map(section => `
            <div class="academic-list-item">
              <strong>${esc(section.label)}</strong>
              <p>${esc(section.summary)}</p>
            </div>
          `).join("")}
        </div>
      </div>

      <div class="academic-grid">
        <div class="academic-card">
          <h4>Tablas clave</h4>
          <div class="academic-list">
            ${tables.map(table => `
              <div class="academic-list-item">
                <strong>${esc(table.label)}</strong>
                <p>${esc(table.summary)}</p>
                <p><a class="inline-link" href="${table.image_url}" target="_blank" rel="noopener noreferrer">Ver pagina ${esc(String(table.page_number || "—"))}</a></p>
              </div>
            `).join("")}
          </div>
        </div>
        <div class="academic-card">
          <h4>Formulas visibles</h4>
          <div class="academic-list">
            ${formulas.map(formula => `
              <div class="academic-list-item">
                <strong>${esc(formula.label)}</strong>
                <p>${esc(formula.summary)}</p>
                ${renderFormulaBlock(formula.latex, "")}
              </div>
            `).join("")}
          </div>
        </div>
      </div>

      <div class="pf-card">
        <div class="pf-section-title">Comparacion secundaria</div>
        <div class="action-row">
          <button class="btn-secondary" type="button" onclick="fetchBenchmarkComparison('references-benchmark')">Ejecutar caso base + benchmark</button>
        </div>
        <div id="references-benchmark"></div>
      </div>

      <div class="pf-card">
        <div class="pf-section-title">Distribuciones de retornos (F5)</div>
        <p style="font-size:13px;color:var(--text-muted);line-height:1.7;margin-bottom:14px">Paso inmediato: verificar supuestos distribucionales (normalidad, asimetría, colas) sobre retornos diarios en la ventana de calibracion.</p>
        <div class="action-row">
          <button class="btn-secondary" type="button" onclick="fetchReturnDiagnostics('returns-diagnostics')">Calcular distribuciones</button>
        </div>
        <div id="returns-diagnostics"></div>
      </div>
    </div>
  `;
  queueMathTypeset();
}

async function pfNavGo(section) {
  PF.activeNav = section;
  setPortfolioNavActive(section);
  setNavState("home");
  if (!PF.catalog || !PF.reportOutline) {
    await ensurePortfolioBootstrap();
  }

  if (section === "introduction") renderIntroduction();
  else if (section === "system") renderSystemProfiles();
  else if (section === "methodologies") renderMethodologies();
  else if (section === "parameters") renderParametersView();
  else if (section === "results") renderResultsView();
  else if (section === "scenarios") renderScenarioView();
  else if (section === "simulate") renderSimulation();
  else if (section === "references") renderReferencesView();
}
