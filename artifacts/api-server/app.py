import os
from flask import Flask, request, jsonify, send_from_directory, redirect
from flask_cors import CORS

# ── Paths ─────────────────────────────────────────────────────────────
_APP_DIR      = os.path.dirname(os.path.abspath(__file__))
_ARTIFACTS    = os.path.dirname(_APP_DIR)
_PROJECT_ROOT = os.path.dirname(_ARTIFACTS)

FRONTEND_DIST = os.environ.get(
    "FRONTEND_DIST",
    os.path.join(_PROJECT_ROOT, "artifacts", "video-downloader", "dist", "public"),
)

_SERVE_FRONTEND = os.path.isdir(FRONTEND_DIST) and os.path.isfile(
    os.path.join(FRONTEND_DIST, "index.html")
)

# ── Flask app ─────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=None)

# CORS: all origins for /api/* — same domain in production, different port in dev.
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ── Constants ──────────────────────────────────────────────────────────
# Modern browser User-Agent to avoid bot-detection blocks on some platforms.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ── Helpers ───────────────────────────────────────────────────────────

def _err(msg: str) -> dict:
    return {"success": False, "error": msg}


def _classify(error_str: str) -> str:
    """Map raw yt-dlp error text to a user-friendly Arabic message."""
    e = error_str.lower()
    if "unsupported url" in e or "no suitable extractor" in e:
        return "هذه المنصة غير مدعومة حاليًا."
    if "private" in e or "login required" in e or "sign in" in e or "members only" in e:
        return "الفيديو خاص أو يتطلب تسجيل الدخول. جرّب توفير ملف cookies.txt."
    if "deleted" in e or "removed" in e or ("not found" in e and "404" in e):
        return "الفيديو محذوف أو غير متاح."
    if "geo" in e or "not available in your country" in e:
        return "الفيديو غير متاح في منطقتك الجغرافية."
    if "connection" in e or "network" in e or "timeout" in e or "timed out" in e:
        return "خطأ في الشبكة. يرجى التحقق من اتصالك والمحاولة لاحقًا."
    if "copyright" in e or "drm" in e:
        return "الفيديو محمي بحقوق الملكية أو DRM ولا يمكن تحميله."
    if "rate" in e and "limit" in e:
        return "تم تجاوز حد الطلبات. يرجى الانتظار قليلاً والمحاولة مجدداً."
    return "تعذّر استخراج الفيديو من هذا الرابط."


def _ydl_opts(force_generic: bool = False) -> dict:
    """
    Build yt-dlp options dict.

    cookies.txt: optional Netscape-format cookie file placed at
    artifacts/api-server/cookies.txt. Improves support for login-required
    content (Instagram, YouTube members-only, etc.). The site works
    perfectly without it for the vast majority of platforms.
    """
    opts = {
        "quiet":            True,
        "no_warnings":      True,
        "ignoreerrors":     False,   # we handle errors ourselves via exceptions
        "extract_flat":     False,
        "noplaylist":       True,
        "skip_download":    True,
        # Modern browser header to bypass bot-detection on some platforms
        "http_headers": {
            "User-Agent": _USER_AGENT,
        },
    }

    if force_generic:
        # Last-resort extractor for platforms not natively supported by yt-dlp.
        # Tries to find any playable stream in the page HTML.
        opts["force_generic_extractor"] = True

    proxy = os.environ.get("PROXY") or os.environ.get("HTTP_PROXY")
    if proxy:
        opts["proxy"] = proxy

    # Optional cookie support — silently ignored when the file doesn't exist
    cookie_path = os.path.join(_APP_DIR, "cookies.txt")
    if os.path.isfile(cookie_path):
        opts["cookiefile"] = cookie_path

    return opts


def _safe_int(val):
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None


def _safe_str(val, limit: int = 500):
    if val is None:
        return None
    return str(val)[:limit]


def _build_formats(info: dict) -> list:
    """
    Extract multiple quality options from yt-dlp info dict.
    Returns up to 5 combined video+audio qualities plus 1 audio-only option.
    """
    formats_raw = info.get("formats") or []

    combined      = []
    audio_only_list = []

    for f in formats_raw:
        furl   = f.get("url")
        if not furl:
            continue
        vcodec = (f.get("vcodec") or "none").lower()
        acodec = (f.get("acodec") or "none").lower()
        has_v  = vcodec not in ("none", "")
        has_a  = acodec not in ("none", "")

        if has_v and has_a:
            combined.append(f)
        elif has_a and not has_v:
            audio_only_list.append(f)

    # Sort combined formats by resolution, highest first
    combined.sort(key=lambda f: (f.get("height") or 0), reverse=True)

    result      = []
    seen_heights = set()

    for f in combined:
        h = f.get("height") or 0
        if h in seen_heights:
            continue
        seen_heights.add(h)
        result.append({
            "type":      "video+audio",
            "quality":   f"{h}p" if h else "best",
            "url":       f["url"],
            "ext":       f.get("ext") or "mp4",
            "filesize":  f.get("filesize") or f.get("filesize_approx"),
            "format_id": f.get("format_id"),
        })
        if len(result) >= 5:   # cap at 5 quality options
            break

    # If no combined format found, fall back to the top-level direct URL
    if not result:
        direct = info.get("url")
        if direct:
            result.append({
                "type":      "video+audio",
                "quality":   "best",
                "url":       direct,
                "ext":       info.get("ext") or "mp4",
                "filesize":  info.get("filesize") or info.get("filesize_approx"),
                "format_id": None,
            })

    # Best audio-only track
    if audio_only_list:
        best_audio = max(audio_only_list, key=lambda f: f.get("tbr") or 0)
        result.append({
            "type":      "audio only",
            "quality":   "best",
            "url":       best_audio["url"],
            "ext":       best_audio.get("ext") or "m4a",
            "filesize":  best_audio.get("filesize") or best_audio.get("filesize_approx"),
            "format_id": best_audio.get("format_id"),
        })

    return result


def _try_extract_raw(url: str, force_generic: bool = False):
    """
    Low-level extraction helper.
    Returns (info_dict, error_string). Exactly one will be None.
    Never raises — all exceptions are caught and returned as error strings.
    """
    try:
        import yt_dlp
    except ImportError:
        return None, "yt-dlp not installed"

    opts = _ydl_opts(force_generic=force_generic)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return info, None
    except Exception as exc:
        return None, str(exc)


def _extract(url: str) -> dict:
    """
    Extract video info with automatic retry using force_generic_extractor.

    Flow:
      1. Normal extraction with the standard yt-dlp extractors.
      2. If yt-dlp reports "no suitable extractor" / "unsupported URL",
         automatically retry with force_generic_extractor=True, which
         attempts to scrape any playable stream from the page HTML.
      3. Classify the error into an Arabic user message if both fail.
    """
    # ── First attempt: normal extraction ──────────────────────────────
    info, raw_err = _try_extract_raw(url, force_generic=False)

    # ── Retry with generic extractor on "unsupported" errors ──────────
    if info is None and raw_err:
        e = raw_err.lower()
        if "unsupported url" in e or "no suitable extractor" in e:
            info, raw_err = _try_extract_raw(url, force_generic=True)

    # ── Handle permanent failure ───────────────────────────────────────
    if info is None:
        return _err(_classify(raw_err or "unknown error"))

    # ── Build response ─────────────────────────────────────────────────
    formats = _build_formats(info)
    if not formats:
        return _err("لم يتم العثور على روابط تحميل متاحة لهذا الفيديو.")

    return {
        "success":   True,
        "title":     _safe_str(info.get("title")),
        "thumbnail": _safe_str(info.get("thumbnail")),
        "duration":  _safe_int(info.get("duration")),
        "uploader":  _safe_str(
            info.get("uploader") or info.get("channel") or info.get("creator")
        ),
        "platform":  _safe_str(info.get("extractor_key") or info.get("extractor")),
        "formats":   formats,
    }


# ── API routes ────────────────────────────────────────────────────────

@app.route("/api/healthz", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/download", methods=["POST"])
def download():
    data = request.get_json(silent=True)
    if not data or not data.get("url"):
        return jsonify(_err("الرجاء إدخال رابط الفيديو.")), 400

    url = str(data["url"]).strip()
    if not url.startswith(("http://", "https://")):
        return jsonify(_err("الرابط غير صالح. يجب أن يبدأ بـ http:// أو https://")), 400

    result = _extract(url)
    return jsonify(result), (200 if result.get("success") else 400)


@app.route("/api/download-file", methods=["GET", "POST"])
def download_file():
    """
    Redirect the browser to a direct CDN download URL.

    Accepts:
      GET  /api/download-file?url=<encoded-url>
      POST /api/download-file  { "url": "..." }

    The server performs a 302 redirect so the browser handles the download
    directly from the CDN — no proxying through the server, no memory overhead.
    """
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        url  = data.get("url", "").strip()
    else:
        url = request.args.get("url", "").strip()

    if not url or not url.startswith(("http://", "https://")):
        return jsonify({"success": False, "error": "رابط التحميل غير صالح."}), 400

    return redirect(url, code=302)


# ── Static / React Router fallback ────────────────────────────────────
# Only registered when the compiled React bundle exists (production).
# In Replit dev mode, Vite handles all frontend traffic.

if _SERVE_FRONTEND:
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        if path.startswith("api/"):
            return jsonify({"error": "Not found"}), 404

        candidate = os.path.join(FRONTEND_DIST, path)
        if path and os.path.isfile(candidate):
            return send_from_directory(FRONTEND_DIST, path)

        return send_from_directory(FRONTEND_DIST, "index.html")


# ── Local development entrypoint ──────────────────────────────────────
# Gunicorn (production) ignores this block entirely.

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
