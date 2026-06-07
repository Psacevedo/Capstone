/* ============================================================
   utils.js — Funciones utilitarias comunes
   ============================================================ */

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function esc(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function fmtCap(val) {
  if (val == null) return '<span class="val-na">—</span>';
  if (val >= 1e12) return (val / 1e12).toFixed(1) + "T";
  if (val >= 1e9) return (val / 1e9).toFixed(1) + "B";
  if (val >= 1e6) return (val / 1e6).toFixed(1) + "M";
  return (val / 1e3).toFixed(1) + "K";
}

function fmtPct(val, signed = false) {
  if (val == null) return '<span class="val-na">—</span>';
  const pct = (val * 100).toFixed(2);
  const sign = signed && val > 0 ? "+" : "";
  const cls = signed ? (val > 0 ? "pos" : val < 0 ? "neg" : "") : "";
  return `<span class="${cls}">${sign}${pct}%</span>`;
}

function fmtNum(val, decimals = 2) {
  if (val == null) return '<span class="val-na">—</span>';
  return val.toFixed(decimals);
}

async function apiFetch(url, options = {}) {
  const response = await fetch(CONFIG.API_BASE + url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API error ${response.status}: ${text}`);
  }

  return response.json();
}

function showContent(html) {
  const main = document.getElementById("main-content");
  if (main) {
    main.innerHTML = html;
    window.scrollTo(0, 0);
  }
}

function showSkeletonTable() {
  const skeleton = `
    <div style="padding: 40px; text-align: center;">
      <div style="color: var(--text-muted); font-size: 14px;">Cargando...</div>
    </div>
  `;
  showContent(skeleton);
}

function showError(message) {
  showContent(`
    <div style="padding: 40px; text-align: center; color: var(--red);">
      <p>${esc(message)}</p>
      <button onclick="window.location.hash='#/'" style="margin-top: 16px;">Volver al inicio</button>
    </div>
  `);
}
