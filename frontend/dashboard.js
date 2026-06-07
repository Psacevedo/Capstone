/* ============================================================
   dashboard.js — Dashboard de métricas del sistema
   ============================================================ */

const Dashboard = {
  metrics: {
    totalSectors: 0,
    totalStocks: 0,
    activeSector: null,
    cacheHits: 0,
    cacheMisses: 0,
    apiCalls: 0,
    apiErrors: 0,
    averageResponseTime: 0,
    lastUpdated: new Date(),
  },

  init() {
    this.loadMetrics();
    this.renderDashboard();
    setInterval(() => this.refreshMetrics(), 30000); // Cada 30s
  },

  async loadMetrics() {
    try {
      const data = await apiFetch("/api/sectors");
      this.metrics.totalSectors = data.length;
      this.metrics.totalStocks = data.reduce((sum, s) => sum + (s.count || 0), 0);
      this.metrics.lastUpdated = new Date();
      this.saveToDashboard();
    } catch (e) {
      console.warn("Error cargando métricas:", e);
    }
  },

  recordApiCall(success, responseTime) {
    this.metrics.apiCalls++;
    if (success) {
      this.metrics.cacheHits++;
      this.metrics.averageResponseTime =
        (this.metrics.averageResponseTime * (this.metrics.cacheHits - 1) + responseTime) /
        this.metrics.cacheHits;
    } else {
      this.metrics.apiErrors++;
    }
    this.saveToDashboard();
  },

  saveToDashboard() {
    try {
      localStorage.setItem("p4_metrics", JSON.stringify(this.metrics));
    } catch (e) {
      console.warn("Error guardando métricas:", e);
    }
  },

  loadFromDashboard() {
    try {
      const saved = localStorage.getItem("p4_metrics");
      if (saved) {
        const data = JSON.parse(saved);
        Object.assign(this.metrics, data);
      }
    } catch (e) {
      console.warn("Error cargando métricas guardadas:", e);
    }
  },

  refreshMetrics() {
    this.loadMetrics();
    this.renderDashboard();
  },

  renderDashboard() {
    const el = document.getElementById("dashboard-panel");
    if (!el) return;

    const cacheHitRate = this.metrics.apiCalls > 0 ?
      ((this.metrics.cacheHits / this.metrics.apiCalls) * 100).toFixed(1) :
      "0.0";

    const timeago = this.getTimeago(this.metrics.lastUpdated);

    el.innerHTML = `
      <div class="dashboard">
        <div class="dashboard-header">
          <h3>📊 Métricas</h3>
          <span class="dashboard-time">${timeago}</span>
        </div>

        <div class="dashboard-grid">
          <div class="metric-card">
            <div class="metric-label">Sectores</div>
            <div class="metric-value">${this.metrics.totalSectors}</div>
          </div>

          <div class="metric-card">
            <div class="metric-label">Acciones</div>
            <div class="metric-value">${this.metrics.totalStocks}</div>
          </div>

          <div class="metric-card">
            <div class="metric-label">Llamadas API</div>
            <div class="metric-value">${this.metrics.apiCalls}</div>
          </div>

          <div class="metric-card">
            <div class="metric-label">Tasa Éxito</div>
            <div class="metric-value">${cacheHitRate}%</div>
            <div class="metric-subtext">${this.metrics.cacheHits}/${this.metrics.apiCalls}</div>
          </div>

          <div class="metric-card">
            <div class="metric-label">Errores</div>
            <div class="metric-value ${this.metrics.apiErrors > 0 ? 'error' : ''}">${this.metrics.apiErrors}</div>
          </div>

          <div class="metric-card">
            <div class="metric-label">Resp. Prom.</div>
            <div class="metric-value">${this.metrics.averageResponseTime.toFixed(0)}ms</div>
          </div>
        </div>

        <div class="dashboard-footer">
          <button onclick="Dashboard.clearMetrics()" class="btn-small">Limpiar</button>
        </div>
      </div>
    `;
  },

  getTimeago(date) {
    const now = new Date();
    const diff = now - date;
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);

    if (seconds < 60) return "Hace segundos";
    if (minutes < 60) return `Hace ${minutes}m`;
    if (hours < 24) return `Hace ${hours}h`;
    return date.toLocaleDateString();
  },

  clearMetrics() {
    this.metrics = {
      totalSectors: 0,
      totalStocks: 0,
      activeSector: null,
      cacheHits: 0,
      cacheMisses: 0,
      apiCalls: 0,
      apiErrors: 0,
      averageResponseTime: 0,
      lastUpdated: new Date(),
    };
    this.saveToDashboard();
    this.loadMetrics();
  },
};

// Inicializar cuando document esté listo
document.addEventListener("DOMContentLoaded", () => {
  Dashboard.loadFromDashboard();
  Dashboard.init();
});
