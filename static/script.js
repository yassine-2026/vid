/* ═══════════════════════════════════════════════════════════════════
   VideoNeste — Frontend Script
   i18n + Format fetching + Preview + Streaming download
═══════════════════════════════════════════════════════════════════ */

"use strict";

/* ── State ──────────────────────────────────────────────────────────── */
let _lang     = "en";
let _strings  = {};
let _formats  = [];
let _isBusy   = false;
let _vidTitle = "";

/* ── i18n ────────────────────────────────────────────────────────────── */
const SUPPORTED_LANGS = [
  "ar","en","es","fr","de","zh","hi","pt","ru","ja","ko","it","tr","nl","pl"
];
const RTL_LANGS = ["ar"];

async function loadLang(code) {
  if (!SUPPORTED_LANGS.includes(code)) code = "en";
  try {
    const res  = await fetch(`/lang/${code}.json`);
    if (!res.ok) throw new Error("HTTP " + res.status);
    _strings = await res.json();
    _lang    = code;
    localStorage.setItem("vn_lang", code);
    applyStrings();
    applyDir(_strings.dir || "ltr");
  } catch (e) {
    console.warn("[VideoNeste] Could not load lang:", code, e);
    if (code !== "en") await loadLang("en");
  }
}

function applyStrings() {
  /* Static elements with data-i18n */
  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.getAttribute("data-i18n");
    if (_strings[key]) el.textContent = _strings[key];
  });
  /* Placeholders */
  document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (_strings[key]) el.placeholder = _strings[key];
  });
  /* Page title */
  if (_strings.title) document.title = _strings.title;
  /* Quality select default option */
  const qsDefault = document.querySelector("#quality-select option[value='']");
  if (qsDefault && _strings.quality_select_default) {
    qsDefault.textContent = _strings.quality_select_default;
  }
}

function applyDir(dir) {
  document.getElementById("html-root").setAttribute("dir", dir);
  document.getElementById("html-root").setAttribute("lang", _lang);
}

function t(key, fallback) {
  return _strings[key] || fallback || key;
}

/* ── Language switcher ───────────────────────────────────────────────── */
const langSelect = document.getElementById("lang-select");
langSelect.addEventListener("change", () => loadLang(langSelect.value));

function detectLang() {
  const stored = localStorage.getItem("vn_lang");
  if (stored && SUPPORTED_LANGS.includes(stored)) return stored;
  const browser = (navigator.language || "en").substring(0, 2).toLowerCase();
  return SUPPORTED_LANGS.includes(browser) ? browser : "en";
}

/* ── DOM helpers ─────────────────────────────────────────────────────── */
const $  = id => document.getElementById(id);
const show   = (id, flex) => { const el = $(id); el && el.classList.remove("d-none"); if (flex) el.style.display = "flex"; };
const hide   = id => { const el = $(id); el && el.classList.add("d-none"); };
const setText = (id, txt) => { const el = $(id); if (el) el.textContent = txt; };

/* ── Loading state ───────────────────────────────────────────────────── */
function setLoading(state, msgKey) {
  _isBusy = state;
  $("fetch-btn").disabled   = state;
  $("download-btn").disabled = state;
  $("preview-btn").disabled  = state;

  const btnText    = $("fetch-btn-text");
  const btnSpinner = $("fetch-btn-spinner");

  if (state) {
    btnText.classList.add("d-none");
    btnSpinner.classList.remove("d-none");
    setText("loading-text", t(msgKey || "fetching_formats", "Loading..."));
    show("loading-state");
  } else {
    btnText.classList.remove("d-none");
    btnSpinner.classList.add("d-none");
    hide("loading-state");
  }
}

/* ── Error popup ─────────────────────────────────────────────────────── */
function showError(msg) {
  /* Map error code to localised string if possible */
  const codeMap = {
    cookie_expired:  "cookie_expired",
    unsupported:     "error_fetch",
    login_required:  "error_fetch",
    deleted:         "error_fetch",
    geo_restricted:  "error_fetch",
    network:         "error_server",
    drm:             "error_fetch",
    rate_limit:      "error_server",
    unknown:         "error_fetch",
  };
  /* msg might be a raw string or an object */
  let text = typeof msg === "string" ? msg : "";
  if (!text && typeof msg === "object" && msg.error) {
    const mapped = codeMap[msg.code];
    text = mapped ? t(mapped) : msg.error;
  }
  $("error-message").textContent = text || t("error_fetch");
  $("error-overlay").classList.remove("d-none");
}

function closeError() {
  $("error-overlay").classList.add("d-none");
}

document.getElementById("error-overlay").addEventListener("click", e => {
  if (e.target === $("error-overlay")) closeError();
});
document.addEventListener("keydown", e => { if (e.key === "Escape") closeError(); });

/* ── URL validation ──────────────────────────────────────────────────── */
function validateURL(url) {
  if (!url) return t("error_empty");
  if (!url.startsWith("http://") && !url.startsWith("https://")) return t("error_invalid_url");
  return null;
}

/* ── Main: fetch formats ─────────────────────────────────────────────── */
async function onFetchFormats(e) {
  if (e) e.preventDefault();
  const url = $("url-input").value.trim();
  const err = validateURL(url);
  if (err) { showError(err); return; }
  if (_isBusy) return;

  setLoading(true, "fetching_formats");
  hide("result-section");
  hide("player-wrap");
  $("download-btn").disabled = false;

  try {
    const res  = await fetch("/api/download", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ url }),
    });
    const data = await res.json();

    if (!data.success) {
      showError(data);
      return;
    }

    _formats   = data.formats || [];
    _vidTitle  = data.title   || "VideoNeste";

    renderResultCard(data);
    fireConfetti();
  } catch (ex) {
    showError(t("error_server"));
  } finally {
    setLoading(false);
  }
}

/* ── Render result card ──────────────────────────────────────────────── */
function renderResultCard(data) {
  /* Thumbnail */
  const thumb   = $("result-thumb");
  const thumbFb = $("thumb-fallback");
  if (data.thumbnail) {
    thumb.src   = data.thumbnail;
    thumb.alt   = data.title || "";
    thumb.classList.remove("d-none");
    thumbFb.classList.add("d-none");
    thumb.onerror = () => {
      thumb.classList.add("d-none");
      thumbFb.classList.remove("d-none");
    };
  } else {
    thumb.classList.add("d-none");
    thumbFb.classList.remove("d-none");
  }

  /* Duration */
  const dur = $("duration-badge");
  if (data.duration) {
    dur.textContent = formatDuration(data.duration);
    dur.classList.remove("d-none");
  } else {
    dur.classList.add("d-none");
  }

  /* Platform */
  const plat = $("platform-badge");
  if (data.platform) {
    plat.textContent = data.platform;
    plat.classList.remove("d-none");
  } else {
    plat.classList.add("d-none");
  }

  /* Title */
  $("result-title").textContent = data.title || "";

  /* Uploader */
  const upl = $("result-uploader");
  if (data.uploader) {
    upl.innerHTML   = `<strong>${escHtml(data.uploader)}</strong>`;
    upl.classList.remove("d-none");
  } else {
    upl.classList.add("d-none");
  }

  /* Quality dropdown */
  const sel = $("quality-select");
  sel.innerHTML = `<option value="">${t("quality_select_default")}</option>`;

  _formats.forEach((fmt, idx) => {
    const opt   = document.createElement("option");
    opt.value   = idx;
    let label   = fmt.label;
    if (fmt.type === "audio") label = `♪ ${label}`;
    if (fmt.filesize_str)     label += `  —  ${fmt.filesize_str}`;
    if (fmt.has_audio === false) label += `  (${t("format_video_audio").split("+")[0].trim()} only)`;
    opt.textContent = label;
    sel.appendChild(opt);
  });

  /* Auto-select first quality */
  if (_formats.length > 0) sel.value = "0";

  show("result-section");
  hide("download-status");
}

/* ── Preview ─────────────────────────────────────────────────────────── */
async function onPreview() {
  const url = $("url-input").value.trim();
  if (!url) { showError(t("error_empty")); return; }
  if (_isBusy) return;

  _isBusy = true;
  $("preview-btn").disabled = true;
  setText("loading-text", t("fetching_preview", "Loading preview..."));
  show("loading-state");

  try {
    const res  = await fetch("/api/preview", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ url }),
    });
    const data = await res.json();

    showPlayerSection(data);
  } catch (ex) {
    showError(t("error_server"));
  } finally {
    _isBusy = false;
    $("preview-btn").disabled = false;
    hide("loading-state");
  }
}

function showPlayerSection(data) {
  const player    = $("video-player");
  const source    = $("video-source");
  const fallback  = $("player-fallback");
  const fbThumb   = $("fallback-thumb");

  if (data.stream_url) {
    source.src = data.stream_url;
    player.classList.remove("d-none");
    fallback.classList.add("d-none");
    player.load();
    player.play().catch(() => {}); // auto-play (may be blocked by browser)
  } else {
    player.classList.add("d-none");
    fallback.classList.remove("d-none");
    if (data.thumbnail) {
      fbThumb.src = data.thumbnail;
      fbThumb.classList.remove("d-none");
    } else {
      fbThumb.classList.add("d-none");
    }
  }

  show("player-wrap");
  $("player-wrap").scrollIntoView({ behavior: "smooth", block: "start" });
}

function closePlayer() {
  const player = $("video-player");
  player.pause();
  player.src = "";
  $("video-source").src = "";
  hide("player-wrap");
}

/* ── Download ────────────────────────────────────────────────────────── */
function onDownload() {
  const url   = $("url-input").value.trim();
  const selEl = $("quality-select");
  const idx   = selEl.value;

  if (!url) { showError(t("error_empty")); return; }

  if (idx === "" || _formats.length === 0) {
    /* Fallback: directly use /api/download and then redirect */
    if (_formats.length === 0) {
      showError(t("select_quality_first"));
      return;
    }
  }

  const fmt = _formats[parseInt(idx, 10) || 0];
  if (!fmt) { showError(t("select_quality_first")); return; }

  const params = new URLSearchParams({
    url:    url,
    format: fmt.format_id,
    ext:    fmt.ext    || "mp4",
    title:  _vidTitle  || "VideoNeste",
  });

  /* Create a hidden anchor and click it — no page navigation */
  const a   = document.createElement("a");
  a.href    = `/download?${params.toString()}`;
  a.download = "";
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);

  /* Show feedback */
  const status = $("download-status");
  status.textContent = t("download_started");
  status.classList.remove("d-none");
  setTimeout(() => status.classList.add("d-none"), 4000);
}

/* ── URL input watcher ───────────────────────────────────────────────── */
$("url-input").addEventListener("input", () => {
  closeError();
  const hasVal = $("url-input").value.trim().length > 0;
  if (!hasVal) {
    hide("result-section");
    hide("player-wrap");
    _formats  = [];
    _vidTitle = "";
  }
});

/* ── Confetti ────────────────────────────────────────────────────────── */
function fireConfetti() {
  if (typeof confetti === "undefined") return;
  const n = 160;
  const o = { y: 0.65 };
  confetti({ origin: o, count: Math.floor(n * .25), spread: 26, startVelocity: 55 });
  confetti({ origin: o, count: Math.floor(n * .2),  spread: 60 });
  confetti({ origin: o, count: Math.floor(n * .35), spread: 100, decay: .91, scalar: .8 });
  confetti({ origin: o, count: Math.floor(n * .1),  spread: 120, startVelocity: 25, decay: .92, scalar: 1.2 });
}

/* ── Utils ───────────────────────────────────────────────────────────── */
function formatDuration(sec) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = Math.floor(sec % 60);
  return h > 0
    ? `${h}:${pad(m)}:${pad(s)}`
    : `${m}:${pad(s)}`;
}
function pad(n) { return String(n).padStart(2, "0"); }

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* ── Boot ────────────────────────────────────────────────────────────── */
(function init() {
  /* Footer year */
  const fy = document.getElementById("footer-year");
  if (fy) fy.textContent = new Date().getFullYear();

  /* Load persisted language */
  const lang = detectLang();
  langSelect.value = SUPPORTED_LANGS.includes(lang) ? lang : "en";
  loadLang(lang);
})();
