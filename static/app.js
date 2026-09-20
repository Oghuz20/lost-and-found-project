function $(sel) {
  return document.querySelector(sel);
}

function showPanel(name) {
  document.querySelectorAll(".tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.tab === name);
  });
  document.querySelectorAll(".panel").forEach((p) => {
    const id = p.id.replace("panel-", "");
    const active = id === name;
    p.classList.toggle("active", active);
    p.hidden = !active;
  });
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    showPanel(btn.dataset.tab);
    if (btn.dataset.tab === "items") loadItems();
  });
});

function formatError(body, status) {
  if (typeof body === "string") return body;
  if (body && body.detail) {
    if (Array.isArray(body.detail)) {
      return body.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
    }
    return String(body.detail);
  }
  return `Request failed (${status})`;
}

async function postRegister(endpoint, form, outputEl) {
  outputEl.textContent = "";
  outputEl.className = "form-result";
  const submitBtn = form.querySelector('button[type="submit"]');
  submitBtn.disabled = true;
  outputEl.textContent = "Analyzing photo… this may take 10–30 seconds.";
  const fd = new FormData(form);
  try {
    const res = await fetch(endpoint, { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      outputEl.className = "form-result error";
      outputEl.textContent = formatError(data, res.status);
      return;
    }
    const item = data.item || {};
    const vlm = item.vlm_description || {};
    outputEl.className = "form-result success";
    outputEl.innerHTML =
      `Registered item #${item.id} (${item.status}). ` +
      `<strong>${vlm.object_class || "object"}</strong> ` +
      `(confidence ${((vlm.confidence ?? 0) * 100).toFixed(0)}%).`;
    form.reset();
  } catch (err) {
    outputEl.className = "form-result error";
    outputEl.textContent = err.message || "Network error";
  } finally {
    submitBtn.disabled = false;
  }
}

$("#form-lost").addEventListener("submit", (e) => {
  e.preventDefault();
  postRegister("/items/lost", e.target, $("#result-lost"));
});

$("#form-found").addEventListener("submit", (e) => {
  e.preventDefault();
  postRegister("/items/found", e.target, $("#result-found"));
});

function renderItemsTable(items) {
  const wrap = $("#items-table-wrap");
  if (!items.length) {
    wrap.innerHTML = "<p class=\"message\">No items yet. Register lost or found items first.</p>";
    return;
  }
  const rows = items
    .map(
      (it) => `
    <tr>
      <td>${it.id}</td>
      <td><span class="badge ${it.status}">${it.status}</span></td>
      <td><img class="thumb" src="/items/${it.id}/image" alt="" loading="lazy" /></td>
      <td>${escapeHtml(it.object_class || "—")}</td>
      <td>${escapeHtml(it.user_text || "")}</td>
      <td><button type="button" class="row-action" data-match-id="${it.id}">Match</button></td>
    </tr>`
    )
    .join("");
  wrap.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Status</th>
          <th>Photo</th>
          <th>Object</th>
          <th>Description</th>
          <th></th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
  wrap.querySelectorAll(".row-action").forEach((btn) => {
    btn.addEventListener("click", () => {
      showPanel("matches");
      const form = $("#form-matches");
      form.item_id.value = btn.dataset.matchId;
      form.requestSubmit();
    });
  });
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function loadItems() {
  const msg = $("#items-message");
  msg.textContent = "";
  msg.className = "message";
  const filter = $("#items-filter").value;
  const url = filter ? `/items?status=${encodeURIComponent(filter)}` : "/items";
  try {
    const res = await fetch(url);
    const data = await res.json();
    if (!res.ok) {
      msg.className = "message error";
      msg.textContent = formatError(data, res.status);
      return;
    }
    renderItemsTable(data.items || []);
  } catch (err) {
    msg.className = "message error";
    msg.textContent = err.message || "Failed to load items";
  }
}

$("#items-filter").addEventListener("change", loadItems);
$("#refresh-items").addEventListener("click", loadItems);

$("#form-matches").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#matches-message");
  const out = $("#matches-results");
  msg.textContent = "";
  out.innerHTML = "";
  const fd = new FormData(e.target);
  const itemId = fd.get("item_id");
  const k = fd.get("k") || "5";
  try {
    const res = await fetch(`/items/${itemId}/matches?k=${encodeURIComponent(k)}`);
    const data = await res.json();
    if (!res.ok) {
      msg.className = "message error";
      msg.textContent = formatError(data, res.status);
      return;
    }
    const query = data.query || {};
    msg.className = "message";
    msg.textContent = `Matches for item #${data.item_id} (${query.object_class || "item"}):`;
    const matches = data.matches || [];
    if (!matches.length) {
      out.innerHTML = "<p class=\"message\">No candidates in the opposite pool yet.</p>";
      return;
    }
    out.innerHTML = `<div class="match-list">${matches
      .map(
        (m) => `
      <article class="match-card">
        <img class="thumb" src="/items/${m.item_id}/image" alt="" />
        <div class="match-score">${(m.score >= 0 ? "+" : "") + m.score.toFixed(3)}</div>
        <div>
          <div><strong>#${m.item_id}</strong> <span class="badge ${m.status}">${m.status}</span></div>
          <div>${escapeHtml(m.object_class || "—")}</div>
          <div class="hint">${escapeHtml(m.user_text || "")}</div>
        </div>
      </article>`
      )
      .join("")}</div>`;
  } catch (err) {
    msg.className = "message error";
    msg.textContent = err.message || "Failed to load matches";
  }
});
