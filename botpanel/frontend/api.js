/**
 * Cliente da API do backend.
 *
 * Todas as chamadas passam por aqui, o que garante que a chave de API
 * (X-API-Key) é sempre enviada automaticamente. O usuário nunca vê uma
 * tela de login: a chave é digitada uma única vez (tela de conexão) e
 * fica salva no localStorage deste navegador.
 */
const Storage = {
  getApiUrl() {
    return localStorage.getItem("panel_api_url") || window.PANEL_CONFIG?.API_BASE_URL || "";
  },
  getApiKey() {
    return localStorage.getItem("panel_api_key") || "";
  },
  setConnection(url, key) {
    localStorage.setItem("panel_api_url", url.replace(/\/+$/, ""));
    localStorage.setItem("panel_api_key", key);
  },
  isConnected() {
    return Boolean(this.getApiUrl() && this.getApiKey());
  },
  getTheme() {
    return localStorage.getItem("panel_theme") || "dark";
  },
  setTheme(theme) {
    localStorage.setItem("panel_theme", theme);
  },
};

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

const Api = {
  async _request(path, options = {}) {
    const baseUrl = Storage.getApiUrl();
    const apiKey = Storage.getApiKey();
    if (!baseUrl || !apiKey) {
      throw new ApiError("Não conectado ao backend.", 0);
    }

    const headers = {
      "X-API-Key": apiKey,
      ...(options.headers || {}),
    };
    if (options.body && !(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }

    let response;
    try {
      response = await fetch(`${baseUrl}${path}`, { ...options, headers });
    } catch (err) {
      throw new ApiError("Não foi possível conectar ao backend. Verifique a URL e se o servidor está online.", 0);
    }

    if (!response.ok) {
      let detail = `Erro ${response.status}`;
      try {
        const body = await response.json();
        detail = body.detail || detail;
      } catch (_) {}
      throw new ApiError(detail, response.status);
    }

    if (response.status === 204) return null;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) return response.json();
    return response;
  },

  get(path) {
    return this._request(path, { method: "GET" });
  },
  post(path, body) {
    return this._request(path, {
      method: "POST",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  },
  put(path, body) {
    return this._request(path, { method: "PUT", body: JSON.stringify(body) });
  },
  patch(path, body) {
    return this._request(path, { method: "PATCH", body: JSON.stringify(body) });
  },
  delete(path) {
    return this._request(path, { method: "DELETE" });
  },
  async uploadFile(path, file, extraParams = {}) {
    const baseUrl = Storage.getApiUrl();
    const apiKey = Storage.getApiKey();
    const formData = new FormData();
    formData.append("file", file);
    const query = new URLSearchParams(extraParams).toString();
    const response = await fetch(`${baseUrl}${path}?${query}`, {
      method: "POST",
      headers: { "X-API-Key": apiKey },
      body: formData,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new ApiError(body.detail || "Falha no upload.", response.status);
    }
    return response.json();
  },
  downloadUrl(path) {
    const baseUrl = Storage.getApiUrl();
    const apiKey = Storage.getApiKey();
    const separator = path.includes("?") ? "&" : "?";
    return `${baseUrl}${path}${separator}api_key=${encodeURIComponent(apiKey)}`;
  },
  wsUrl(path) {
    const baseUrl = Storage.getApiUrl().replace(/^http/, "ws");
    const apiKey = Storage.getApiKey();
    return `${baseUrl}${path}?api_key=${encodeURIComponent(apiKey)}`;
  },
  async health(url) {
    const response = await fetch(`${url.replace(/\/+$/, "")}/health`);
    if (!response.ok) throw new Error("offline");
    return response.json();
  },
};
