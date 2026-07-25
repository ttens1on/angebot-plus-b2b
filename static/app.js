// ============================================================================
// AngebotPlus B2B — client-side logic: dynamic items, live preview, API calls
// ============================================================================

const UNIT_OPTIONS = [
  { value: "Std", label: "Std." },
  { value: "Pauschal", label: "Pauschal" },
  { value: "m2", label: "m²" },
  { value: "Stk", label: "Stk." },
];

const DRAFT_KEY = "angebotplus_draft";

const els = {
  form: document.getElementById("offer-form"),
  itemsContainer: document.getElementById("items-container"),
  btnAddItem: document.getElementById("btn-add-item"),
  btnGenerate: document.getElementById("btn-generate"),
  btnDraft: document.getElementById("btn-draft"),
  offerNumber: document.getElementById("offer_number"),
  offerDate: document.getElementById("offer_date"),
  validityDays: document.getElementById("validity_days"),
  vatRate: document.getElementById("vat_rate"),
  discountPercent: document.getElementById("discount_percent"),
  toast: document.getElementById("toast"),
  historyModal: document.getElementById("history-modal"),
  btnHistory: document.getElementById("btn-history"),
  btnCloseHistory: document.getElementById("btn-close-history"),
  historyList: document.getElementById("history-list"),
  historyEmpty: document.getElementById("history-empty"),
  tabForm: document.getElementById("tab-form"),
  tabPreview: document.getElementById("tab-preview"),
  panelForm: document.getElementById("panel-form"),
  panelPreview: document.getElementById("panel-preview"),
};

// ------------------------------- Formatting -------------------------------
const eurFmt = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" });
const numFmt = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 2 });

function fmtEUR(v) {
  return eurFmt.format(Number.isFinite(v) ? v : 0);
}
function fmtQty(v) {
  return numFmt.format(Number.isFinite(v) ? v : 0);
}
function fmtDateDE(iso) {
  if (!iso) return "–";
  const d = new Date(`${iso}T00:00:00`);
  if (isNaN(d)) return "–";
  return d.toLocaleDateString("de-DE");
}
function validUntilDE(iso, days) {
  if (!iso) return "–";
  const d = new Date(`${iso}T00:00:00`);
  if (isNaN(d)) return "–";
  d.setDate(d.getDate() + (parseInt(days, 10) || 0));
  return d.toLocaleDateString("de-DE");
}
function unitLabel(value) {
  return (UNIT_OPTIONS.find((u) => u.value === value) || {}).label || value;
}

// ------------------------------- Toast -------------------------------
let toastTimer = null;
function showToast(message, type = "default") {
  clearTimeout(toastTimer);
  els.toast.textContent = message;
  els.toast.className = "toast";
  if (type === "success") els.toast.classList.add("toast-success");
  if (type === "error") els.toast.classList.add("toast-error");
  els.toast.classList.remove("hidden");
  toastTimer = setTimeout(() => els.toast.classList.add("hidden"), 3200);
}

// ------------------------------- Line items -------------------------------
function makeItemRow(item = { description: "", quantity: 1, unit: "Stk", unit_price: 0 }) {
  const row = document.createElement("div");
  row.className = "item-row";
  row.innerHTML = `
    <input class="ir-desc" type="text" placeholder="z. B. Montage Steckdose" value="${escapeAttr(item.description)}" />
    <input class="ir-qty" type="number" min="0" step="0.5" value="${item.quantity}" />
    <select class="ir-unit">
      ${UNIT_OPTIONS.map((u) => `<option value="${u.value}" ${u.value === item.unit ? "selected" : ""}>${u.label}</option>`).join("")}
    </select>
    <input class="ir-price" type="number" min="0" step="0.01" value="${item.unit_price}" />
    <div class="ir-total-value">${fmtEUR(item.quantity * item.unit_price)}</div>
    <button type="button" class="ir-del-btn" title="Position entfernen">
      <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
    </button>
  `;
  row.querySelectorAll("input, select").forEach((el) => {
    el.addEventListener("input", () => {
      updateRowTotal(row);
      renderPreview();
    });
  });
  row.querySelector(".ir-del-btn").addEventListener("click", () => {
    if (els.itemsContainer.children.length <= 1) {
      showToast("Mindestens eine Position ist erforderlich.", "error");
      return;
    }
    row.remove();
    renderPreview();
  });
  return row;
}

function updateRowTotal(row) {
  const qty = parseFloat(row.querySelector(".ir-qty").value) || 0;
  const price = parseFloat(row.querySelector(".ir-price").value) || 0;
  row.querySelector(".ir-total-value").textContent = fmtEUR(qty * price);
}

function addItem(item) {
  const row = makeItemRow(item);
  els.itemsContainer.appendChild(row);
}

function escapeAttr(str) {
  return String(str ?? "").replace(/"/g, "&quot;");
}
function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = String(str ?? "");
  return div.innerHTML;
}

function readItems() {
  return Array.from(els.itemsContainer.querySelectorAll(".item-row")).map((row) => ({
    description: row.querySelector(".ir-desc").value.trim() || "Position",
    quantity: parseFloat(row.querySelector(".ir-qty").value) || 0,
    unit: row.querySelector(".ir-unit").value,
    unit_price: parseFloat(row.querySelector(".ir-price").value) || 0,
  }));
}

// ------------------------------- Calculation (mirrors backend) -------------------------------
function calcTotals(items, discountPercent, vatRate) {
  const subtotal_net = items.reduce((s, i) => s + i.quantity * i.unit_price, 0);
  const discount_amount = subtotal_net * (discountPercent / 100);
  const net_after_discount = subtotal_net - discount_amount;
  const vat_amount = net_after_discount * (vatRate / 100);
  const gross_total = net_after_discount + vat_amount;
  return { subtotal_net, discount_amount, net_after_discount, vat_amount, gross_total };
}

// ------------------------------- Form <-> data -------------------------------
function collectFormData() {
  const fd = new FormData(els.form);
  return {
    offer_number: els.offerNumber.value.trim(),
    offer_date: els.offerDate.value,
    validity_days: parseInt(els.validityDays.value, 10) || 30,
    provider: {
      name: fd.get("provider_name")?.trim() || "",
      address: fd.get("provider_address")?.trim() || "",
      tax_id: fd.get("provider_tax_id")?.trim() || "",
      iban: fd.get("provider_iban")?.trim() || "",
      email: fd.get("provider_email")?.trim() || "",
    },
    client: {
      name: fd.get("client_name")?.trim() || "",
      company: fd.get("client_company")?.trim() || "",
      address: fd.get("client_address")?.trim() || "",
    },
    items: readItems(),
    vat_rate: parseFloat(els.vatRate.value),
    discount_percent: parseFloat(els.discountPercent.value) || 0,
  };
}

function populateForm(data) {
  els.form.querySelector('[name="provider_name"]').value = data.provider?.name || "";
  els.form.querySelector('[name="provider_address"]').value = data.provider?.address || "";
  els.form.querySelector('[name="provider_tax_id"]').value = data.provider?.tax_id || "";
  els.form.querySelector('[name="provider_iban"]').value = data.provider?.iban || "";
  els.form.querySelector('[name="provider_email"]').value = data.provider?.email || "";
  els.form.querySelector('[name="client_name"]').value = data.client?.name || "";
  els.form.querySelector('[name="client_company"]').value = data.client?.company || "";
  els.form.querySelector('[name="client_address"]').value = data.client?.address || "";
  els.offerNumber.value = data.offer_number || "";
  els.offerDate.value = data.offer_date || "";
  els.validityDays.value = data.validity_days || 30;
  els.vatRate.value = String(data.vat_rate ?? 19);
  els.discountPercent.value = data.discount_percent ?? 0;

  els.itemsContainer.innerHTML = "";
  (data.items && data.items.length ? data.items : [{ description: "", quantity: 1, unit: "Stk", unit_price: 0 }]).forEach(addItem);
  renderPreview();
}

// ------------------------------- Live preview render -------------------------------
function renderPreview() {
  const data = collectFormData();
  const totals = calcTotals(data.items, data.discount_percent, data.vat_rate);

  const providerAddrOneLine = (data.provider.address || "").split("\n").filter(Boolean).join(", ");
  document.getElementById("pv-sender").textContent = data.provider.name
    ? `${data.provider.name} · ${providerAddrOneLine}`
    : "";

  document.getElementById("pv-offer-number").textContent = data.offer_number || "–";
  document.getElementById("pv-offer-date").textContent = fmtDateDE(data.offer_date);
  const validUntil = validUntilDE(data.offer_date, data.validity_days);
  document.getElementById("pv-valid-until").textContent = validUntil;
  document.getElementById("pv-valid-until-2").textContent = validUntil;

  const clientLines = [data.client.name, data.client.company, ...(data.client.address || "").split("\n")].filter(Boolean);
  document.getElementById("pv-client").innerHTML = clientLines.map(escapeHtml).join("<br/>") || "&nbsp;";

  const itemsBody = document.getElementById("pv-items");
  itemsBody.innerHTML = data.items
    .map((item, idx) => {
      const lineTotal = item.quantity * item.unit_price;
      return `<tr>
        <td class="al-c">${idx + 1}</td>
        <td>${escapeHtml(item.description) || "&nbsp;"}</td>
        <td class="al-r">${fmtQty(item.quantity)}</td>
        <td class="al-r">${unitLabel(item.unit)}</td>
        <td class="al-r">${fmtEUR(item.unit_price)}</td>
        <td class="al-r">${fmtEUR(lineTotal)}</td>
      </tr>`;
    })
    .join("");

  const totalsBody = document.getElementById("pv-totals");
  let rowsHtml = `<tr><td>Nettobetrag</td><td class="al-r">${fmtEUR(totals.subtotal_net)}</td></tr>`;
  if (data.discount_percent) {
    rowsHtml += `<tr><td>Rabatt (${data.discount_percent}%)</td><td class="al-r">− ${fmtEUR(totals.discount_amount)}</td></tr>`;
    rowsHtml += `<tr><td>Zwischensumme</td><td class="al-r">${fmtEUR(totals.net_after_discount)}</td></tr>`;
  }
  if (data.vat_rate > 0) {
    rowsHtml += `<tr><td>zzgl. MwSt. (${data.vat_rate}%)</td><td class="al-r">${fmtEUR(totals.vat_amount)}</td></tr>`;
  } else {
    rowsHtml += `<tr><td>Umsatzsteuer</td><td class="al-r">${fmtEUR(0)}</td></tr>`;
  }
  rowsHtml += `<tr class="total-row"><td>Gesamtbetrag brutto</td><td class="al-r">${fmtEUR(totals.gross_total)}</td></tr>`;
  totalsBody.innerHTML = rowsHtml;

  document.getElementById("pv-note").textContent =
    data.vat_rate === 0 ? "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet (Kleinunternehmerregelung)." : "";

  document.getElementById("pv-footer-name").textContent = data.provider.name || "";
  document.getElementById("pv-footer-line").textContent =
    `USt-IdNr./Steuernr.: ${data.provider.tax_id || "–"}    IBAN: ${data.provider.iban || "–"}    E-Mail: ${data.provider.email || "–"}`;
}

// ------------------------------- API calls -------------------------------
async function fetchNextOfferNumber() {
  const res = await fetch("/api/offers/next-number");
  const data = await res.json();
  els.offerNumber.value = data.offer_number;
}

async function submitOffer(e) {
  e.preventDefault();
  const data = collectFormData();

  if (!data.provider.name || !data.client.name || !data.client.address) {
    showToast("Bitte alle Pflichtfelder ausfüllen.", "error");
    return;
  }
  if (!data.items.length || data.items.every((i) => !i.description)) {
    showToast("Bitte mindestens eine Position mit Beschreibung angeben.", "error");
    return;
  }

  els.btnGenerate.disabled = true;
  els.btnGenerate.classList.add("opacity-60");
  try {
    const res = await fetch("/api/offers/generate-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "PDF konnte nicht erstellt werden.");
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${data.offer_number}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    showToast("Angebot gespeichert & PDF heruntergeladen.", "success");
    localStorage.removeItem(DRAFT_KEY);
    await fetchNextOfferNumber();
  } catch (err) {
    showToast(err.message || "Fehler beim Erstellen des Angebots.", "error");
  } finally {
    els.btnGenerate.disabled = false;
    els.btnGenerate.classList.remove("opacity-60");
  }
}

function saveDraft() {
  const data = collectFormData();
  localStorage.setItem(DRAFT_KEY, JSON.stringify(data));
  showToast("Entwurf lokal gespeichert.", "success");
}

function loadDraftIfPresent() {
  const raw = localStorage.getItem(DRAFT_KEY);
  if (!raw) return false;
  try {
    const data = JSON.parse(raw);
    populateForm(data);
    return true;
  } catch {
    return false;
  }
}

// ------------------------------- History modal -------------------------------
async function openHistory() {
  els.historyModal.classList.remove("hidden");
  els.historyList.innerHTML = "";
  els.historyEmpty.classList.add("hidden");
  try {
    const res = await fetch("/api/offers");
    const offers = await res.json();
    if (!offers.length) {
      els.historyEmpty.classList.remove("hidden");
      return;
    }
    els.historyList.innerHTML = offers
      .map(
        (o) => `
      <div class="history-row" data-id="${o.id}">
        <div>
          <div class="history-number">${escapeHtml(o.offer_number)}</div>
          <div class="history-meta">${escapeHtml(o.client_company || o.client_name)} · ${fmtDateDE(o.offer_date)} · ${fmtEUR(o.gross_total)}</div>
        </div>
        <div class="history-actions">
          <button class="history-btn" data-action="load" data-id="${o.id}">Laden</button>
          <button class="history-btn primary" data-action="pdf" data-id="${o.id}">PDF</button>
          <button class="history-btn danger" data-action="delete" data-id="${o.id}">Löschen</button>
        </div>
      </div>`
      )
      .join("");
  } catch {
    showToast("Historie konnte nicht geladen werden.", "error");
  }
}

function closeHistory() {
  els.historyModal.classList.add("hidden");
}

els.historyList?.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const id = btn.dataset.id;
  const action = btn.dataset.action;

  if (action === "pdf") {
    window.open(`/api/offers/${id}/pdf`, "_blank");
    return;
  }
  if (action === "load") {
    try {
      const res = await fetch(`/api/offers/${id}`);
      if (!res.ok) throw new Error();
      const offer = await res.json();
      populateForm(offer);
      closeHistory();
      showToast(`Angebot ${offer.offer_number} geladen.`, "success");
    } catch {
      showToast("Angebot konnte nicht geladen werden.", "error");
    }
    return;
  }
  if (action === "delete") {
    if (!confirm("Dieses Angebot wirklich löschen?")) return;
    try {
      const res = await fetch(`/api/offers/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error();
      showToast("Angebot gelöscht.", "success");
      openHistory();
    } catch {
      showToast("Löschen fehlgeschlagen.", "error");
    }
  }
});

// ------------------------------- Mobile tabs -------------------------------
function setMobileTab(tab) {
  const isForm = tab === "form";
  els.panelForm.classList.toggle("mobile-hide", !isForm);
  els.panelPreview.classList.toggle("mobile-show", !isForm);
  els.tabForm.classList.toggle("border-navy", isForm);
  els.tabForm.classList.toggle("text-navy", isForm);
  els.tabForm.classList.toggle("border-transparent", !isForm);
  els.tabForm.classList.toggle("text-slate-400", !isForm);
  els.tabPreview.classList.toggle("border-navy", !isForm);
  els.tabPreview.classList.toggle("text-navy", !isForm);
  els.tabPreview.classList.toggle("border-transparent", isForm);
  els.tabPreview.classList.toggle("text-slate-400", isForm);
}

// ------------------------------- Wiring -------------------------------
els.form.addEventListener("input", renderPreview);
els.form.addEventListener("submit", submitOffer);
els.btnAddItem.addEventListener("click", () => {
  addItem();
  renderPreview();
});
els.btnDraft.addEventListener("click", saveDraft);
els.btnHistory.addEventListener("click", openHistory);
els.btnCloseHistory.addEventListener("click", closeHistory);
els.historyModal.addEventListener("click", (e) => {
  if (e.target === els.historyModal) closeHistory();
});
els.tabForm?.addEventListener("click", () => setMobileTab("form"));
els.tabPreview?.addEventListener("click", () => setMobileTab("preview"));

// ------------------------------- Init -------------------------------
(async function init() {
  els.offerDate.value = new Date().toISOString().slice(0, 10);
  const restored = loadDraftIfPresent();
  if (!restored) {
    addItem({ description: "Beispielleistung", quantity: 1, unit: "Std", unit_price: 65 });
    await fetchNextOfferNumber();
  }
  renderPreview();
})();
