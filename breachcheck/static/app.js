"use strict";

const $ = (sel) => document.querySelector(sel);
const HISTORY_KEY = "breachcheck.history";

// ---------------------------------------------------------------------------
// View switching
// ---------------------------------------------------------------------------
$("#tab-search").addEventListener("click", () => switchView("search"));
$("#tab-settings").addEventListener("click", () => switchView("settings"));

function switchView(name) {
  const isSearch = name === "search";
  $("#view-search").classList.toggle("hidden", !isSearch);
  $("#view-settings").classList.toggle("hidden", isSearch);
  $("#tab-search").classList.toggle("active", isSearch);
  $("#tab-settings").classList.toggle("active", !isSearch);
}

// ---------------------------------------------------------------------------
// Status chips
// ---------------------------------------------------------------------------
async function refreshStatus() {
  try {
    const s = await (await fetch("/api/status")).json();
    setChip("#chip-lc", "LeakCheck", s.leakcheck_set);
    setChip("#chip-hibp", "HIBP", s.hibp_set);
    if (!s.leakcheck_set) switchView("settings");
  } catch (_) {}
}
function setChip(sel, label, on) {
  const el = $(sel);
  el.classList.toggle("on", on);
  el.classList.toggle("off", !on);
  el.innerHTML = `${label}: <b>${on ? "OK" : "unset"}</b>`;
}

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------
$("#toggle-reveal").addEventListener("click", () => {
  const t = $("#key-lc").type === "password" ? "text" : "password";
  $("#key-lc").type = t;
  $("#key-hibp").type = t;
  $("#toggle-reveal").textContent = t === "text" ? "hide" : "reveal";
});

$("#settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = {
    leakcheck_key: $("#key-lc").value,
    hibp_key: $("#key-hibp").value,
    persist: $("#persist").checked,
  };
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok || data.ok === false) {
    $("#settings-msg").innerHTML = `<span style="color:var(--red)">${esc(data.error || "save failed")}</span>`;
    return;
  }
  // Clear the inputs from the DOM once saved so keys don't linger on screen.
  $("#key-lc").value = "";
  $("#key-hibp").value = "";
  $("#settings-msg").innerHTML = `<span style="color:var(--green)">saved &#10003; keys held in memory${body.persist ? " + local .env" : ""}</span>`;
  refreshStatus();
});

$("#clear-keys").addEventListener("click", async () => {
  await fetch("/api/settings/clear", { method: "POST" });
  $("#settings-msg").innerHTML = `<span style="color:var(--amber)">keys wiped</span>`;
  refreshStatus();
});

// ---------------------------------------------------------------------------
// Search type UI hints
// ---------------------------------------------------------------------------
const HINTS = {
  auto: "Reverse / auto-detect: paste an email, phone, username, name, or hash — LeakCheck figures out the type.",
  email: "Looks up an email address in LeakCheck breach data.",
  username: "Looks up a username / login.",
  phone: "Phone number, digits only (e.g. 15551234567).",
  keyword: "Name or free-text keyword search.",
  hash: "Search by a password/credential hash (md5/sha*).",
  password: "Checked ONLY against HIBP Pwned Passwords via k-anonymity. The password is SHA-1'd locally; only the first 5 hash chars are sent.",
};
function updateHint() {
  const t = $("#search-type").value;
  $("#type-hint").textContent = HINTS[t] || "";
  const isPw = t === "password";
  $("#limit-wrap").classList.toggle("hidden", isPw);
  // "also HIBP email" only makes sense for email lookups.
  $("#hibp-also-wrap").classList.toggle("hidden", t !== "email" && t !== "auto");
  $("#search-query").type = isPw ? "password" : "text";
}
$("#search-type").addEventListener("change", updateHint);

// ---------------------------------------------------------------------------
// Search submit
// ---------------------------------------------------------------------------
$("#search-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const type = $("#search-type").value;
  const query = $("#search-query").value.trim();
  if (!query) return;

  showLoading(true);
  clearError();
  $("#results").innerHTML = "";

  try {
    if (type === "password") {
      await runPassword(query);
    } else {
      await runLeakCheck(type, query);
      if ((type === "email" || type === "auto") && $("#hibp-also").checked && looksLikeEmail(query)) {
        await runHibpEmail(query);
      }
    }
    addHistory(type, query);
  } catch (err) {
    showError(err.message || String(err));
  } finally {
    showLoading(false);
  }
});

async function runLeakCheck(type, query) {
  const res = await fetch("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type, query, limit: Number($("#search-limit").value) || 100 }),
  });
  const data = await res.json();
  if (!res.ok || data.ok === false) throw new Error(data.error || "search failed");
  renderLeakCheck(data);
}

async function runHibpEmail(email) {
  const res = await fetch("/api/hibp/email", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type: "email", query: email }),
  });
  const data = await res.json();
  if (!res.ok || data.ok === false) {
    // HIBP is optional; surface as a soft note, don't nuke LeakCheck results.
    appendNote(`HIBP: ${data.error || "lookup failed"}`);
    return;
  }
  renderHibpBreaches(data);
}

async function runPassword(password) {
  const res = await fetch("/api/hibp/password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  const data = await res.json();
  if (!res.ok || data.ok === false) throw new Error(data.error || "password check failed");
  renderPassword(data);
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------
const PW_KEYS = new Set(["password", "pass"]);

function renderLeakCheck(data) {
  const root = $("#results");
  const head = document.createElement("div");
  head.className = "summary";
  head.innerHTML = `LEAKCHECK &rarr; <b>${data.count}</b> record(s)`;
  root.appendChild(head);

  if (!data.count) {
    appendNote("LeakCheck: no records found. (clean, or not in this dataset)");
    return;
  }

  data.results.forEach((rec) => {
    const card = document.createElement("div");
    card.className = "record";
    const src = sourceLabel(rec.source);
    if (src) {
      const s = document.createElement("div");
      s.className = "src";
      s.textContent = "SOURCE: " + src;
      card.appendChild(s);
    }
    const kv = document.createElement("div");
    kv.className = "kv";
    Object.keys(rec).forEach((key) => {
      if (key === "source") return;
      const val = rec[key];
      if (val === null || val === "" || (Array.isArray(val) && !val.length)) return;
      const k = document.createElement("div");
      k.className = "k";
      k.textContent = key;
      const v = document.createElement("div");
      v.className = "v" + (PW_KEYS.has(key.toLowerCase()) ? " pw" : "");
      v.textContent = typeof val === "object" ? JSON.stringify(val) : String(val);
      kv.appendChild(k);
      kv.appendChild(v);
    });
    card.appendChild(kv);
    root.appendChild(card);
  });
}

function sourceLabel(source) {
  if (!source) return "";
  if (typeof source === "string") return source;
  const name = source.name || "unknown";
  return source.breach_date ? `${name} (${source.breach_date})` : name;
}

function renderHibpBreaches(data) {
  const root = $("#results");
  const head = document.createElement("div");
  head.className = "summary";
  head.innerHTML = `HIBP &rarr; <b>${data.count}</b> breach(es)`;
  root.appendChild(head);

  if (!data.count) {
    appendNote("HIBP: no breaches for this account.");
    return;
  }
  data.results.forEach((b) => {
    const card = document.createElement("div");
    card.className = "breach";
    const classes = (b.DataClasses || []).map((c) => `<span>${esc(c)}</span>`).join("");
    card.innerHTML = `
      <h3>${esc(b.Title || b.Name || "breach")}</h3>
      <div class="meta">${esc(b.Domain || "")} &middot; breach date: ${esc(b.BreachDate || "?")}
        &middot; accounts: ${esc(String(b.PwnCount || "?"))}</div>
      <div class="classes">${classes}</div>`;
    root.appendChild(card);
  });
}

function renderPassword(data) {
  const root = $("#results");
  const div = document.createElement("div");
  if (data.pwned) {
    div.className = "pw-result bad";
    div.innerHTML = `&#9888; PWNED &mdash; seen <b>${data.count.toLocaleString()}</b> time(s) in known breaches. Do not use it.`;
  } else {
    div.className = "pw-result safe";
    div.innerHTML = `&#10003; Not found in HIBP Pwned Passwords. (absence &ne; safety)`;
  }
  root.appendChild(div);
}

function appendNote(text) {
  const n = document.createElement("div");
  n.className = "summary";
  n.textContent = text;
  $("#results").appendChild(n);
}

// ---------------------------------------------------------------------------
// History (browser localStorage only)
// ---------------------------------------------------------------------------
function loadHistory() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); }
  catch (_) { return []; }
}
function addHistory(type, query) {
  // Never store raw passwords in history.
  const q = type === "password" ? "••••••••" : query;
  const list = loadHistory();
  list.unshift({ type, q, t: new Date().toLocaleTimeString() });
  localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(0, 25)));
  renderHistory();
}
function renderHistory() {
  const ul = $("#history");
  ul.innerHTML = "";
  loadHistory().forEach((h) => {
    const li = document.createElement("li");
    li.innerHTML = `<span>[${esc(h.type)}] ${esc(h.q)}</span><span class="t">${esc(h.t)}</span>`;
    li.addEventListener("click", () => {
      if (h.type === "password") return;
      $("#search-type").value = h.type;
      updateHint();
      $("#search-query").value = h.q;
    });
    ul.appendChild(li);
  });
}
$("#clear-history").addEventListener("click", () => {
  localStorage.removeItem(HISTORY_KEY);
  renderHistory();
});

// ---------------------------------------------------------------------------
// Utils
// ---------------------------------------------------------------------------
function showLoading(on) {
  $("#loading").classList.toggle("hidden", !on);
  $("#run-btn").disabled = on;
}
function showError(msg) { const e = $("#error"); e.textContent = "✗ " + msg; e.classList.remove("hidden"); }
function clearError() { $("#error").classList.add("hidden"); }
function esc(s) { return String(s).replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c])); }
function looksLikeEmail(s) { return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(s); }

// Init
updateHint();
renderHistory();
refreshStatus();
