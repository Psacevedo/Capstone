/* ============================================================
   state-manager.js — Gestión de estado con localStorage
   ============================================================ */

const StateManager = {
  STORAGE_KEY: "p4_finpuc_state",

  save() {
    try {
      const stateToSave = {
        currentSector: STATE.currentSector,
        currentTicker: STATE.currentTicker,
        currentPage: STATE.currentPage,
        sortKey: STATE.sortKey,
        sortAsc: STATE.sortAsc,
        filterText: STATE.filterText,
      };
      localStorage.setItem(this.STORAGE_KEY, JSON.stringify(stateToSave));
    } catch (e) {
      console.warn("No se pudo guardar estado:", e);
    }
  },

  load() {
    try {
      const saved = localStorage.getItem(this.STORAGE_KEY);
      if (saved) {
        const data = JSON.parse(saved);
        Object.assign(STATE, data);
      }
    } catch (e) {
      console.warn("No se pudo cargar estado:", e);
    }
  },

  clear() {
    try {
      localStorage.removeItem(this.STORAGE_KEY);
      STATE.currentSector = null;
      STATE.currentTicker = null;
      STATE.currentPage = 1;
      STATE.sortKey = null;
      STATE.sortAsc = true;
      STATE.filterText = "";
    } catch (e) {
      console.warn("No se pudo limpiar estado:", e);
    }
  },

  getSectorCache(sector) {
    const key = `sector_${sector}`;
    try {
      const cached = localStorage.getItem(key);
      return cached ? JSON.parse(cached) : null;
    } catch (e) {
      return null;
    }
  },

  setSectorCache(sector, data, ttl = 3600000) {
    const key = `sector_${sector}`;
    try {
      const item = { data, expiry: Date.now() + ttl };
      localStorage.setItem(key, JSON.stringify(item));
    } catch (e) {
      console.warn("No se pudo cachear sector:", e);
    }
  },

  isCacheValid(sector) {
    const key = `sector_${sector}`;
    try {
      const item = localStorage.getItem(key);
      if (!item) return false;
      const { expiry } = JSON.parse(item);
      return expiry > Date.now();
    } catch (e) {
      return false;
    }
  },
};

// Auto-guardar estado periódicamente
setInterval(() => StateManager.save(), 5000);
