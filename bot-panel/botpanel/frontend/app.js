/**
 * Bot Panel — aplicação principal.
 * SPA em JavaScript puro, sem framework, para ficar 100% compatível
 * com deploy estático no Netlify.
 */

// ============================================================
// Estado global
// ============================================================
const State = {
  bots: [],
  currentBotId: null,
  currentTab: "overview",
  openFiles: new Map(), // path -> { content, dirty }
  activeFilePath: null,
  codeMirror: null,
  consoleSocket: null,
  pollHandle: null,
  botDetailPollHandle: null,
};

// ============================================================
// Toasts
// ============================================================
function showToast(message, type = "info") {
  const stack = document.getElementById("toast-stack");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.textContent = message;
  stack.appendChild(toast);
  setTimeout(() => toast.remove(), 4500);
}

function handleApiError(err, fallback = "Ocorreu um erro.") {
  console.error(err);
  showToast(err?.message || fallback, "error");
}

// ============================================================
// Tema
// ============================================================
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  Storage.setTheme(theme);
  const themeSwitch = document.getElementById("theme-switch");
  if (themeSwitch) themeSwitch.classList.toggle("on", theme === "dark");
  if (State.codeMirror) {
    State.codeMirror.setOption("theme", theme === "dark" ? "dracula" : "default");
  }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme");
  applyTheme(current === "dark" ? "light" : "dark");
}

// ============================================================
// Navegação entre views
// ============================================================
function navigateTo(viewName) {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.getElementById(`view-${viewName}`)?.classList.add("active");

  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === viewName);
  });

  const titles = {
    dashboard: "Dashboard",
    bots: "Meus Bots",
    "bot-detail": "Detalhes do Bot",
    settings: "Configurações",
  };
  document.getElementById("page-title").textContent = titles[viewName] || "Bot Panel";

  closeSidebarOnMobile();

  if (viewName === "dashboard") loadDashboard();
  if (viewName === "bots") loadBotsList();
  if (viewName === "settings") loadSettingsView();

  stopBotDetailPolling();
}

function closeSidebarOnMobile() {
  document.getElementById("sidebar").classList.remove("open");
  document.getElementById("sidebar-scrim").classList.remove("open");
}

// ============================================================
// Formatação
// ============================================================
function formatUptime(seconds) {
  if (!seconds || seconds < 1) return "—";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function formatBytes(mb) {
  if (mb > 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb.toFixed(0)} MB`;
}

function timeAgo(dateString) {
  if (!dateString) return "—";
  const diff = (Date.now() - new Date(dateString + "Z").getTime()) / 1000;
  if (diff < 60) return "agora";
  if (diff < 3600) return `${Math.floor(diff / 60)}min atrás`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h atrás`;
  return `${Math.floor(diff / 86400)}d atrás`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ============================================================
// Conexão inicial (tela de "conectar", não é login de usuário)
// ============================================================
function checkConnection() {
  if (!Storage.isConnected()) {
    document.getElementById("connect-screen").classList.remove("hidden");
    document.getElementById("app-shell").style.display = "none";
    return false;
  }
  document.getElementById("connect-screen").classList.add("hidden");
  document.getElementById("app-shell").style.display = "grid";
  return true;
}

async function submitConnection() {
  const url = document.getElementById("connect-url").value.trim();
  const key = document.getElementById("connect-key").value.trim();
  const errorEl = document.getElementById("connect-error");
  errorEl.classList.add("hidden");

  if (!url || !key) {
    errorEl.textContent = "Preencha a URL e a chave de API.";
    errorEl.classList.remove("hidden");
    return;
  }

  try {
    await Api.health(url);
  } catch (_) {
    errorEl.textContent = "Não foi possível conectar a esse endereço. Verifique a URL.";
    errorEl.classList.remove("hidden");
    return;
  }

  Storage.setConnection(url, key);

  // valida a chave de fato chamando uma rota protegida
  try {
    await Api.get("/api/bots");
  } catch (err) {
    errorEl.textContent = "Conectado, mas a chave de API parece inválida.";
    errorEl.classList.remove("hidden");
    localStorage.removeItem("panel_api_key");
    return;
  }

  checkConnection();
  bootstrapApp();
}

// ============================================================
// Inicialização geral
// ============================================================
function bootstrapApp() {
  applyTheme(Storage.getTheme());
  checkServerHealth();
  navigateTo("dashboard");
  if (State.pollHandle) clearInterval(State.pollHandle);
  State.pollHandle = setInterval(() => {
    checkServerHealth();
    if (document.getElementById("view-dashboard").classList.contains("active")) {
      loadDashboard();
    }
    if (document.getElementById("view-bots").classList.contains("active")) {
      refreshBotsGridData();
    }
  }, 8000);
}

async function checkServerHealth() {
  const led = document.getElementById("server-status-led");
  const text = document.getElementById("server-status-text");
  try {
    await Api.health(Storage.getApiUrl());
    led.className = "status-led online";
    text.textContent = "Servidor online";
  } catch (_) {
    led.className = "status-led crashed";
    text.textContent = "Servidor offline";
  }
}

document.addEventListener("DOMContentLoaded", () => {
  setupGlobalListeners();
  if (checkConnection()) {
    bootstrapApp();
  }
});

function setupGlobalListeners() {
  document.getElementById("connect-submit").addEventListener("click", submitConnection);

  document.querySelectorAll(".nav-item[data-view]").forEach((item) => {
    item.addEventListener("click", () => navigateTo(item.dataset.view));
  });
  document.querySelectorAll("[data-view-link]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      navigateTo(el.dataset.viewLink);
    });
  });

  document.getElementById("theme-toggle-btn").addEventListener("click", toggleTheme);
  document.getElementById("theme-switch").addEventListener("click", toggleTheme);

  document.getElementById("menu-toggle").addEventListener("click", () => {
    document.getElementById("sidebar").classList.add("open");
    document.getElementById("sidebar-scrim").classList.add("open");
  });
  document.getElementById("sidebar-scrim").addEventListener("click", closeSidebarOnMobile);

  document.getElementById("refresh-btn").addEventListener("click", () => {
    checkServerHealth();
    const active = document.querySelector(".view.active").id;
    if (active === "view-dashboard") loadDashboard();
    if (active === "view-bots") loadBotsList();
    if (active === "view-bot-detail") loadBotDetail(State.currentBotId);
  });

  setupCreateBotModal();
  setupBotDetailListeners();
  setupSettingsListeners();
}

// ============================================================
// Dashboard
// ============================================================
async function loadDashboard() {
  renderStatsGridSkeleton("stats-grid");
  try {
    const [stats, bots] = await Promise.all([
      Api.get("/api/monitoring/system"),
      Api.get("/api/bots"),
    ]);
    State.bots = bots;
    renderDashboardStats(stats);
    renderDashboardBotsList(bots);
    renderDashboardRestarts(bots);
  } catch (err) {
    handleApiError(err, "Não foi possível carregar o dashboard.");
  }
}

function renderStatsGridSkeleton(gridId) {
  const grid = document.getElementById(gridId);
  if (grid.children.length > 0) return; // evita flicker em refresh
  grid.innerHTML = Array.from({ length: 4 })
    .map(() => `<div class="card stat-card"><div class="skeleton" style="height:52px;"></div></div>`)
    .join("");
}

function progressClass(percent) {
  if (percent > 85) return "";
  if (percent > 60) return "warn";
  return "ok";
}

function renderDashboardStats(stats) {
  const grid = document.getElementById("stats-grid");
  grid.innerHTML = `
    <div class="card stat-card">
      <div class="stat-card-label">Bots online</div>
      <div class="stat-card-value" style="color:var(--status-online);">${stats.bots_online}</div>
    </div>
    <div class="card stat-card">
      <div class="stat-card-label">Bots offline</div>
      <div class="stat-card-value" style="color:var(--text-tertiary);">${stats.bots_offline}</div>
    </div>
    <div class="card stat-card">
      <div class="stat-card-label">CPU do servidor</div>
      <div class="stat-card-value">${stats.cpu_percent.toFixed(0)}<span class="unit">%</span></div>
      <div class="progress-track"><div class="progress-fill ${progressClass(stats.cpu_percent)}" style="width:${stats.cpu_percent}%"></div></div>
    </div>
    <div class="card stat-card">
      <div class="stat-card-label">RAM do servidor</div>
      <div class="stat-card-value">${stats.ram_percent.toFixed(0)}<span class="unit">%</span></div>
      <div class="progress-track"><div class="progress-fill ${progressClass(stats.ram_percent)}" style="width:${stats.ram_percent}%"></div></div>
    </div>
    <div class="card stat-card">
      <div class="stat-card-label">Disco</div>
      <div class="stat-card-value">${stats.disk_percent.toFixed(0)}<span class="unit">%</span></div>
      <div class="progress-track"><div class="progress-fill ${progressClass(stats.disk_percent)}" style="width:${stats.disk_percent}%"></div></div>
    </div>
    <div class="card stat-card">
      <div class="stat-card-label">RAM usada</div>
      <div class="stat-card-value" style="font-size:20px;">${formatBytes(stats.ram_used_mb)}<span class="unit">/ ${formatBytes(stats.ram_total_mb)}</span></div>
    </div>
    <div class="card stat-card">
      <div class="stat-card-label">Disco usado</div>
      <div class="stat-card-value" style="font-size:20px;">${stats.disk_used_gb.toFixed(1)}<span class="unit">/ ${stats.disk_total_gb.toFixed(0)} GB</span></div>
    </div>
    <div class="card stat-card">
      <div class="stat-card-label">Uptime do servidor</div>
      <div class="stat-card-value" style="font-size:20px;">${formatUptime(stats.uptime_seconds)}</div>
    </div>
  `;
}

function renderDashboardBotsList(bots) {
  const container = document.getElementById("dashboard-bots-list");
  if (bots.length === 0) {
    container.innerHTML = `<div class="empty-state" style="padding:24px;"><p>Nenhum bot criado ainda.</p></div>`;
    return;
  }
  container.innerHTML = bots
    .slice(0, 8)
    .map(
      (bot) => `
      <div class="mini-bot-row">
        <span class="status-led ${bot.status === "running" ? "online" : bot.status === "crashed" ? "crashed" : ""}"></span>
        <span class="mini-bot-name">${escapeHtml(bot.name)}</span>
        <span class="mini-bot-uptime">${bot.status === "running" ? timeAgo(bot.last_started_at) : bot.status}</span>
      </div>
    `
    )
    .join("");
}

function renderDashboardRestarts(bots) {
  const container = document.getElementById("dashboard-restarts-list");
  // Busca as últimas reinicializações do primeiro bot com atividade (visão simplificada e leve)
  if (bots.length === 0) {
    container.innerHTML = `<div class="empty-state" style="padding:24px;"><p>Sem histórico ainda.</p></div>`;
    return;
  }
  container.innerHTML = `<p class="text-tertiary" style="font-size:12.5px;">Veja o histórico completo na página de cada bot, aba "Visão geral".</p>`;
}

async function refreshBotsGridData() {
  try {
    const bots = await Api.get("/api/bots");
    State.bots = bots;
    renderBotsGrid(bots);
  } catch (_) {}
}

// ============================================================
// Lista de bots
// ============================================================
async function loadBotsList() {
  const grid = document.getElementById("bots-grid");
  if (grid.children.length === 0) {
    grid.innerHTML = Array.from({ length: 3 })
      .map(() => `<div class="card"><div class="skeleton" style="height:120px;"></div></div>`)
      .join("");
  }
  try {
    const bots = await Api.get("/api/bots");
    State.bots = bots;
    renderBotsGrid(bots);
  } catch (err) {
    handleApiError(err, "Não foi possível carregar os bots.");
  }
}

function renderBotsGrid(bots) {
  const grid = document.getElementById("bots-grid");
  const searchTerm = (document.getElementById("bots-search").value || "").toLowerCase();
  const filtered = bots.filter((b) => b.name.toLowerCase().includes(searchTerm));

  if (filtered.length === 0) {
    grid.innerHTML = `
      <div class="empty-state" style="grid-column:1/-1;">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="4" y="7" width="16" height="12" rx="2"/><path d="M9 7V5a3 3 0 0 1 6 0v2"/></svg>
        <h3>Nenhum bot encontrado</h3>
        <p>Crie seu primeiro bot para começar.</p>
      </div>`;
    return;
  }

  grid.innerHTML = filtered
    .map((bot) => {
      const statusClass = bot.status === "running" ? "online" : bot.status === "crashed" ? "crashed" : "offline";
      return `
      <div class="bot-card" data-bot-id="${bot.id}">
        <div class="bot-card-top">
          <div class="bot-card-identity">
            <span class="status-led ${statusClass}"></span>
            <div style="min-width:0;">
              <div class="bot-card-name">${escapeHtml(bot.name)}</div>
              <div class="bot-card-desc">${escapeHtml(bot.description || bot.start_command)}</div>
            </div>
          </div>
          <span class="badge ${statusClass}">${bot.status}</span>
        </div>
        <div class="bot-card-metrics">
          <div class="bot-metric">
            <span class="bot-metric-label">Uptime</span>
            <span class="bot-metric-value">${bot.status === "running" ? timeAgo(bot.last_started_at) : "—"}</span>
          </div>
          <div class="bot-metric">
            <span class="bot-metric-label">PID</span>
            <span class="bot-metric-value">${bot.pid ?? "—"}</span>
          </div>
          <div class="bot-metric">
            <span class="bot-metric-label">Runtime</span>
            <span class="bot-metric-value">${bot.runtime}</span>
          </div>
        </div>
        ${bot.last_error ? `<div class="bot-card-error" title="${escapeHtml(bot.last_error)}">${escapeHtml(bot.last_error)}</div>` : ""}
        <div class="bot-card-actions">
          <button class="btn btn-sm" data-action="open" data-id="${bot.id}">Abrir</button>
          ${bot.status === "running"
            ? `<button class="btn btn-sm btn-danger" data-action="stop" data-id="${bot.id}">Parar</button>`
            : `<button class="btn btn-sm" data-action="start" data-id="${bot.id}">Iniciar</button>`}
          <button class="btn btn-sm" data-action="restart" data-id="${bot.id}">Reiniciar</button>
        </div>
      </div>`;
    })
    .join("");

  grid.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      handleBotCardAction(btn.dataset.action, btn.dataset.id);
    });
  });
  grid.querySelectorAll(".bot-card").forEach((card) => {
    card.addEventListener("click", () => openBotDetail(card.dataset.botId));
  });
}

async function handleBotCardAction(action, botId) {
  try {
    if (action === "open") return openBotDetail(botId);
    if (action === "start") await Api.post(`/api/bots/${botId}/start`);
    if (action === "stop") await Api.post(`/api/bots/${botId}/stop`);
    if (action === "restart") await Api.post(`/api/bots/${botId}/restart`);
    showToast(`Ação "${action}" executada com sucesso.`, "success");
    refreshBotsGridData();
  } catch (err) {
    handleApiError(err, "Não foi possível executar a ação.");
  }
}

document.getElementById("bots-search")?.addEventListener("input", () => renderBotsGrid(State.bots));

// ============================================================
// Modal: Criar bot
// ============================================================
function setupCreateBotModal() {
  document.getElementById("open-create-bot-modal").addEventListener("click", () => {
    document.getElementById("create-bot-modal").classList.remove("hidden");
  });
  document.getElementById("cancel-create-bot").addEventListener("click", () => {
    document.getElementById("create-bot-modal").classList.add("hidden");
  });
  document.getElementById("submit-create-bot").addEventListener("click", submitCreateBot);
}

async function submitCreateBot() {
  const name = document.getElementById("new-bot-name").value.trim();
  const description = document.getElementById("new-bot-description").value.trim();
  const start_command = document.getElementById("new-bot-command").value.trim();
  const runtime = document.getElementById("new-bot-runtime").value;
  const auto_restart = document.getElementById("new-bot-auto-restart").checked;
  const autostart_on_boot = document.getElementById("new-bot-autostart-boot").checked;

  if (!name || !start_command) {
    showToast("Preencha ao menos o nome e o comando de inicialização.", "error");
    return;
  }

  try {
    const bot = await Api.post("/api/bots", {
      name,
      description,
      start_command,
      runtime,
      auto_restart,
      autostart_on_boot,
    });
    document.getElementById("create-bot-modal").classList.add("hidden");
    ["new-bot-name", "new-bot-description", "new-bot-command"].forEach(
      (id) => (document.getElementById(id).value = "")
    );
    showToast("Bot criado com sucesso.", "success");
    loadBotsList();
    openBotDetail(bot.id);
  } catch (err) {
    handleApiError(err, "Não foi possível criar o bot.");
  }
}

// ============================================================
// Detalhe do bot
// ============================================================
function setupBotDetailListeners() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchBotTab(btn.dataset.tab));
  });

  document.getElementById("detail-start-btn").addEventListener("click", () => botAction("start"));
  document.getElementById("detail-stop-btn").addEventListener("click", () => botAction("stop"));
  document.getElementById("detail-restart-btn").addEventListener("click", () => botAction("restart"));
  document.getElementById("detail-delete-btn").addEventListener("click", deleteCurrentBot);

  document.getElementById("config-save-btn").addEventListener("click", saveBotConfig);

  setupEditorListeners();
  setupFilesManagerListeners();
  setupEnvVarsListeners();
  setupConsoleListeners();
}

async function openBotDetail(botId) {
  State.currentBotId = botId;
  navigateTo("bot-detail");
  switchBotTab("overview");
  await loadBotDetail(botId);
  startBotDetailPolling();
}

function startBotDetailPolling() {
  stopBotDetailPolling();
  State.botDetailPollHandle = setInterval(() => {
    if (State.currentBotId && document.getElementById("view-bot-detail").classList.contains("active")) {
      loadBotDetail(State.currentBotId, true);
    }
  }, 6000);
}

function stopBotDetailPolling() {
  if (State.botDetailPollHandle) {
    clearInterval(State.botDetailPollHandle);
    State.botDetailPollHandle = null;
  }
}

async function loadBotDetail(botId, silent = false) {
  try {
    const [bot, botStats] = await Promise.all([
      Api.get(`/api/bots/${botId}`),
      Api.get(`/api/monitoring/bots/${botId}`),
    ]);
    renderBotDetailHeader(bot);
    renderBotMetrics(bot, botStats);
    if (!silent) fillBotConfigForm(bot);
    if (!silent) await loadRestartHistory(botId);
  } catch (err) {
    if (!silent) handleApiError(err, "Não foi possível carregar o bot.");
  }
}

function renderBotDetailHeader(bot) {
  const statusClass = bot.status === "running" ? "online" : bot.status === "crashed" ? "crashed" : "";
  document.getElementById("detail-status-led").className = `status-led ${statusClass}`;
  document.getElementById("detail-bot-name").textContent = bot.name;
  document.getElementById("detail-bot-desc").textContent = bot.description || bot.start_command;
  document.getElementById("detail-start-btn").disabled = bot.status === "running";
  document.getElementById("detail-stop-btn").disabled = bot.status !== "running";
}

function renderBotMetrics(bot, stats) {
  const grid = document.getElementById("bot-metrics-grid");
  grid.innerHTML = `
    <div class="card stat-card">
      <div class="stat-card-label">Status</div>
      <div class="stat-card-value" style="font-size:18px; text-transform:capitalize;">${bot.status}</div>
    </div>
    <div class="card stat-card">
      <div class="stat-card-label">Uptime</div>
      <div class="stat-card-value" style="font-size:18px;">${formatUptime(stats.uptime_seconds)}</div>
    </div>
    <div class="card stat-card">
      <div class="stat-card-label">CPU do processo</div>
      <div class="stat-card-value">${stats.cpu_percent.toFixed(1)}<span class="unit">%</span></div>
    </div>
    <div class="card stat-card">
      <div class="stat-card-label">RAM do processo</div>
      <div class="stat-card-value" style="font-size:18px;">${formatBytes(stats.ram_mb)}</div>
    </div>
    <div class="card stat-card">
      <div class="stat-card-label">PID</div>
      <div class="stat-card-value" style="font-size:18px;">${stats.pid ?? "—"}</div>
    </div>
  `;

  const errorCard = document.getElementById("bot-error-card");
  if (bot.last_error) {
    errorCard.style.display = "block";
    document.getElementById("bot-error-text").textContent = bot.last_error;
  } else {
    errorCard.style.display = "none";
  }
}

async function loadRestartHistory(botId) {
  try {
    const restarts = await Api.get(`/api/bots/${botId}/restarts`);
    const container = document.getElementById("dashboard-restarts-list");
    if (!document.getElementById("view-dashboard").classList.contains("active")) return;
    if (restarts.length === 0) {
      container.innerHTML = `<div class="empty-state" style="padding:24px;"><p>Sem histórico ainda.</p></div>`;
      return;
    }
    container.innerHTML = restarts
      .slice(0, 10)
      .map(
        (r) => `
        <div class="restart-history-item">
          <span class="restart-reason ${r.reason === "crash" ? "crash" : ""}">${r.reason}</span>
          <span class="text-tertiary">${timeAgo(r.timestamp)}</span>
        </div>`
      )
      .join("");
  } catch (_) {}
}

function switchBotTab(tabName) {
  State.currentTab = tabName;
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.toggle("active", b.dataset.tab === tabName));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.dataset.panel === tabName));

  if (tabName === "editor") loadFileTree();
  if (tabName === "files") loadFilesManager();
  if (tabName === "env") loadEnvVars();
  if (tabName === "console") connectConsole();
  else disconnectConsole();
}

async function botAction(action) {
  try {
    await Api.post(`/api/bots/${State.currentBotId}/${action}`);
    showToast(`Bot ${action === "start" ? "iniciado" : action === "stop" ? "parado" : "reiniciado"}.`, "success");
    loadBotDetail(State.currentBotId);
  } catch (err) {
    handleApiError(err, "Não foi possível executar a ação.");
  }
}

async function deleteCurrentBot() {
  const bot = State.bots.find((b) => b.id === State.currentBotId);
  const confirmed = confirm(`Excluir o bot "${bot?.name || ""}"? Essa ação não pode ser desfeita.`);
  if (!confirmed) return;
  try {
    await Api.delete(`/api/bots/${State.currentBotId}`);
    showToast("Bot excluído.", "success");
    navigateTo("bots");
  } catch (err) {
    handleApiError(err, "Não foi possível excluir o bot.");
  }
}

function fillBotConfigForm(bot) {
  document.getElementById("config-name").value = bot.name;
  document.getElementById("config-description").value = bot.description || "";
  document.getElementById("config-start-command").value = bot.start_command;
  document.getElementById("config-auto-restart").checked = bot.auto_restart;
  document.getElementById("config-autostart-boot").checked = bot.autostart_on_boot;
}

async function saveBotConfig() {
  const payload = {
    name: document.getElementById("config-name").value.trim(),
    description: document.getElementById("config-description").value.trim(),
    start_command: document.getElementById("config-start-command").value.trim(),
    auto_restart: document.getElementById("config-auto-restart").checked,
    autostart_on_boot: document.getElementById("config-autostart-boot").checked,
  };
  try {
    await Api.patch(`/api/bots/${State.currentBotId}`, payload);
    showToast("Configurações salvas.", "success");
    loadBotDetail(State.currentBotId);
  } catch (err) {
    handleApiError(err, "Não foi possível salvar as configurações.");
  }
}

// ============================================================
// Configurações gerais (view "settings")
// ============================================================
function setupSettingsListeners() {
  document.getElementById("settings-save-connection").addEventListener("click", () => {
    const url = document.getElementById("settings-api-url").value.trim();
    const key = document.getElementById("settings-api-key").value.trim();
    if (!url || !key) {
      showToast("Preencha a URL e a chave de API.", "error");
      return;
    }
    Storage.setConnection(url, key);
    showToast("Conexão atualizada.", "success");
    checkServerHealth();
  });
}

function loadSettingsView() {
  document.getElementById("settings-api-url").value = Storage.getApiUrl();
  document.getElementById("settings-api-key").value = Storage.getApiKey();
}

// ============================================================
// Editor de código
// ============================================================
const CODE_MODE_BY_EXT = {
  py: "python", js: "javascript", jsx: "javascript", ts: "javascript", tsx: "javascript",
  json: { name: "javascript", json: true }, html: "htmlmixed", css: "css",
  yml: "yaml", yaml: "yaml", sh: "shell", sql: "sql", toml: "toml",
  md: "markdown", xml: "xml", env: null, txt: null, ini: null, cfg: null, conf: null, log: null,
};

function getFileExtension(path) {
  const parts = path.split(".");
  return parts.length > 1 ? parts.pop().toLowerCase() : "";
}

function initCodeEditor() {
  if (State.codeMirror) return;
  const mount = document.createElement("textarea");
  document.getElementById("code-editor-mount").appendChild(mount);
  State.codeMirror = CodeMirror.fromTextArea(mount, {
    lineNumbers: true,
    theme: Storage.getTheme() === "dark" ? "dracula" : "default",
    autoCloseBrackets: true,
    matchBrackets: true,
    styleActiveLine: true,
    indentUnit: 4,
    tabSize: 4,
    lineWrapping: false,
    extraKeys: {
      "Ctrl-S": saveActiveFile,
      "Cmd-S": saveActiveFile,
      "Ctrl-F": "findPersistent",
      "Cmd-F": "findPersistent",
    },
  });
  State.codeMirror.on("change", () => {
    if (!State.activeFilePath) return;
    const entry = State.openFiles.get(State.activeFilePath);
    if (entry) {
      entry.dirty = entry.content !== State.codeMirror.getValue();
      renderEditorTabs();
    }
  });
}

function setupEditorListeners() {
  document.getElementById("editor-refresh-tree").addEventListener("click", loadFileTree);
  document.getElementById("editor-save-btn").addEventListener("click", saveActiveFile);
  document.getElementById("editor-new-file").addEventListener("click", () => createFileOrFolder(false));
  document.getElementById("editor-new-folder").addEventListener("click", () => createFileOrFolder(true));
  document.getElementById("editor-search-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") searchInEditor(e.target.value);
  });
}

async function loadFileTree() {
  const mount = document.getElementById("file-tree-mount");
  mount.innerHTML = `<div class="skeleton" style="height:200px;"></div>`;
  try {
    const tree = await Api.get(`/api/bots/${State.currentBotId}/files/tree`);
    mount.innerHTML = "";
    mount.appendChild(renderTreeNode(tree, true));
  } catch (err) {
    handleApiError(err, "Não foi possível carregar os arquivos.");
  }
}

function renderTreeNode(node, isRoot = false) {
  const wrapper = document.createElement("div");
  wrapper.className = "tree-node";

  if (!isRoot) {
    const row = document.createElement("div");
    row.className = "tree-node-row";
    row.innerHTML = node.is_dir
      ? `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg><span>${escapeHtml(node.name)}</span>`
      : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg><span>${escapeHtml(node.name)}</span>`;
    row.dataset.path = node.path;
    row.dataset.isDir = node.is_dir;
    if (node.path === State.activeFilePath) row.classList.add("active");

    if (node.is_dir) {
      row.addEventListener("click", () => {
        const childrenEl = wrapper.querySelector(".tree-children");
        if (childrenEl) childrenEl.classList.toggle("hidden");
      });
    } else {
      row.addEventListener("click", () => openFileInEditor(node.path));
      row.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        showFileContextMenu(e, node.path, node.is_dir);
      });
    }
    row.addEventListener("contextmenu", (e) => {
      if (node.is_dir) {
        e.preventDefault();
        showFileContextMenu(e, node.path, node.is_dir);
      }
    });
    wrapper.appendChild(row);
  }

  if (node.is_dir && node.children) {
    const childrenWrapper = document.createElement("div");
    childrenWrapper.className = "tree-children";
    node.children.forEach((child) => childrenWrapper.appendChild(renderTreeNode(child)));
    wrapper.appendChild(childrenWrapper);
  }

  return wrapper;
}

function showFileContextMenu(event, path, isDir) {
  const choice = prompt(
    `"${path}"\n\nDigite: renomear <novo-nome> | excluir | copiar <destino> | mover <destino>`
  );
  if (!choice) return;
  const [cmd, ...rest] = choice.trim().split(" ");
  const arg = rest.join(" ");
  if (cmd === "excluir") return deleteFileOrFolder(path);
  if (cmd === "renomear" && arg) return renameFileOrFolder(path, arg);
  if (cmd === "copiar" && arg) return copyFileOrFolder(path, arg);
  if (cmd === "mover" && arg) return moveFileOrFolder(path, arg);
}

async function openFileInEditor(path) {
  initCodeEditor();
  State.activeFilePath = path;

  if (!State.openFiles.has(path)) {
    try {
      const data = await Api.get(`/api/bots/${State.currentBotId}/files/content?path=${encodeURIComponent(path)}`);
      State.openFiles.set(path, { content: data.content, dirty: false });
    } catch (err) {
      handleApiError(err, "Não foi possível abrir o arquivo.");
      return;
    }
  }

  const entry = State.openFiles.get(path);
  State.codeMirror.setValue(entry.content);
  const ext = getFileExtension(path);
  State.codeMirror.setOption("mode", CODE_MODE_BY_EXT[ext] || null);
  renderEditorTabs();
  highlightActiveTreeNode(path);
}

function highlightActiveTreeNode(path) {
  document.querySelectorAll(".tree-node-row").forEach((row) => {
    row.classList.toggle("active", row.dataset.path === path);
  });
}

function renderEditorTabs() {
  const container = document.getElementById("editor-tabs");
  container.innerHTML = "";
  State.openFiles.forEach((entry, path) => {
    const tab = document.createElement("div");
    tab.className = `editor-tab ${path === State.activeFilePath ? "active" : ""} ${entry.dirty ? "dirty" : ""}`;
    tab.innerHTML = `<span class="dot"></span><span>${escapeHtml(path.split("/").pop())}</span><span class="close-tab">✕</span>`;
    tab.addEventListener("click", (e) => {
      if (e.target.classList.contains("close-tab")) {
        closeEditorTab(path);
      } else {
        openFileInEditor(path);
      }
    });
    container.appendChild(tab);
  });
}

function closeEditorTab(path) {
  const entry = State.openFiles.get(path);
  if (entry?.dirty && !confirm("Este arquivo tem alterações não salvas. Fechar mesmo assim?")) return;
  State.openFiles.delete(path);
  if (State.activeFilePath === path) {
    const remaining = Array.from(State.openFiles.keys());
    State.activeFilePath = remaining[0] || null;
    if (State.activeFilePath) openFileInEditor(State.activeFilePath);
    else State.codeMirror?.setValue("");
  }
  renderEditorTabs();
}

async function saveActiveFile() {
  if (!State.activeFilePath) return;
  const content = State.codeMirror.getValue();
  const statusEl = document.getElementById("editor-save-status");
  statusEl.textContent = "Salvando...";
  try {
    await Api.put(`/api/bots/${State.currentBotId}/files/content`, {
      path: State.activeFilePath,
      content,
    });
    const entry = State.openFiles.get(State.activeFilePath);
    entry.content = content;
    entry.dirty = false;
    renderEditorTabs();
    statusEl.textContent = `Salvo às ${new Date().toLocaleTimeString()}`;
  } catch (err) {
    statusEl.textContent = "";
    handleApiError(err, "Não foi possível salvar o arquivo.");
  }
}

function searchInEditor(term) {
  if (!State.codeMirror || !term) return;
  const cursor = State.codeMirror.getSearchCursor(term);
  if (cursor.findNext()) {
    State.codeMirror.setSelection(cursor.from(), cursor.to());
    State.codeMirror.scrollIntoView(cursor.from());
  }
}

async function createFileOrFolder(isDir) {
  const name = prompt(isDir ? "Nome da nova pasta:" : "Nome do novo arquivo (ex: main.py):");
  if (!name) return;
  try {
    await Api.post(`/api/bots/${State.currentBotId}/files/create`, { path: name, is_dir: isDir });
    showToast(`${isDir ? "Pasta" : "Arquivo"} criado.`, "success");
    loadFileTree();
  } catch (err) {
    handleApiError(err, "Não foi possível criar.");
  }
}

async function deleteFileOrFolder(path) {
  if (!confirm(`Excluir "${path}"? Essa ação não pode ser desfeita.`)) return;
  try {
    await Api.delete(`/api/bots/${State.currentBotId}/files/delete?path=${encodeURIComponent(path)}`);
    State.openFiles.delete(path);
    showToast("Excluído.", "success");
    loadFileTree();
  } catch (err) {
    handleApiError(err, "Não foi possível excluir.");
  }
}

async function renameFileOrFolder(oldPath, newPath) {
  try {
    await Api.post(`/api/bots/${State.currentBotId}/files/rename`, { old_path: oldPath, new_path: newPath });
    showToast("Renomeado.", "success");
    loadFileTree();
  } catch (err) {
    handleApiError(err, "Não foi possível renomear.");
  }
}

async function copyFileOrFolder(sourcePath, destPath) {
  try {
    await Api.post(`/api/bots/${State.currentBotId}/files/copy`, { source_path: sourcePath, dest_path: destPath });
    showToast("Copiado.", "success");
    loadFileTree();
  } catch (err) {
    handleApiError(err, "Não foi possível copiar.");
  }
}

async function moveFileOrFolder(sourcePath, destPath) {
  try {
    await Api.post(`/api/bots/${State.currentBotId}/files/move`, { source_path: sourcePath, dest_path: destPath });
    showToast("Movido.", "success");
    loadFileTree();
  } catch (err) {
    handleApiError(err, "Não foi possível mover.");
  }
}

// ============================================================
// Gerenciador de Arquivos (upload / zip / listagem em tabela)
// ============================================================
function setupFilesManagerListeners() {
  document.getElementById("files-upload-btn").addEventListener("click", () => {
    document.getElementById("files-upload-input").click();
  });
  document.getElementById("files-upload-input").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    await uploadFileToBot(file, file.name);
    e.target.value = "";
  });

  document.getElementById("files-upload-zip-btn").addEventListener("click", () => {
    document.getElementById("files-upload-zip-input").click();
  });
  document.getElementById("files-upload-zip-input").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    await uploadFileToBot(file, file.name);
    if (confirm(`Extrair "${file.name}" agora?`)) {
      try {
        await Api.post(`/api/bots/${State.currentBotId}/files/extract-zip?zip_path=${encodeURIComponent(file.name)}&dest_path=`);
        showToast("ZIP extraído.", "success");
        loadFilesManager();
      } catch (err) {
        handleApiError(err, "Não foi possível extrair o ZIP.");
      }
    }
    e.target.value = "";
  });
}

async function uploadFileToBot(file, path) {
  try {
    await Api.uploadFile(`/api/bots/${State.currentBotId}/files/upload`, file, { path });
    showToast("Arquivo enviado.", "success");
    loadFilesManager();
  } catch (err) {
    handleApiError(err, "Não foi possível enviar o arquivo.");
  }
}

async function loadFilesManager() {
  const container = document.getElementById("files-manager-list");
  container.innerHTML = `<div class="skeleton" style="height:180px;"></div>`;
  try {
    const tree = await Api.get(`/api/bots/${State.currentBotId}/files/tree`);
    renderFilesManagerTable(tree);
  } catch (err) {
    handleApiError(err, "Não foi possível carregar os arquivos.");
  }
}

function flattenTree(node, depth = 0, acc = []) {
  if (node.path) acc.push({ ...node, depth });
  (node.children || []).forEach((child) => flattenTree(child, depth + 1, acc));
  return acc;
}

function renderFilesManagerTable(tree) {
  const items = flattenTree(tree);
  const container = document.getElementById("files-manager-list");
  if (items.length === 0) {
    container.innerHTML = `<div class="empty-state"><p>Nenhum arquivo ainda. Envie um arquivo ou crie um pelo editor.</p></div>`;
    return;
  }
  container.innerHTML = `
    <table style="width:100%; border-collapse:collapse; font-size:13px;">
      <thead>
        <tr style="text-align:left; color:var(--text-tertiary); font-size:11.5px; text-transform:uppercase;">
          <th style="padding:8px 6px;">Nome</th>
          <th style="padding:8px 6px;">Tamanho</th>
          <th style="padding:8px 6px;">Modificado</th>
          <th style="padding:8px 6px;"></th>
        </tr>
      </thead>
      <tbody>
        ${items
          .map(
            (item) => `
          <tr style="border-top:1px solid var(--border-subtle);">
            <td style="padding:8px 6px; padding-left:${8 + item.depth * 16}px;">${escapeHtml(item.name)}${item.is_dir ? "/" : ""}</td>
            <td style="padding:8px 6px; color:var(--text-tertiary);">${item.is_dir ? "—" : formatBytes((item.size || 0) / (1024 * 1024))}</td>
            <td style="padding:8px 6px; color:var(--text-tertiary);">${item.modified_at ? timeAgo(item.modified_at) : "—"}</td>
            <td style="padding:8px 6px; text-align:right;">
              ${!item.is_dir ? `<button class="btn btn-sm btn-ghost" data-download="${item.path}">Baixar</button>` : ""}
              <button class="btn btn-sm btn-ghost" data-delete="${item.path}">Excluir</button>
            </td>
          </tr>`
          )
          .join("")}
      </tbody>
    </table>
  `;

  container.querySelectorAll("[data-download]").forEach((btn) => {
    btn.addEventListener("click", () => {
      window.open(Api.downloadUrl(`/api/bots/${State.currentBotId}/files/download?path=${encodeURIComponent(btn.dataset.download)}`), "_blank");
    });
  });
  container.querySelectorAll("[data-delete]").forEach((btn) => {
    btn.addEventListener("click", () => deleteFileOrFolder(btn.dataset.delete).then(loadFilesManager));
  });
}

// ============================================================
// Variáveis de ambiente
// ============================================================
let envRevealed = false;

function setupEnvVarsListeners() {
  document.getElementById("env-reveal-btn").addEventListener("click", async () => {
    envRevealed = !envRevealed;
    document.getElementById("env-reveal-btn").textContent = envRevealed ? "Ocultar valores" : "Mostrar valores";
    await loadEnvVars();
  });
  document.getElementById("env-add-row-btn").addEventListener("click", () => addEnvRow("", ""));
  document.getElementById("env-save-btn").addEventListener("click", saveEnvVars);
}

async function loadEnvVars() {
  const container = document.getElementById("env-vars-list");
  container.innerHTML = `<div class="skeleton" style="height:80px;"></div>`;
  try {
    const data = await Api.get(`/api/bots/${State.currentBotId}/env?reveal=${envRevealed}`);
    container.innerHTML = "";
    const entries = Object.entries(data.variables);
    if (entries.length === 0) {
      container.innerHTML = `<p class="text-tertiary" style="font-size:13px; padding:12px 0;">Nenhuma variável definida ainda. Clique em "+ Variável" para adicionar.</p>`;
    } else {
      entries.forEach(([key, value]) => addEnvRow(key, value));
    }
  } catch (err) {
    handleApiError(err, "Não foi possível carregar as variáveis.");
  }
}

function addEnvRow(key, value) {
  const container = document.getElementById("env-vars-list");
  const emptyMsg = container.querySelector("p");
  if (emptyMsg) emptyMsg.remove();

  const row = document.createElement("div");
  row.className = "env-row";
  row.innerHTML = `
    <input type="text" placeholder="NOME_DA_VARIAVEL" value="${escapeHtml(key)}" data-role="key" />
    <input type="${envRevealed ? "text" : "password"}" placeholder="valor" value="${escapeHtml(value)}" data-role="value" />
    <button class="btn btn-sm btn-ghost" data-role="remove">✕</button>
  `;
  row.querySelector("[data-role='remove']").addEventListener("click", () => row.remove());
  container.appendChild(row);
}

async function saveEnvVars() {
  const rows = document.querySelectorAll("#env-vars-list .env-row");
  const variables = {};
  rows.forEach((row) => {
    const key = row.querySelector("[data-role='key']").value.trim();
    const value = row.querySelector("[data-role='value']").value;
    if (key) variables[key] = value;
  });
  const restart_bot = document.getElementById("env-restart-checkbox").checked;

  try {
    await Api.put(`/api/bots/${State.currentBotId}/env`, { variables, restart_bot });
    showToast("Variáveis salvas.", "success");
    loadEnvVars();
    if (restart_bot) loadBotDetail(State.currentBotId);
  } catch (err) {
    handleApiError(err, "Não foi possível salvar as variáveis.");
  }
}

// ============================================================
// Console em tempo real (WebSocket)
// ============================================================
function setupConsoleListeners() {
  document.getElementById("console-clear-btn").addEventListener("click", clearConsole);
  document.getElementById("console-download-btn").addEventListener("click", downloadConsoleLogs);
  document.getElementById("console-search").addEventListener("input", filterConsoleLines);
}

async function connectConsole() {
  disconnectConsole();
  const output = document.getElementById("console-output");
  output.innerHTML = "";

  try {
    const history = await Api.get(`/api/bots/${State.currentBotId}/logs?limit=500`);
    history.lines.forEach((line) => appendConsoleLine(line));
  } catch (_) {}

  const wsUrl = Api.wsUrl(`/api/bots/${State.currentBotId}/console`);
  const socket = new WebSocket(wsUrl);
  socket.onmessage = (event) => appendConsoleLine(event.data);
  socket.onerror = () => showToast("Conexão do console perdida.", "error");
  State.consoleSocket = socket;
}

function disconnectConsole() {
  if (State.consoleSocket) {
    State.consoleSocket.close();
    State.consoleSocket = null;
  }
}

function appendConsoleLine(text) {
  const output = document.getElementById("console-output");
  const line = document.createElement("div");
  const isError = /error|erro|exception|traceback/i.test(text);
  line.className = `console-line ${isError ? "err" : ""}`;
  line.textContent = text;
  output.appendChild(line);
  output.scrollTop = output.scrollHeight;
}

function filterConsoleLines() {
  const term = document.getElementById("console-search").value.toLowerCase();
  document.querySelectorAll("#console-output .console-line").forEach((line) => {
    line.style.display = !term || line.textContent.toLowerCase().includes(term) ? "" : "none";
  });
}

async function clearConsole() {
  if (!confirm("Limpar todos os logs deste bot?")) return;
  try {
    await Api.delete(`/api/bots/${State.currentBotId}/logs`);
    document.getElementById("console-output").innerHTML = "";
    showToast("Logs limpos.", "success");
  } catch (err) {
    handleApiError(err, "Não foi possível limpar os logs.");
  }
}

function downloadConsoleLogs() {
  window.open(Api.downloadUrl(`/api/bots/${State.currentBotId}/logs/download`), "_blank");
}
