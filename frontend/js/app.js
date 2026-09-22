const App = (() => {
  const root = document.getElementById("app");
  let currentUser = null;

  const fmtMoney = (n) => (n ?? 0).toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtDate = (d) => d ? new Date(d).toLocaleDateString("tr-TR") : "-";
  // A bare signed number ("-3.600,00") is ambiguous to whoever reads a sent
  // statement - always show the absolute amount plus who owes whom in words.
  function fmtNetBalance(n) {
    const v = n ?? 0;
    if (Math.abs(v) < 0.005) return "Bakiye yok (0,00 TRY)";
    return v > 0
      ? `${fmtMoney(v)} TRY (Müşteri Borcu)`
      : `${fmtMoney(Math.abs(v))} TRY (Bizim Borcumuz)`;
  }
  // Always shows a non-negative "still owed" figure; if payments exceeded
  // invoices, the excess becomes a separately-labeled credit line instead of
  // a bare negative number under a "debt" stat.
  function fmtDebtCredit(n, creditLabel) {
    const v = n ?? 0;
    const debtHtml = `${fmtMoney(Math.max(v, 0))} TRY`;
    if (v >= -0.005) return debtHtml;
    return `${debtHtml}<div class="hint" style="margin-top:4px">${esc(creditLabel)}: ${fmtMoney(Math.abs(v))} TRY</div>`;
  }
  const esc = (s) => (s ?? "").toString().replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function toast(msg) {
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3500);
  }

  function openEditRowModal({ rowType, initial, onSave }) {
    const isInvoice = rowType === "invoice";
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal-card">
        <h3>${isInvoice ? "Faturayı Düzenle" : "Ödemeyi Düzenle"}</h3>
        <form id="editRowForm">
          ${isInvoice ? `<label>Fatura No</label><input name="invoice_number" value="${esc(initial.reference)}" required>` : ""}
          <label>Tarih</label><input name="date" type="date" value="${initial.date}" required>
          <label>Tutar</label><input name="amount" type="number" step="0.01" value="${initial.amount}" required>
          <label>Açıklama</label><input name="description" value="${esc(initial.description || "")}">
          <div class="modal-actions">
            <button class="primary" type="submit">Kaydet</button>
            <button class="secondary" type="button" id="editRowCancel">İptal</button>
          </div>
        </form>
      </div>
    `;
    document.body.appendChild(overlay);
    overlay.querySelector("#editRowCancel").onclick = () => overlay.remove();
    overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
    overlay.querySelector("#editRowForm").onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const data = Object.fromEntries(fd.entries());
      data.amount = Number(data.amount);
      try {
        await onSave(data);
        overlay.remove();
      } catch (err) {
        toast(err.message);
      }
    };
  }

  function layout(activeRoute, contentHtml) {
    const links = [
      ["#/dashboard", "Panel"],
      ["#/companies", "Cari Hesaplar"],
      ["#/uploads", "Yükleme"],
      ["#/receipts", "Dekontlar"],
    ];
    root.innerHTML = `
      <div class="topbar">
        <h1>Bemas Treyler &middot; Cari Hesap Takip</h1>
        <nav>
          ${links.map(([href, label]) => `<a href="${href}" class="${activeRoute === href ? "active" : ""}">${label}</a>`).join("")}
          <button class="linklike" id="logoutBtn">Çıkış (${esc(currentUser?.username || "")})</button>
        </nav>
      </div>
      <div class="container">${contentHtml}</div>
    `;
    document.getElementById("logoutBtn").onclick = () => {
      Api.clearToken();
      currentUser = null;
      window.location.hash = "#/login";
    };
  }

  // ---------- Routes ----------

  function renderLogin() {
    root.innerHTML = `
      <div class="login-wrap">
        <div class="card login-card">
          <h2>Yönetici Girişi</h2>
          <form id="loginForm">
            <label>Kullanıcı Adı</label>
            <input name="username" required autofocus>
            <label>Şifre</label>
            <input name="password" type="password" required>
            <button class="primary" type="submit" style="width:100%">Giriş Yap</button>
            <div class="error-msg" id="loginError"></div>
          </form>
        </div>
      </div>
    `;
    document.getElementById("loginForm").onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      try {
        const res = await Api.login(fd.get("username"), fd.get("password"));
        Api.setToken(res.access_token);
        currentUser = await Api.me();
        window.location.hash = "#/dashboard";
      } catch (err) {
        document.getElementById("loginError").textContent = err.message;
      }
    };
  }

  async function renderDashboard() {
    layout("#/dashboard", `<div class="card">Yükleniyor...</div>`);
    const balances = await Api.allBalances();

    const totalReceivable = balances.reduce((s, b) => s + b.net_customer_debt, 0);
    const totalPayable = balances.reduce((s, b) => s + b.net_company_debt, 0);

    const rows = balances.map(b => `
      <tr>
        <td><a class="company-link" href="#/companies/${b.company_id}">${esc(b.company_name)}</a></td>
        <td>${esc(b.tax_id)}</td>
        <td class="num">${fmtMoney(b.net_customer_debt)}</td>
        <td class="num">${fmtMoney(b.net_company_debt)}</td>
        <td class="num ${b.net_balance >= 0 ? "pos" : "neg"}">${fmtNetBalance(b.net_balance)}</td>
      </tr>
    `).join("");

    layout("#/dashboard", `
      <div class="grid">
        <div class="stat"><div class="label">Firma Sayısı</div><div class="value">${balances.length}</div></div>
        <div class="stat"><div class="label">Toplam Müşteri Alacağı</div><div class="value pos">${fmtMoney(totalReceivable)} TRY</div></div>
        <div class="stat"><div class="label">Toplam Tedarikçi Borcu</div><div class="value neg">${fmtMoney(totalPayable)} TRY</div></div>
      </div>
      <div class="card">
        <h2>Firma Bazlı Bakiyeler</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Firma</th><th>Vergi No</th><th class="num">Müşteri Borcu</th><th class="num">Bizim Borcumuz</th><th class="num">Net Bakiye</th></tr></thead>
            <tbody>${rows || `<tr><td colspan="5">Henüz firma yok.</td></tr>`}</tbody>
          </table>
        </div>
      </div>
    `);
  }

  async function renderCompanies() {
    layout("#/companies", `<div class="card">Yükleniyor...</div>`);
    const companies = await Api.listCompanies();

    const rows = companies.map(c => `
      <tr>
        <td><a class="company-link" href="#/companies/${c.id}">${esc(c.name)}</a></td>
        <td>${esc(c.tax_id)}</td>
        <td>${esc(c.phone || "-")}</td>
        <td>${esc(c.iban || "-")}</td>
        <td class="row-actions">
          <button class="secondary small" data-edit="${c.id}">Düzenle</button>
          <button class="secondary danger small" data-del="${c.id}">Sil</button>
        </td>
      </tr>
    `).join("");

    layout("#/companies", `
      <div class="card">
        <h2>Yeni Cari Hesap</h2>
        <form id="companyForm">
          <div class="grid">
            <div><label>Firma Adı *</label><input name="name" required></div>
            <div><label>Vergi No / TCKN *</label><input name="tax_id" required></div>
            <div><label>Vergi Dairesi</label><input name="tax_office"></div>
            <div><label>Telefon</label><input name="phone"></div>
            <div><label>E-posta</label><input name="email" type="email"></div>
            <div><label>IBAN</label><input name="iban" placeholder="TR.."></div>
          </div>
          <label>Adres</label><textarea name="address" rows="2"></textarea>
          <button class="primary" type="submit">Kaydet</button>
          <div class="error-msg" id="companyError"></div>
        </form>
      </div>
      <div class="card">
        <h2>Cari Hesap Listesi</h2>
        <div class="searchbar">
          <input id="searchInput" placeholder="Firma adı veya vergi no ile ara...">
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Firma</th><th>Vergi No</th><th>Telefon</th><th>IBAN</th><th></th></tr></thead>
            <tbody>${rows || `<tr><td colspan="5">Kayıtlı firma yok.</td></tr>`}</tbody>
          </table>
        </div>
      </div>
    `);

    document.getElementById("companyForm").onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const data = Object.fromEntries(fd.entries());
      try {
        await Api.createCompany(data);
        toast("Firma eklendi");
        renderCompanies();
      } catch (err) {
        document.getElementById("companyError").textContent = err.message;
      }
    };

    document.getElementById("searchInput").oninput = async (e) => {
      const q = e.target.value;
      const filtered = await Api.listCompanies(q);
      const tbody = document.querySelector("table tbody");
      tbody.innerHTML = filtered.map(c => `
        <tr>
          <td><a class="company-link" href="#/companies/${c.id}">${esc(c.name)}</a></td>
          <td>${esc(c.tax_id)}</td>
          <td>${esc(c.phone || "-")}</td>
          <td>${esc(c.iban || "-")}</td>
          <td></td>
        </tr>
      `).join("") || `<tr><td colspan="5">Sonuç yok.</td></tr>`;
    };

    root.querySelectorAll("[data-del]").forEach(btn => {
      btn.onclick = async () => {
        if (!confirm("Bu firmayı ve tüm kayıtlarını silmek istediğinize emin misiniz?")) return;
        await Api.deleteCompany(btn.dataset.del);
        renderCompanies();
      };
    });
    root.querySelectorAll("[data-edit]").forEach(btn => {
      btn.onclick = () => { window.location.hash = `#/companies/${btn.dataset.edit}`; };
    });
  }

  async function renderCompanyDetail(companyId) {
    layout("#/companies", `<div class="card">Yükleniyor...</div>`);
    const ledger = await Api.getLedger(companyId);
    const b = ledger.balance;

    const rowHtml = (rows) => rows.map(r => `
      <tr>
        <td>${fmtDate(r.date)}</td>
        <td><span class="badge ${r.row_type === "invoice" ? "" : "warn"}">${r.row_type === "invoice" ? "Fatura" : "Ödeme"}</span></td>
        <td>${esc(r.reference)}</td>
        <td>${esc(r.description || "-")}</td>
        <td class="num">${r.debit ? fmtMoney(r.debit) : ""}</td>
        <td class="num">${r.credit ? fmtMoney(r.credit) : ""}</td>
        <td class="num">${fmtMoney(r.running_balance)}</td>
        <td class="row-actions">
          <button class="secondary small" data-row-edit="${r.row_type}:${r.id}">Düzenle</button>
          <button class="secondary danger small" data-row-del="${r.row_type}:${r.id}">Sil</button>
        </td>
      </tr>
    `).join("");

    layout("#/companies", `
      <button class="secondary" onclick="window.location.hash='#/companies'">&larr; Cari Hesaplara Dön</button>
      <div class="card">
        <h2>${esc(ledger.company.name)}</h2>
        <div class="hint">Vergi No: ${esc(ledger.company.tax_id)} ${ledger.company.iban ? `| IBAN: ${esc(ledger.company.iban)}` : ""}</div>
        <div class="grid" style="margin-top:12px">
          <div class="stat"><div class="label">Net Müşteri Borcu (Bize)</div><div class="value pos">${fmtDebtCredit(b.net_customer_debt, "Müşterinin Alacağı")}</div></div>
          <div class="stat"><div class="label">Net Firma Borcu (Bizden)</div><div class="value neg">${fmtDebtCredit(b.net_company_debt, "Bizim Alacağımız")}</div></div>
          <div class="stat"><div class="label">Genel Net Bakiye</div><div class="value ${b.net_balance >= 0 ? "pos" : "neg"}">${fmtNetBalance(b.net_balance)}</div></div>
        </div>
        <button class="primary" id="exportBtn">Excel Olarak Dışa Aktar</button>
        <button class="secondary" id="exportPdfBtn" style="margin-left:8px">PDF Olarak Dışa Aktar</button>
      </div>

      <div class="card">
        <h2>Müşteri Hesabı (Satış Faturaları / Tahsilatlar)</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Tarih</th><th>Tür</th><th>Referans</th><th>Açıklama</th><th class="num">Borç</th><th class="num">Yapılan Ödeme</th><th class="num">Bakiye</th><th></th></tr></thead>
            <tbody>${rowHtml(ledger.receivable_rows) || `<tr><td colspan="8">Kayıt yok.</td></tr>`}</tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <h2>Tedarikçi Hesabı (Alış Faturaları / Ödemeler)</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Tarih</th><th>Tür</th><th>Referans</th><th>Açıklama</th><th class="num">Borç</th><th class="num">Yapılan Ödeme</th><th class="num">Bakiye</th><th></th></tr></thead>
            <tbody>${rowHtml(ledger.payable_rows) || `<tr><td colspan="8">Kayıt yok.</td></tr>`}</tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <h2>Fatura Ekle</h2>
        <p class="hint">Toplu Excel listesinde olmayan tekil faturalar için (ör. e-Arşiv/e-Fatura) - tutar KDV dahil toplam olmalı.</p>
        <form id="invoiceForm">
          <div class="grid">
            <div><label>Yön</label>
              <select name="direction">
                <option value="outgoing">Giden Fatura (Satış - Müşteriye kestiğimiz)</option>
                <option value="incoming">Gelen Fatura (Alış - Bize kesilen)</option>
              </select>
            </div>
            <div><label>Fatura No *</label><input name="invoice_number" required></div>
            <div><label>Tarih *</label><input name="issue_date" type="date" required></div>
            <div><label>Tutar (KDV Dahil) *</label><input name="amount" type="number" step="0.01" required></div>
            <div><label>KDV Tutarı</label><input name="tax_amount" type="number" step="0.01"></div>
            <div><label>ETTN</label><input name="ettn"></div>
          </div>
          <label>Açıklama</label><input name="description">
          <button class="primary" type="submit">Fatura Ekle</button>
        </form>
      </div>

      <div class="card">
        <h2>Manuel Ödeme / Tahsilat Ekle</h2>
        <form id="txForm">
          <div class="grid">
            <div><label>Yön</label>
              <select name="direction">
                <option value="inflow">Tahsilat (Müşteriden bize)</option>
                <option value="outflow">Ödeme (Bizden tedarikçiye)</option>
              </select>
            </div>
            <div><label>Tarih *</label><input name="transaction_date" type="date" required></div>
            <div><label>Tutar *</label><input name="amount" type="number" step="0.01" required></div>
            <div><label>Karşı Taraf</label><input name="counterparty_name"></div>
          </div>
          <label>Açıklama</label><input name="description">
          <button class="primary" type="submit">Ekle</button>
        </form>
      </div>
    `);

    async function downloadExport(url, fallbackName) {
      try {
        const res = await fetch(url, {
          headers: { Authorization: `Bearer ${Api.getToken()}` },
        });
        if (!res.ok) throw new Error("Dışa aktarma başarısız");
        const blob = await res.blob();
        const disposition = res.headers.get("Content-Disposition") || "";
        const match = disposition.match(/filename="?([^"]+)"?/);
        const filename = match ? match[1] : fallbackName;
        const objUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = objUrl; a.download = filename;
        document.body.appendChild(a); a.click(); a.remove();
        URL.revokeObjectURL(objUrl);
      } catch (err) {
        toast(err.message);
      }
    }

    document.getElementById("exportBtn").onclick = () =>
      downloadExport(Api.exportLedgerUrl(companyId), `${ledger.company.name}_cari_hesap.xlsx`);
    document.getElementById("exportPdfBtn").onclick = () =>
      downloadExport(Api.exportLedgerPdfUrl(companyId), `${ledger.company.name}_cari_hesap.pdf`);

    document.getElementById("invoiceForm").onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const data = Object.fromEntries(fd.entries());
      data.company_id = Number(companyId);
      data.amount = Number(data.amount);
      data.tax_amount = data.tax_amount ? Number(data.tax_amount) : null;
      if (!data.ettn) delete data.ettn;
      try {
        await Api.createInvoice(data);
        toast("Fatura eklendi");
        renderCompanyDetail(companyId);
      } catch (err) {
        toast(err.message);
      }
    };

    document.getElementById("txForm").onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const data = Object.fromEntries(fd.entries());
      data.company_id = Number(companyId);
      data.amount = Number(data.amount);
      try {
        await Api.createTransaction(data);
        toast("İşlem eklendi");
        renderCompanyDetail(companyId);
      } catch (err) {
        toast(err.message);
      }
    };

    const rowsById = {};
    [...ledger.receivable_rows, ...ledger.payable_rows].forEach(r => {
      rowsById[`${r.row_type}:${r.id}`] = r;
    });

    root.querySelectorAll("[data-row-del]").forEach(btn => {
      btn.onclick = async () => {
        const [type, id] = btn.dataset.rowDel.split(":");
        if (!confirm(`Bu ${type === "invoice" ? "faturayı" : "ödemeyi"} silmek istediğinize emin misiniz?`)) return;
        try {
          if (type === "invoice") await Api.deleteInvoice(id);
          else await Api.deleteTransaction(id);
          toast("Silindi");
          renderCompanyDetail(companyId);
        } catch (err) {
          toast(err.message);
        }
      };
    });

    root.querySelectorAll("[data-row-edit]").forEach(btn => {
      btn.onclick = () => {
        const [type, id] = btn.dataset.rowEdit.split(":");
        const row = rowsById[`${type}:${id}`];
        openEditRowModal({
          rowType: type,
          initial: {
            date: row.date,
            amount: type === "invoice" ? row.debit : row.credit,
            description: row.description,
            reference: row.reference,
          },
          onSave: async (data) => {
            if (type === "invoice") {
              await Api.updateInvoice(id, {
                invoice_number: data.invoice_number,
                issue_date: data.date,
                amount: data.amount,
                description: data.description,
              });
            } else {
              await Api.updateTransaction(id, {
                transaction_date: data.date,
                amount: data.amount,
                description: data.description,
              });
            }
            toast("Güncellendi");
            renderCompanyDetail(companyId);
          },
        });
      };
    });
  }

  async function renderUploads() {
    layout("#/uploads", `
      <div class="card">
        <h2>Kolaysoft Fatura Excel Yükle</h2>
        <p class="hint">Giden (satış) veya gelen (alış) fatura listesi Excel dosyasını seçin. Firma ve fatura kayıtları otomatik oluşturulur/güncellenir.</p>
        <form id="excelForm">
          <label>Fatura Yönü</label>
          <select name="direction">
            <option value="outgoing">Giden Fatura (Satış - Müşteriye kestiğimiz)</option>
            <option value="incoming">Gelen Fatura (Alış - Bize kesilen)</option>
          </select>
          <label>Excel Dosyası (.xlsx)</label>
          <input type="file" name="file" accept=".xlsx,.xls" required>
          <button class="primary" type="submit">Yükle ve İşle</button>
        </form>
        <div id="excelResult"></div>
      </div>

      <div class="card">
        <h2>Banka Dekontu (PDF) Yükle</h2>
        <p class="hint">Havale/EFT dekontu PDF'i yükleyin; tutar, tarih ve IBAN otomatik çıkarılır. Ardından "Dekontlar" sayfasından hangi firmaya ait olduğunu onaylayın.</p>
        <form id="pdfForm">
          <label>Dekont PDF</label>
          <input type="file" name="file" accept=".pdf" required>
          <button class="primary" type="submit">Yükle ve Ayrıştır</button>
        </form>
        <div id="pdfResult"></div>
      </div>
    `);

    document.getElementById("excelForm").onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const file = fd.get("file");
      const direction = fd.get("direction");
      const resultEl = document.getElementById("excelResult");
      resultEl.innerHTML = "Yükleniyor...";
      try {
        const result = await Api.uploadInvoiceExcel(direction, file);
        resultEl.innerHTML = `
          <div class="card" style="background:#f7faf7">
            <strong>${esc(result.filename)}</strong> işlendi: ${result.rows_read} satır okundu,
            ${result.invoices_created} fatura eklendi, ${result.invoices_skipped_duplicate} mükerrer atlandı,
            ${result.companies_created} yeni firma oluşturuldu.
            ${result.errors.length ? `<div class="error-msg">${result.errors.map(esc).join("<br>")}</div>` : ""}
          </div>`;
      } catch (err) {
        resultEl.innerHTML = `<div class="error-msg">${esc(err.message)}</div>`;
      }
    };

    document.getElementById("pdfForm").onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(e.target);
      const file = fd.get("file");
      const resultEl = document.getElementById("pdfResult");
      resultEl.innerHTML = "Yükleniyor ve ayrıştırılıyor...";
      try {
        const receipt = await Api.uploadReceiptPdf(file);
        resultEl.innerHTML = `
          <div class="card" style="background:#f7faf7">
            Dekont yüklendi (${receipt.ocr_used ? "OCR ile" : "metin katmanından"} okundu).<br>
            Tutar: ${receipt.parsed_amount ? fmtMoney(receipt.parsed_amount) + " " + (receipt.parsed_currency || "") : "bulunamadı"} |
            Tarih: ${fmtDate(receipt.parsed_date)}<br>
            Devam etmek için <a class="company-link" href="#/receipts">Dekontlar</a> sayfasından firmayı onaylayın.
          </div>`;
      } catch (err) {
        resultEl.innerHTML = `<div class="error-msg">${esc(err.message)}</div>`;
      }
    };
  }

  async function renderReceipts() {
    layout("#/receipts", `<div class="card">Yükleniyor...</div>`);
    const [receipts, companies] = await Promise.all([Api.listReceipts(), Api.listCompanies()]);

    const companyOptions = companies.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join("");

    const rows = receipts.map(r => `
      <tr>
        <td>${esc(r.filename)}</td>
        <td>${fmtDate(r.parsed_date)}</td>
        <td class="num">${r.parsed_amount ? fmtMoney(r.parsed_amount) : "-"} ${esc(r.parsed_currency || "")}</td>
        <td>${esc(r.sender_name || "-")}</td>
        <td>${esc(r.receiver_name || "-")}</td>
        <td>${r.transaction_id ? `<span class="badge">Eşleşti</span>` : `<span class="badge warn">Bekliyor</span>`}</td>
        <td>
          ${r.transaction_id ? "-" : `
          <form class="confirmForm" data-id="${r.id}" style="display:flex; gap:4px; flex-wrap:wrap; align-items:center">
            <select name="company_id" required><option value="">Firma seç...</option>${companyOptions}</select>
            <select name="direction">
              <option value="inflow">Tahsilat</option>
              <option value="outflow">Ödeme</option>
            </select>
            <input name="amount" type="number" step="0.01" placeholder="Tutar" value="${r.parsed_amount ?? ""}" style="width:100px">
            <button class="secondary small" type="submit">Onayla</button>
          </form>`}
        </td>
      </tr>
    `).join("");

    layout("#/receipts", `
      <div class="card">
        <h2>Yüklenen Banka Dekontları</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Dosya</th><th>Tarih</th><th class="num">Tutar</th><th>Gönderen</th><th>Alıcı</th><th>Durum</th><th>İşlem</th></tr></thead>
            <tbody>${rows || `<tr><td colspan="7">Henüz dekont yüklenmedi.</td></tr>`}</tbody>
          </table>
        </div>
      </div>
    `);

    root.querySelectorAll(".confirmForm").forEach(form => {
      form.onsubmit = async (e) => {
        e.preventDefault();
        const fd = new FormData(form);
        const data = {
          company_id: Number(fd.get("company_id")),
          direction: fd.get("direction"),
          amount: fd.get("amount") ? Number(fd.get("amount")) : null,
        };
        try {
          await Api.confirmReceipt(form.dataset.id, data);
          toast("Dekont onaylandı ve işlem oluşturuldu");
          renderReceipts();
        } catch (err) {
          toast(err.message);
        }
      };
    });
  }

  // ---------- Router ----------

  async function route() {
    const hash = window.location.hash || "#/dashboard";
    if (!Api.getToken() && hash !== "#/login") {
      window.location.hash = "#/login";
      return;
    }
    if (Api.getToken() && !currentUser) {
      try { currentUser = await Api.me(); } catch (_) { return; }
    }

    try {
      if (hash === "#/login") return renderLogin();
      if (hash === "#/dashboard") return await renderDashboard();
      if (hash === "#/companies") return await renderCompanies();
      if (hash === "#/uploads") return await renderUploads();
      if (hash === "#/receipts") return await renderReceipts();
      const companyMatch = hash.match(/^#\/companies\/(\d+)$/);
      if (companyMatch) return await renderCompanyDetail(companyMatch[1]);
      window.location.hash = "#/dashboard";
    } catch (err) {
      root.innerHTML = `<div class="container"><div class="card error-msg">Hata: ${esc(err.message)}</div></div>`;
    }
  }

  window.addEventListener("hashchange", route);
  window.addEventListener("DOMContentLoaded", route);

  return { route };
})();
