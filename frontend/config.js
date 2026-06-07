/* ============================================================
   config.js — Configuración y constantes globales
   ============================================================ */

const CONFIG = {
  PAGE_SIZE: 100,
  API_BASE: "",
  CACHE_DURATION: 300000, // 5 minutos

  PLOTLY_LAYOUT: {
    paper_bgcolor: "#161b22",
    plot_bgcolor: "#161b22",
    font: { color: "#e6edf3", size: 11 },
    margin: { t: 8, r: 10, b: 40, l: 60 },
    xaxis: { gridcolor: "#30363d", linecolor: "#30363d", zerolinecolor: "#30363d" },
    yaxis: { gridcolor: "#30363d", linecolor: "#30363d", zerolinecolor: "#30363d" },
  },

  PLOTLY_CONFIG: {
    displayModeBar: false,
    responsive: true,
  },
};

const STATE = {
  sectors: [],
  sectorStocks: {},
  currentSector: null,
  currentTicker: null,
  currentPage: 1,
  sortKey: null,
  sortAsc: true,
  filterText: "",
};
