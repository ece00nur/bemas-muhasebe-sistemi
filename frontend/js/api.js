// Thin fetch wrapper. API is always served at the site root ("/api/..."),
// independent of whichever subdirectory (e.g. /adminpanel/) this SPA is mounted under.
const Api = (() => {
  const TOKEN_KEY = "bemas_token";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }
  function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
  }
  function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
  }

  async function request(path, { method = "GET", body, isForm = false, raw = false } = {}) {
    const headers = {};
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    let payload = body;
    if (body && !isForm) {
      headers["Content-Type"] = "application/json";
      payload = JSON.stringify(body);
    }

    const res = await fetch(`/api${path}`, { method, headers, body: payload });

    // A 401 on an already-authenticated request means the session/token expired.
    // A 401 on the login call itself just means wrong credentials - let it fall
    // through to the generic error handling below so the real backend message
    // ("Hatalı kullanıcı adı veya şifre") is shown instead of a misleading
    // "session expired" message.
    if (res.status === 401 && token && path !== "/auth/login") {
      clearToken();
      window.location.hash = "#/login";
      throw new Error("Oturum süresi doldu, lütfen tekrar giriş yapın.");
    }

    if (!res.ok) {
      let detail = res.statusText;
      try {
        const errJson = await res.json();
        detail = errJson.detail || JSON.stringify(errJson);
      } catch (_) { /* ignore */ }
      throw new Error(detail);
    }

    if (raw) return res;
    if (res.status === 204) return null;
    return res.json();
  }

  return {
    getToken, setToken, clearToken,
    login: (username, password) => request("/auth/login", { method: "POST", body: { username, password } }),
    me: () => request("/auth/me"),

    listCompanies: (q) => request(`/companies${q ? `?q=${encodeURIComponent(q)}` : ""}`),
    createCompany: (data) => request("/companies", { method: "POST", body: data }),
    updateCompany: (id, data) => request(`/companies/${id}`, { method: "PATCH", body: data }),
    deleteCompany: (id) => request(`/companies/${id}`, { method: "DELETE" }),
    allBalances: () => request("/companies/balances/all"),

    listInvoices: (companyId) => request(`/invoices${companyId ? `?company_id=${companyId}` : ""}`),
    createInvoice: (data) => request("/invoices", { method: "POST", body: data }),
    updateInvoice: (id, data) => request(`/invoices/${id}`, { method: "PATCH", body: data }),
    deleteInvoice: (id) => request(`/invoices/${id}`, { method: "DELETE" }),

    createTransaction: (data) => request("/invoices/transactions", { method: "POST", body: data }),
    updateTransaction: (id, data) => request(`/invoices/transactions/${id}`, { method: "PATCH", body: data }),
    listTransactions: (companyId) => request(`/invoices/transactions/list${companyId ? `?company_id=${companyId}` : ""}`),
    deleteTransaction: (id) => request(`/invoices/transactions/${id}`, { method: "DELETE" }),

    uploadInvoiceExcel: (direction, file) => {
      const fd = new FormData();
      fd.append("direction", direction);
      fd.append("file", file);
      return request("/uploads/invoices/excel", { method: "POST", body: fd, isForm: true });
    },
    uploadReceiptPdf: (file) => {
      const fd = new FormData();
      fd.append("file", file);
      return request("/uploads/receipts/pdf", { method: "POST", body: fd, isForm: true });
    },

    listReceipts: (unmatchedOnly) => request(`/receipts${unmatchedOnly ? "?unmatched_only=true" : ""}`),
    confirmReceipt: (id, data) => request(`/receipts/${id}/confirm`, { method: "POST", body: data }),
    deleteReceipt: (id) => request(`/receipts/${id}`, { method: "DELETE" }),

    getLedger: (companyId) => request(`/ledger/${companyId}`),
    exportLedgerUrl: (companyId) => `/api/ledger/${companyId}/export`,
    exportLedgerPdfUrl: (companyId) => `/api/ledger/${companyId}/export-pdf`,
  };
})();
