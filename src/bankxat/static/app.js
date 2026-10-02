const state = { dashboard: null, files: [], results: [], review: [], aiStatus: null };

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / (1024 ** index)).toFixed(index ? 1 : 0)} ${units[index]}`;
}

function escapeHtml(value) {
  const node = document.createElement("div");
  node.textContent = value ?? "";
  return node.innerHTML;
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

function highlightEvidence(snippet, card) {
  const text = String(snippet || "Manba matni mavjud emas");
  const digits = String(card || "").replace(/\D/g, "");
  if (digits.length !== 16) return escapeHtml(text);
  const pattern = new RegExp(digits.split("").join("[\\s.\\-]*"));
  const match = pattern.exec(text);
  if (!match) return escapeHtml(text);
  return `${escapeHtml(text.slice(0, match.index))}<mark>${escapeHtml(match[0])}</mark>${escapeHtml(text.slice(match.index + match[0].length))}`;
}

function formatCard(card) {
  const digits = String(card || "").replace(/\D/g, "");
  return digits.length === 16 ? digits.replace(/(.{4})/g, "$1 ").trim() : String(card || "—");
}

function sourceLabel(source) {
  const value = String(source || "");
  if (value.startsWith("ocr")) return "Rasmdan o‘qildi";
  if (value.startsWith("docx")) return "Word hujjatidan";
  if (value === "text_layer") return "Hujjat matnidan";
  if (value === "text") return "Matn faylidan";
  return "Hujjatdan olindi";
}

function roleMethodLabel(card) {
  const source = String(card.role_source || "");
  if (source === "hybrid_consensus") return "Matn dalili va AI bir xil xulosaga keldi";
  if (source === "ai_assistant") return "AI xat mazmunidan dalil topdi";
  if (source === "context_rules") return "Xatdagi yo‘nalish iboralari orqali aniqlandi";
  if (source === "semantic_conflict") return "Tahlillar mos kelmadi — tekshirish kerak";
  if (source === "pair_order_fallback") return "Hujjat tartibi bo‘yicha taxmin — tekshirish kerak";
  return "Rolni aniqlash usuli mavjud emas";
}

function warningLabel(warning) {
  const value = String(warning || "").toLowerCase();
  if (value.includes("luhn")) return "Raqam karta formatiga mos kelmadi";
  if (value.includes("ocr") || value.includes("konsensus") || value.includes("ishonch")) return "Raqamni hujjat bilan solishtirib tekshiring";
  if (value.includes("rol") || value.includes("recipient") || value.includes("sender")) return "Kartaning kimga tegishli ekanini aniqlab bo‘lmadi";
  return "Natijani hujjat bilan solishtirib tekshiring";
}

function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.classList.add("show");
  window.setTimeout(() => element.classList.remove("show"), 2600);
}

async function api(path, options = {}) {
  const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || "So‘rov bajarilmadi");
  return body;
}

let selectedEntries = [];

function renderSelectedFiles() {
  const container = $("#selected-files");
  const scanButton = $("#start-scan");
  const clearButton = $("#clear-selection");
  const hint = $("#scan-button-hint");
  if (!selectedEntries.length) {
    container.hidden = true;
    clearButton.hidden = true;
    scanButton.disabled = true;
    hint.textContent = "Avval hujjat tanlang";
    container.innerHTML = "";
    return;
  }
  const total = selectedEntries.reduce((sum, entry) => sum + entry.file.size, 0);
  const preview = selectedEntries.slice(0, 3).map((entry) => `<div class="file-preview">${escapeHtml(entry.path)} · ${formatBytes(entry.file.size)}</div>`).join("");
  const extra = selectedEntries.length > 3 ? `<div>yana ${selectedEntries.length - 3} ta fayl</div>` : "";
  container.innerHTML = `<strong>Tanlandi: ${selectedEntries.length} ta fayl · ${formatBytes(total)}</strong>${preview}${extra}`;
  container.hidden = false;
  clearButton.hidden = false;
  scanButton.disabled = false;
  hint.textContent = `${selectedEntries.length} ta faylni qayta ishlash`;
}

function addUploadFiles(files, preserveFolders = false) {
  const incoming = [...files].map((file) => ({
    file,
    path: preserveFolders && file.webkitRelativePath ? file.webkitRelativePath : file.name,
  }));
  addEntries(incoming);
}

function addEntries(incoming) {
  const entries = new Map(selectedEntries.map((entry) => [`${entry.path}:${entry.file.size}:${entry.file.lastModified}`, entry]));
  incoming.forEach((entry) => entries.set(`${entry.path}:${entry.file.size}:${entry.file.lastModified}`, entry));
  selectedEntries = [...entries.values()];
  renderSelectedFiles();
}

function readFileEntry(entry, prefix = "") {
  return new Promise((resolve, reject) => {
    entry.file((file) => resolve([{ file, path: `${prefix}${file.name}` }]), reject);
  });
}

async function readDirectoryEntry(entry, prefix = "") {
  const directoryPrefix = `${prefix}${entry.name}/`;
  const reader = entry.createReader();
  const children = [];
  while (true) {
    const batch = await new Promise((resolve, reject) => reader.readEntries(resolve, reject));
    if (!batch.length) break;
    children.push(...batch);
  }
  const nested = await Promise.all(children.map((child) => (
    child.isDirectory ? readDirectoryEntry(child, directoryPrefix) : readFileEntry(child, directoryPrefix)
  )));
  return nested.flat();
}

async function entriesFromDrop(dataTransfer) {
  const items = [...dataTransfer.items];
  const entries = items.map((item) => item.webkitGetAsEntry?.()).filter(Boolean);
  if (!entries.length) {
    return [...dataTransfer.files].map((file) => ({ file, path: file.name }));
  }
  const nested = await Promise.all(entries.map((entry) => (
    entry.isDirectory ? readDirectoryEntry(entry) : readFileEntry(entry)
  )));
  return nested.flat();
}

function clearSelection() {
  selectedEntries = [];
  $("#file-input").value = "";
  $("#folder-input").value = "";
  $("#intake-message").textContent = "";
  renderSelectedFiles();
}

function showView(viewName) {
  $$(".view").forEach((view) => view.classList.toggle("active-view", view.id === viewName));
  $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === viewName));
  const titles = { overview: "Umumiy holat", files: "Hujjatlar", review: "Tekshiruv navbati", about: "Loyiha haqida", system: "Tizim holati" };
  $("#page-title").textContent = titles[viewName];
  $(".sidebar").classList.remove("open");
  if (viewName === "system") loadTools();
}

function renderFiles(files) {
  const full = $("#all-files");
  if (!files.length) {
    full.innerHTML = '<div class="empty large"><span>▤</span><strong>Hujjatlar topilmadi</strong><p>Umumiy holat sahifasidan fayl, arxiv yoki papka tanlang.</p></div>';
    return;
  }
  const rows = files.map((file) => `
    <div class="file-row">
      <div class="file-name"><strong title="${escapeAttribute(file.relative_path)}">${escapeHtml(file.relative_path)}</strong><small>${file.sha256.slice(0, 12)}…</small></div>
      <small>${formatBytes(file.size_bytes)}</small>
      <span class="status">${file.duplicate_of ? "TAKRORIY" : "TOPILDI"}</span>
    </div>`).join("");
  full.innerHTML = rows;
}

function renderResults(results) {
  const container = $("#recent-results");
  const query = $("#result-search").value.trim().toLowerCase();
  const roleFilter = $("#role-filter").value;
  const sourceFilter = $("#source-filter").value;
  const sortMode = $("#sort-filter").value;
  const reviewOnly = $("#review-filter").checked;
  const filtered = results.map((file) => ({
    ...file,
    cards: file.cards.filter((card) => {
      const searchTarget = `${file.relative_path} ${card.card}`.toLowerCase();
      const isOcr = String(card.source || "").startsWith("ocr");
      return (!query || searchTarget.includes(query))
        && (roleFilter === "ALL" || card.role === roleFilter)
        && (sourceFilter === "ALL" || (sourceFilter === "OCR" ? isOcr : !isOcr))
        && (!reviewOnly || card.needs_review);
    }),
  })).filter((file) => file.cards.length);
  filtered.forEach((file) => {
    if (sortMode === "CARD_ASC") file.cards.sort((a, b) => a.card.localeCompare(b.card));
    if (sortMode === "ROLE") file.cards.sort((a, b) => a.role.localeCompare(b.role));
  });
  filtered.sort((a, b) => {
    const direction = sortMode === "FILE_DESC" ? -1 : 1;
    return direction * a.relative_path.localeCompare(b.relative_path, "uz");
  });
  const totalCards = results.reduce((total, file) => total + file.cards.length, 0);
  const aiAssisted = results.reduce(
    (total, file) => total + file.cards.filter((card) => card.ai_assisted).length,
    0,
  );
  const visibleCards = filtered.reduce((total, file) => total + file.cards.length, 0);
  $("#stat-cards").textContent = totalCards;
  $("#results-summary").textContent = `${visibleCards} ta karta · ${filtered.length} ta fayl${aiAssisted ? ` · ${aiAssisted} tasi AI yordamchida tekshirildi` : ""}`;
  if (!filtered.length) {
    container.innerHTML = totalCards
      ? '<div class="empty"><span>⌕</span><strong>Mos natija topilmadi</strong><p>Qidiruv yoki filtrlarni o‘zgartiring.</p></div>'
      : '<div class="empty"><span>▤</span><strong>Hali karta topilmadi</strong><p>Hujjat tanlab, skanerlashni boshlang.</p></div>';
    return;
  }
  const roleLabels = {
    SENDER: "Jo‘natuvchi",
    RECIPIENT: "Qabul qiluvchi",
    UNKNOWN: "Noma’lum",
  };
  container.innerHTML = filtered.map((file) => `
    <details class="file-result-group" open>
      <summary class="file-result-header">
        <span class="file-result-icon" aria-hidden="true">▤</span>
        <div class="file-result-title">
          <strong title="${escapeAttribute(file.relative_path)}">${escapeHtml(file.relative_path)}</strong>
          <small>${escapeHtml((file.file_type || "fayl").toUpperCase())}</small>
        </div>
        <span class="file-card-count">${file.cards.length} ta karta</span>
        <span class="disclosure" aria-hidden="true">⌄</span>
      </summary>
      <div class="file-cards">
        <div class="card-table-heading"><span>№</span><span>Karta va manba</span><span>Amallar</span></div>
        ${file.cards.map((card) => {
          const role = ["SENDER", "RECIPIENT"].includes(card.role) ? card.role : "UNKNOWN";
          const roleClass = role.toLowerCase();
          const positionLabel = card.position ? `#${card.position}` : "—";
          const positionDescription = card.position ? `${card.position}-karta` : "Tartib raqami mavjud emas";
          const page = card.page ? `${card.page}-sahifa` : "Sahifa noma’lum";
          const reviewLabel = card.needs_review ? '<span class="review-badge">Tekshirish kerak</span>' : "";
          const semanticLabel = card.ai_assisted ? '<span class="semantic-badge">Mazmun bo‘yicha tasdiqlandi</span>' : "";
          return `
            <article class="card-result" tabindex="0" aria-label="${escapeAttribute(`${positionDescription}, ${roleLabels[role]}, ${card.card}`)}" data-card="${escapeAttribute(card.card)}">
              <div class="card-position" aria-hidden="true">${positionLabel}</div>
              <div class="card-main">
                <div class="result-card-number">${escapeHtml(formatCard(card.card))}</div>
                <div class="card-badges">
                  <span class="role-badge ${roleClass}">${escapeHtml(roleLabels[role] || roleLabels.UNKNOWN)}</span>
                  ${semanticLabel}
                  ${reviewLabel}
                </div>
                <div class="result-meta">${escapeHtml(page)} · ${escapeHtml(sourceLabel(card.source))}</div>
              </div>
              <div class="card-actions">
                <button class="copy-card" type="button" data-copy-card="${escapeAttribute(card.card)}" aria-label="Karta raqamini nusxalash">Nusxalash</button>
                <button class="show-evidence" type="button" aria-label="Dalilni ochish">Dalil</button>
              </div>
              <div class="evidence-tooltip" role="tooltip">
                <strong>Manba · ${escapeHtml(page)}</strong>
                <p>${highlightEvidence(card.snippet, card.card)}</p>
                <small>${escapeHtml(roleMethodLabel(card))}</small>
              </div>
            </article>`;
        }).join("")}
      </div>
    </details>`).join("");
}

function renderReview(items) {
  const container = $("#review-list");
  $("#queue-count").textContent = `${items.length} ta`;
  if (!items.length) {
    container.innerHTML = '<div class="empty large"><span>◇</span><strong>Tekshiruv navbati bo‘sh</strong><p>Qo‘lda tasdiqlash kerak bo‘lgan natijalar shu yerda ko‘rinadi.</p></div>';
    return;
  }
  container.innerHTML = items.map((item) => `
    <article class="review-item">
      <div><strong>${escapeHtml(formatCard(item.card))}</strong><small>${escapeHtml(item.relative_path)} · ${item.page || "?"}-sahifa</small></div>
      <div class="review-reason">${escapeHtml((item.warnings || []).map(warningLabel).join(" · ") || "Natijani hujjat bilan solishtirib tekshiring")}</div>
    </article>`).join("");
}

function openEvidence(card, filePath) {
  const roleLabels = { SENDER: "Jo‘natuvchi", RECIPIENT: "Qabul qiluvchi", UNKNOWN: "Noma’lum" };
  $("#evidence-content").innerHTML = `
    <div class="evidence-card-number">${escapeHtml(formatCard(card.card))}</div>
    <div class="evidence-grid">
      <div><small>Fayl</small><strong>${escapeHtml(filePath)}</strong></div>
      <div><small>Sahifa</small><strong>${card.page || "—"}</strong></div>
      <div><small>Rol</small><strong>${escapeHtml(roleLabels[card.role] || roleLabels.UNKNOWN)}</strong></div>
      <div><small>Rol qanday aniqlandi</small><strong>${escapeHtml(roleMethodLabel(card))}</strong></div>
      <div><small>Karta raqami</small><strong>${card.validation?.luhn ? "Format bo‘yicha tekshirildi" : "Qo‘lda tekshirish kerak"}</strong></div>
      <div><small>O‘qish holati</small><strong>${card.validation?.ocr_engines_agree === true ? "Ikki usulda tasdiqlandi" : card.source?.startsWith("ocr") ? "Hujjat bilan solishtiring" : "Hujjat matnidan olindi"}</strong></div>
    </div>
    <div class="source-evidence"><small>Manba matni</small><p>${highlightEvidence(card.snippet, card.card)}</p></div>
    ${card.ai_assisted ? `<div class="semantic-evidence"><small>Mazmuniy dalil</small><p>${escapeHtml(card.ai_evidence || "—")}</p></div>` : ""}
    ${(card.warnings || []).length ? `<div class="evidence-warnings">${card.warnings.map((warning) => `<span>${escapeHtml(warningLabel(warning))}</span>`).join("")}</div>` : ""}`;
  $("#evidence-dialog").showModal();
}

function renderDashboard(data) {
  $("#stat-files").textContent = data.files;
}

function renderAiStatus(status) {
  const element = $("#ai-status");
  const available = Boolean(status?.available);
  element.classList.toggle("unavailable", !available);
  element.querySelector("b").textContent = available
    ? "AI yordamchi tayyor"
    : status?.enabled === false
      ? "AI yordamchi o‘chirilgan"
      : "AI yordamchi mavjud emas";
  element.title = available ? `${status.model} · lokal` : "Asosiy skanerlash AI'siz davom etadi";
}

async function refresh() {
  const [dashboard, files, results, review, aiStatus] = await Promise.all([api("/api/dashboard"), api("/api/files"), api("/api/results"), api("/api/review"), api("/api/ai-status")]);
  state.dashboard = dashboard;
  state.files = files;
  state.results = results;
  state.review = review;
  state.aiStatus = aiStatus;
  renderDashboard(dashboard);
  renderAiStatus(aiStatus);
  renderFiles(files);
  renderResults(results);
  renderReview(review);
}

async function loadTools() {
  const list = $("#tool-list");
  list.innerHTML = '<div class="empty compact"><strong>Tekshirilmoqda…</strong></div>';
  try {
    const tools = await api("/api/selftest");
    list.innerHTML = tools.map((tool) => `
      <div class="tool-row"><div><strong>${escapeHtml(tool.name)}</strong><small>${escapeHtml(tool.path || tool.install_hint)}</small></div><span class="tool-state ${tool.available ? "ok" : "missing"}">${tool.available ? "TAYYOR" : "O‘RNATILMAGAN"}</span></div>`).join("");
  } catch (error) {
    list.innerHTML = `<div class="empty compact"><strong>Tekshiruv bajarilmadi</strong><p>${escapeHtml(error.message)}</p></div>`;
  }
}

const sourceDialog = $("#source-dialog");
$("#choose-files").addEventListener("click", () => sourceDialog.showModal());
$("#close-source-dialog").addEventListener("click", () => sourceDialog.close());
$("#select-files").addEventListener("click", () => {
  sourceDialog.close();
  $("#file-input").click();
});
$("#select-folder").addEventListener("click", () => {
  sourceDialog.close();
  $("#folder-input").click();
});
$("#file-input").addEventListener("change", (event) => addUploadFiles(event.target.files));
$("#folder-input").addEventListener("change", (event) => addUploadFiles(event.target.files, true));
$("#clear-selection").addEventListener("click", clearSelection);
const dropzone = $("#source-dropzone");
["dragenter", "dragover"].forEach((eventName) => dropzone.addEventListener(eventName, (event) => {
  event.preventDefault();
  dropzone.classList.add("dragging");
}));
["dragleave", "drop"].forEach((eventName) => dropzone.addEventListener(eventName, (event) => {
  event.preventDefault();
  dropzone.classList.remove("dragging");
}));
dropzone.addEventListener("drop", async (event) => {
  try {
    addEntries(await entriesFromDrop(event.dataTransfer));
  } catch (_error) {
    toast("Papka yoki fayllarni o‘qib bo‘lmadi");
  }
});

const clearDialog = $("#clear-dialog");
$("#clear-all").addEventListener("click", () => clearDialog.showModal());
$("#confirm-clear").addEventListener("click", async () => {
  const button = $("#confirm-clear");
  button.disabled = true;
  button.textContent = "Tozalanmoqda…";
  try {
    const response = await fetch("/api/workspace", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ confirm: "CLEAR_ALL" }),
    });
    const result = await response.json();
    if (!response.ok || !result.cleared) throw new Error(result.detail || "Ma’lumotlarni tozalab bo‘lmadi");
    clearDialog.close();
    clearSelection();
    await refresh();
    toast("Barcha ish ma’lumotlari tozalandi");
  } catch (error) {
    toast(error.message);
  } finally {
    button.disabled = false;
    button.textContent = "Ha, hammasini tozalash";
  }
});

$("#intake-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!selectedEntries.length) return;
  const button = $("#start-scan");
  const label = button.querySelector(".scan-button-label");
  const message = $("#intake-message");
  const formData = new FormData();
  selectedEntries.forEach((entry) => {
    formData.append("files", entry.file, entry.file.name);
    formData.append("relative_paths", entry.path);
  });
  button.disabled = true;
  label.textContent = "Skanerlanmoqda…";
  message.className = "form-message";
  message.textContent = "Fayllar qabul qilinmoqda va qayta ishlash boshlanmoqda.";
  try {
    const response = await fetch("/api/uploads", { method: "POST", body: formData });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Skanerlashni boshlab bo‘lmadi");
    toast("Skanerlash jarayoni muvaffaqiyatli boshlandi");
    clearSelection();
    const foundCards = result.processing?.found_cards ?? 0;
    const aiAssisted = result.processing?.ai_assisted ?? 0;
    const reviewCount = result.processing?.needs_review ?? 0;
    message.textContent = `${result.processing?.processed ?? result.uploaded_files} ta hujjat o‘qildi. ${foundCards} ta karta topildi${aiAssisted ? `, AI yordamchi ${aiAssisted} ta karta rolini tasdiqladi` : ""}${reviewCount ? `, ${reviewCount} ta holat tekshiruvga qoldi` : ""}.`;
    await refresh();
  } catch (error) {
    message.className = "form-message error";
    message.textContent = error.message;
  } finally {
    label.textContent = "Skanerlashni boshlash";
    button.disabled = selectedEntries.length === 0;
  }
});

$$('[data-view]').forEach((item) => item.addEventListener("click", () => showView(item.dataset.view)));
$$('[data-go]').forEach((item) => item.addEventListener("click", () => showView(item.dataset.go)));
$(".menu-button").addEventListener("click", () => $(".sidebar").classList.toggle("open"));
$("#refresh-tools").addEventListener("click", loadTools);
$("#result-search").addEventListener("input", () => renderResults(state.results));
$("#role-filter").addEventListener("change", () => renderResults(state.results));
$("#source-filter").addEventListener("change", () => renderResults(state.results));
$("#sort-filter").addEventListener("change", () => renderResults(state.results));
$("#review-filter").addEventListener("change", () => renderResults(state.results));
$("#recent-results").addEventListener("click", async (event) => {
  const copyButton = event.target.closest("[data-copy-card]");
  if (copyButton) {
    await navigator.clipboard.writeText(copyButton.dataset.copyCard);
    toast("Karta raqami nusxalandi");
    return;
  }
  const evidenceButton = event.target.closest(".show-evidence");
  if (evidenceButton) {
    const row = evidenceButton.closest(".card-result");
    const group = evidenceButton.closest(".file-result-group");
    const file = state.results.find((item) => item.relative_path === group.querySelector(".file-result-title strong").textContent);
    const card = file?.cards.find((item) => item.card === row.dataset.card);
    if (card) openEvidence(card, file.relative_path);
  }
});
$("#close-evidence").addEventListener("click", () => $("#evidence-dialog").close());

refresh().catch((error) => toast(error.message));
