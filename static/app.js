const $ = (id) => document.getElementById(id);

const els = {
  rfq: $("rfq"),
  vendor: $("vendor"),
  file: $("file"),
  submit: $("submit"),
  status: $("status"),
  result: $("result"),
  evaluations: $("evaluations"),
};

const escape = (s) =>
  String(s).replace(/[&<>"']/g, (c) =>
    c === "&" ? "&" + "amp;"
    : c === "<" ? "&" + "lt;"
    : c === ">" ? "&" + "gt;"
    : c === '"' ? "&" + "quot;"
    : "&" + "#39;"
  );

const dimBadge = (d) =>
  `<span class="dim">${escape(d)}</span>`;

const renderList = (items) =>
  items
    .map(
      (x) => `<li><span class="dim">${escape(x.dimension)}</span> ${escape(x.text)}</li>`
    )
    .join("");

function setStatus(text, kind = "") {
  els.status.textContent = text || "";
  els.status.className = kind;
}

function updateSubmitState() {
  const hasRfq = !!els.rfq.value;
  const hasText = els.vendor.value.trim().length > 0;
  els.submit.disabled = !(hasRfq && hasText);
}

function renderResult(data) {
  if (!data) {
    els.result.innerHTML = "";
    return;
  }
  if (data.error) {
    els.result.innerHTML = `<div class="error"><strong>${escape(data.error)}</strong>${
      data.detail ? ": " + escape(data.detail) : ""
    }</div>`;
    return;
  }
  els.result.innerHTML = `
    <div class="score">Score: <strong>${escape(data.score)}</strong> / 100</div>
    <h3>Reasons</h3>
    <ul class="bullets">${renderList(data.reasons)}</ul>
    <h3>Gaps</h3>
    <ul class="bullets">${renderList(data.gaps)}</ul>
  `;
}

function renderEvaluations(list) {
  if (!list || list.length === 0) {
    els.evaluations.innerHTML = '<li class="empty">No evaluations yet.</li>';
    return;
  }
  els.evaluations.innerHTML = list
    .map((e) => {
      const preview =
        e.vendor_text.length > 120
          ? escape(e.vendor_text.slice(0, 120)) + "…"
          : escape(e.vendor_text);
      return `
        <li class="eval">
          <div class="eval-header">
            <span class="eval-rfq">${escape(e.rfq_id)}</span>
            <span class="eval-score">Score ${escape(e.score)}</span>
            <span class="eval-ts">${escape(e.created_at)}</span>
          </div>
          <div class="eval-vendor" title="${escape(e.vendor_text)}">${preview}</div>
          <details>
            <summary>Reasons & gaps</summary>
            <h4>Reasons</h4>
            <ul class="bullets">${renderList(e.reasons)}</ul>
            <h4>Gaps</h4>
            <ul class="bullets">${renderList(e.gaps)}</ul>
          </details>
        </li>
      `;
    })
    .join("");
}

async function safeJson(res) {
  const ct = (res.headers.get("content-type") || "").toLowerCase();
  if (ct.includes("application/json")) {
    return res.json();
  }
  const text = await res.text();
  return { error: "non-JSON response", detail: text.slice(0, 200) };
}

async function loadRfqs() {
  try {
    const res = await fetch("/api/rfqs");
    const rfqs = await res.json();
    els.rfq.innerHTML =
      '<option value="">-- select an RFQ --</option>' +
      rfqs
        .map(
          (r) =>
            `<option value="${escape(r.id)}">${escape(r.id)} — ${escape(r.title)}</option>`
        )
        .join("");
  } catch (err) {
    els.rfq.innerHTML = '<option value="">Failed to load RFQs</option>';
  }
  updateSubmitState();
}

async function loadEvaluations() {
  try {
    const res = await fetch("/api/evaluations");
    const list = await res.json();
    renderEvaluations(list);
  } catch (err) {
    els.evaluations.innerHTML = '<li class="empty">Failed to load history.</li>';
  }
}

async function submitEvaluation() {
  const rfqId = els.rfq.value;
  const vendorText = els.vendor.value.trim();
  if (!rfqId || !vendorText) return;

  els.submit.disabled = true;
  setStatus("Evaluating…", "loading");
  renderResult(null);

  try {
    const res = await fetch("/api/evaluate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rfq_id: rfqId, vendor_text: vendorText }),
    });
    const data = await safeJson(res);
    if (!res.ok) {
      setStatus(res.status === 502 ? "Evaluation failed, try again." : "Failed.", "error");
      renderResult(data);
    } else {
      setStatus("Done.", "ok");
      renderResult(data);
      await loadEvaluations();
    }
  } catch (err) {
    setStatus("Network error.", "error");
    renderResult({ error: "network error", detail: String(err) });
  } finally {
    updateSubmitState();
  }
}

function wireFileInput() {
  els.file.addEventListener("change", () => {
    const file = els.file.files && els.file.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      els.vendor.value = reader.result;
      updateSubmitState();
    };
    reader.onerror = () => setStatus("Failed to read file.", "error");
    reader.readAsText(file);
  });
}

function init() {
  loadRfqs();
  loadEvaluations();
  els.rfq.addEventListener("change", updateSubmitState);
  els.vendor.addEventListener("input", updateSubmitState);
  els.submit.addEventListener("click", submitEvaluation);
  wireFileInput();
}

document.addEventListener("DOMContentLoaded", init);
