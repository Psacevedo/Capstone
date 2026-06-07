/* ============================================================
   routing.js — Gestión de rutas y navegación
   ============================================================ */

function handleHash() {
  const hash = window.location.hash.replace("#", "");
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
  STATE.currentSector = null;
  STATE.currentTicker = null;
  STATE.sortKey = null;
  STATE.sortAsc = true;
  STATE.filterText = "";
  STATE.currentPage = 1;
  setActiveSector(null);
  setNavState("home");
  showContent(`
    <div class="welcome">
      <div class="welcome-icon">📊</div>
      <h3>Bienvenido al módulo Acciones</h3>
      <p>Selecciona un sector en el panel izquierdo para explorar las acciones disponibles.</p>
    </div>
  `);
  window.location.hash = "#/";
  StateManager.save();
}

function goSector() {
  if (STATE.currentSector) {
    window.location.hash = `#/sector/${encodeURIComponent(STATE.currentSector)}`;
  }
}
