/* ── State ──────────────────────────────────────────────────────────── */
let isLoading = false;

/* ── DOM refs ───────────────────────────────────────────────────────── */
const form         = document.getElementById("download-form");
const urlInput     = document.getElementById("url-input");
const submitBtn    = document.getElementById("submit-btn");
const btnText      = document.getElementById("btn-text");
const btnSpinner   = document.getElementById("btn-spinner");
const loadingEl    = document.getElementById("loading");
const resultCard   = document.getElementById("result-card");
const errorOverlay = document.getElementById("error-overlay");
const errorMsg     = document.getElementById("error-message");

/* ── Form submission ────────────────────────────────────────────────── */
async function handleSubmit(e) {
  e.preventDefault();
  const url = urlInput.value.trim();
  if (!url || isLoading) return;
  await extractVideo(url);
}

/* ── Extract video ──────────────────────────────────────────────────── */
async function extractVideo(url) {
  setLoading(true);
  hideResult();

  try {
    const res = await fetch("/api/download", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ url }),
    });

    const data = await res.json();

    if (data.success) {
      renderResult(data);
      fireConfetti();
    } else {
      showError(data.error || "تعذّر استخراج الفيديو من هذا الرابط.");
    }
  } catch (err) {
    showError("خطأ في الشبكة أو الخادم غير متاح. يرجى المحاولة مجدداً.");
  } finally {
    setLoading(false);
  }
}

/* ── Render result card ─────────────────────────────────────────────── */
function renderResult(data) {
  /* Thumbnail */
  const thumb       = document.getElementById("result-thumb");
  const thumbFallbk = document.getElementById("thumb-fallback");

  if (data.thumbnail) {
    thumb.src         = data.thumbnail;
    thumb.alt         = data.title || "صورة مصغرة";
    thumb.classList.remove("hidden");
    thumbFallbk.classList.add("hidden");
    thumb.onerror = () => {
      thumb.classList.add("hidden");
      thumbFallbk.classList.remove("hidden");
    };
  } else {
    thumb.classList.add("hidden");
    thumbFallbk.classList.remove("hidden");
  }

  /* Duration badge */
  const durEl = document.getElementById("result-duration");
  if (data.duration) {
    durEl.textContent = formatDuration(data.duration);
    durEl.classList.remove("hidden");
  } else {
    durEl.classList.add("hidden");
  }

  /* Platform badge */
  const platEl = document.getElementById("result-platform");
  if (data.platform) {
    platEl.textContent = data.platform;
    platEl.classList.remove("hidden");
  } else {
    platEl.classList.add("hidden");
  }

  /* Title */
  document.getElementById("result-title").textContent = data.title || "عنوان غير متاح";

  /* Uploader */
  const uplEl = document.getElementById("result-uploader");
  if (data.uploader) {
    uplEl.innerHTML = `بواسطة <strong>${escHtml(data.uploader)}</strong>`;
    uplEl.classList.remove("hidden");
  } else {
    uplEl.classList.add("hidden");
  }

  /* Formats */
  const grid = document.getElementById("formats-grid");
  grid.innerHTML = "";

  if (!data.formats || data.formats.length === 0) {
    grid.innerHTML = '<p style="color:var(--muted);font-size:.9rem;padding:.5rem 0">لم يتم العثور على صيغ متاحة.</p>';
  } else {
    data.formats.forEach((fmt) => {
      const a     = document.createElement("a");
      const dlUrl = `/api/download-file?url=${encodeURIComponent(fmt.url)}`;
      a.href      = dlUrl;
      a.target    = "_blank";
      a.rel       = "noopener noreferrer";
      a.download  = "";
      a.className = "format-btn";

      const icon  = fmt.type === "audio" ? "♪" : "▶";
      const label = fmt.quality + (fmt.ext ? ` <span class="format-ext">${escHtml(fmt.ext)}</span>` : "");
      const size  = fmt.filesize ? `<span class="format-size">${formatSize(fmt.filesize)}</span>` : "";

      a.innerHTML = `
        <span class="format-icon">${icon}</span>
        <span class="format-label">${label}</span>
        ${size}
      `;
      grid.appendChild(a);
    });
  }

  resultCard.classList.remove("hidden");
}

/* ── Loading state ──────────────────────────────────────────────────── */
function setLoading(state) {
  isLoading          = state;
  submitBtn.disabled = state;
  btnText.classList.toggle("hidden",  state);
  btnSpinner.classList.toggle("hidden", !state);
  loadingEl.classList.toggle("hidden",  !state);
}

/* ── Hide result ────────────────────────────────────────────────────── */
function hideResult() {
  resultCard.classList.add("hidden");
}

/* ── Error popup ────────────────────────────────────────────────────── */
function showError(msg) {
  errorMsg.textContent = msg;
  errorOverlay.classList.remove("hidden");
}

function closeError() {
  errorOverlay.classList.add("hidden");
}

/* Close popup on overlay click */
errorOverlay.addEventListener("click", (e) => {
  if (e.target === errorOverlay) closeError();
});

/* Close on Escape */
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeError();
});

/* ── Confetti ────────────────────────────────────────────────────────── */
function fireConfetti() {
  if (typeof confetti === "undefined") return;
  const count  = 180;
  const origin = { y: 0.65 };
  const fire   = (ratio, opts) =>
    confetti({ origin, count: Math.floor(count * ratio), ...opts });

  fire(0.25, { spread: 26, startVelocity: 55 });
  fire(0.20, { spread: 60 });
  fire(0.35, { spread: 100, decay: 0.91, scalar: 0.8 });
  fire(0.10, { spread: 120, startVelocity: 25, decay: 0.92, scalar: 1.2 });
  fire(0.10, { spread: 120, startVelocity: 45 });
}

/* ── Utils ───────────────────────────────────────────────────────────── */
function formatDuration(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${pad(m)}:${pad(s)}`;
  return `${m}:${pad(s)}`;
}

function pad(n) { return String(n).padStart(2, "0"); }

function formatSize(bytes) {
  if (!bytes) return "";
  if (bytes < 1024 * 1024)           return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024)    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 ** 3)).toFixed(1)} GB`;
}

function escHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* ── Clear results on new input ─────────────────────────────────────── */
urlInput.addEventListener("input", () => {
  if (!resultCard.classList.contains("hidden")) hideResult();
  closeError();
});
