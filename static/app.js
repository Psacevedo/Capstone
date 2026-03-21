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
      <div class="welcome-icon">📈</div>
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

// ---- Estado del módulo portafolios ----
const PF = {
  activeNav: "nuevo",        // "nuevo" | "benchmark" | "simulate"
  currentModule: "acciones", // "acciones" | "portafolios"
  lastResult: null,          // última respuesta de /api/portfolio/optimize
  lastBenchmark: null,       // última respuesta de /api/portfolio/benchmark
  lastSimulation: null,      // última respuesta de /api/portfolio/simulate
  recommendations: [],       // [{id, date, status, items}]
};

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

  const contentEl = document.getElementById("content");
  contentEl.innerHTML = `
    <div class="pf-section">
      <div class="pf-card">
        <div class="pf-card-title">📋 Definir Perfil de Riesgo</div>
        <p style="font-size:13px;color:var(--text-muted);margin-bottom:20px">
          Define tu tolerancia máxima de pérdida para recibir un portafolio inicial
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
          <div class="form-group">
            <label class="form-label">Método de optimización</label>
            <select id="pf-method" class="form-select">
              <option value="markowitz">Markowitz (Sharpe máximo)</option>
              <option value="benchmark">Benchmark (top CAGR)</option>
            </select>
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
            ⏳ Optimizando...
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
  const method     = document.getElementById("pf-method").value;
  const maxLossPct = parseInt(document.getElementById("pf-loss-pct").value) / 100;

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
        max_loss_pct:    maxLossPct,
        n_stocks:        nstocks,
        method:          method,
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

  const validHtml = r.validation
    ? `<div class="validation-pill">
         📊 Validación (${r.validation.period}):
         retorno portafolio = <strong style="margin-left:4px">${r.validation.total_return_pct > 0 ? "+" : ""}${r.validation.total_return_pct}%</strong>
         (anualizado: ${r.validation.annualized_return_pct > 0 ? "+" : ""}${r.validation.annualized_return_pct}%)
       </div>`
    : "";

  const html = `
    <!-- Perfil de riesgo -->
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
        <div class="scenario-label">🟢 Favorable</div>
        <div class="scenario-ret" style="color:var(--green)">
          ${sc.favorable.annual_return_pct > 0 ? "+" : ""}${sc.favorable.annual_return_pct}%/año
        </div>
        <div class="scenario-cap">Año 5: ${fmtUSD(sc.favorable.capital_by_year["5"])}</div>
        <div class="scenario-cap">Retorno total: ${sc.favorable.total_return_pct > 0 ? "+" : ""}${sc.favorable.total_return_pct}%</div>
      </div>
      <div class="scenario-card neutro">
        <div class="scenario-label">🔵 Neutro</div>
        <div class="scenario-ret" style="color:var(--azul-claro)">
          ${sc.neutro.annual_return_pct > 0 ? "+" : ""}${sc.neutro.annual_return_pct}%/año
        </div>
        <div class="scenario-cap">Año 5: ${fmtUSD(sc.neutro.capital_by_year["5"])}</div>
        <div class="scenario-cap">Retorno total: ${sc.neutro.total_return_pct > 0 ? "+" : ""}${sc.neutro.total_return_pct}%</div>
      </div>
      <div class="scenario-card desfavorable">
        <div class="scenario-label">🔴 Desfavorable</div>
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
      <div class="pf-card-title" style="color:var(--red)">⚠️ Derecho a retiro</div>
      <p style="font-size:13px;color:var(--text-muted);margin-bottom:12px">
        Si las pérdidas de tu portafolio superan tu tolerancia máxima (${(maxLossPct*100).toFixed(0)}%),
        puedes retirar tu inversión en cualquier momento.
      </p>
      <button class="btn-secondary" style="border-color:var(--red);color:var(--red)"
              onclick="simulateWithdrawal(${capital}, ${maxLossPct})">
        Simular escenario de retiro
      </button>
    </div>`;

  document.getElementById("pf-result").innerHTML = html;
  renderScenarioChart(r.scenario_timeseries);
  renderRecommendations();
}

function renderScenarioChart(ts) {
  if (!ts || !ts.months) return;
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
            ? `<button class="accept-btn" onclick="respondRec(${rec.id}, true)">✓ Aceptar</button>
               <button class="reject-btn"  onclick="respondRec(${rec.id}, false)">✗ Rechazar</button>`
            : `<span class="rec-status ${rec.status}">${rec.status}</span>`}
        </div>
      </div>
      <div style="font-size:12px;color:var(--text-muted)">
        ${rec.items.slice(0, 5).map(p =>
          `<span style="margin-right:12px"><strong>${p.ticker}</strong> ${(p.weight*100).toFixed(1)}%</span>`
        ).join("")}${rec.items.length > 5 ? `<span>+${rec.items.length - 5} más</span>` : ""}
      </div>
    </div>`).join("");
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
      <div class="pf-card-title">🏆 Benchmark Simple — Top CAGR</div>
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
        <div class="pf-card-title">🎲 Simulación de Comportamiento del Cliente</div>
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
          <span id="sim-loading" style="font-size:13px;color:var(--text-muted);display:none">⏳ Simulando...</span>
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



