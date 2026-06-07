/* ============================================================
   ui.js — Componentes y utilidades de UI
   ============================================================ */

function renderSidebar(sectors) {
  const list = document.getElementById("sector-list");
  list.innerHTML = sectors
    .map(
      (s) => `
    <div class="sector-item" data-sector="${esc(s.sector)}"
         onclick="window.location.hash='#/sector/${encodeURIComponent(s.sector)}'">
      <span>${esc(s.sector)}</span>
      <span class="sector-badge">${s.count}</span>
    </div>
  `
    )
    .join("");
}

function setActiveSector(sector) {
  document.querySelectorAll(".sector-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.sector === sector);
  });
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
    current.textContent = "Selecciona un sector";
  } else if (view === "sector") {
    btnHome.style.display = "flex";
    btnSector.style.display = "none";
    sep.style.display = "none";
    current.textContent = STATE.currentSector || "";
  } else if (view === "stock") {
    btnHome.style.display = "flex";
    btnSector.style.display = "flex";
    sep.style.display = "inline";
    document.getElementById("btn-sector-label").textContent = STATE.currentSector || "Sector";
    current.textContent = STATE.currentTicker || "";
  }
}

function applyFilter(stocks) {
  const q = STATE.filterText.trim().toLowerCase();
  if (!q) return stocks;
  return stocks.filter(
    (s) =>
      (s.ticker || "").toLowerCase().includes(q) ||
      (s.short_name || "").toLowerCase().includes(q) ||
      (s.industry || "").toLowerCase().includes(q)
  );
}

function applySort(stocks) {
  const key = STATE.sortKey;
  if (!key) return stocks;
  return [...stocks].sort((a, b) => {
    const nullVal = STATE.sortAsc ? Infinity : -Infinity;
    const va = a[key] ?? nullVal;
    const vb = b[key] ?? nullVal;
    if (va === vb) return 0;
    return STATE.sortAsc ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
  });
}

function sortTable(key) {
  if (STATE.sortKey === key) {
    STATE.sortAsc = !STATE.sortAsc;
  } else {
    STATE.sortKey = key;
    STATE.sortAsc = true;
  }
  STATE.currentPage = 1;
  renderStockList();
  StateManager.save();
}

function changePage(newPage) {
  STATE.currentPage = newPage;
  renderStockList();
  StateManager.save();
}

function updateFilterText(value) {
  STATE.filterText = value;
  STATE.currentPage = 1;
  renderStockList();
  StateManager.save();
}
