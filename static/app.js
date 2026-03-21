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

async function apiFetch(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API ${res.status}: ${url}`);
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
