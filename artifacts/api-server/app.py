import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ── Paths ─────────────────────────────────────────────────────────────
# app.py lives at:  <root>/artifacts/api-server/app.py
# Frontend dist at: <root>/artifacts/video-downloader/dist/public/
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

# CORS: allow all origins so the API works whether called from the same
# domain (production) or a different port (local dev / Replit preview).
CORS(app, resources={r"/api/*": {"origins": "*"}})


# ── Helpers ───────────────────────────────────────────────────────────

def _err(msg: str) -> dict:
    return {"success": False, "error": msg}


def _classify(error_str: str) -> str:
    e = error_str.lower()
    if "unsupported url" in e or "no suitable extractor" in e:
        return "هذه المنصة غير مدعومة حاليًا. يدعم الموقع أكثر من 1800 موقع."
    if "private" in e or "login required" in e or "sign in" in e or "members only" in e:
        return "الفيديو خاص أو يتطلب تسجيل الدخول. جرب توفير ملف cookies.txt."
    if "deleted" in e or "removed" in e or "not found" in e or "404" in e:
        return "الفيديو محذوف أو غير متاح."
    if "geo" in e or "not available in your country" in e:
        return "الفيديو غير متاح في منطقتك الجغرافية."
    if "connection" in e or "network" in e or "timeout" in e or "timed out" in e:
        return "خطأ في الشبكة. يرجى التحقق من اتصالك والمحاولة لاحقًا."
    if "copyright" in e or "drm" in e:
        return "الفيديو محمي بحقوق الملكية أو DRM ولا يمكن تحميله."
    return f"فشل استخراج الفيديو: {error_str[:200]}"


def _ydl_opts() -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "noplaylist": True,
        "skip_download": True,
    }
    proxy = os.environ.get("PROXY") or os.environ.get("HTTP_PROXY")
    if proxy:
        opts["proxy"] = proxy
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


def _extract(url: str) -> dict:
    try:
        import yt_dlp
    except ImportError:
        return _err("yt-dlp غير مثبت على الخادم.")

    opts = _ydl_opts()
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        return _err(_classify(str(exc)))
    except yt_dlp.utils.ExtractorError as exc:
        return _err(_classify(str(exc)))
    except Exception as exc:
        e = str(exc).lower()
        if any(k in e for k in ("connection", "network", "timeout")):
            return _err("خطأ في الاتصال بالشبكة. يرجى المحاولة مرة أخرى.")
        return _err(f"حدث خطأ غير متوقع: {str(exc)[:150]}")

    if info is None:
        return _err("لم يتم العثور على معلومات الفيديو.")

    formats_raw = info.get("formats") or []
    best_video_url   = best_video_quality = best_video_ext = None
    best_audio_url   = best_audio_ext = None
    best_audio_tbr   = 0
    best_video_h     = -1

    for f in formats_raw:
        furl = f.get("url")
        if not furl:
            continue
        vcodec = f.get("vcodec", "none") or "none"
        acodec = f.get("acodec", "none") or "none"
        height = f.get("height") or 0
        tbr    = f.get("tbr") or 0
        ext    = f.get("ext", "")
        has_v  = vcodec not in ("none", "")
        has_a  = acodec not in ("none", "")

        if has_v and has_a and height > best_video_h:
            best_video_h       = height
            best_video_url     = furl
            best_video_quality = f"{height}p" if height else "best"
            best_video_ext     = ext

        elif has_a and not has_v and tbr > best_audio_tbr:
            best_audio_tbr = tbr
            best_audio_url = furl
            best_audio_ext = ext

    if not best_video_url:
        direct = info.get("url")
        if direct:
            best_video_url     = direct
            best_video_quality = "best"
            best_video_ext     = info.get("ext", "mp4")

    if not best_video_url:
        return _err("لم يتم العثور على روابط تحميل متاحة لهذا الفيديو.")

    formats = []
    formats.append({
        "type": "video+audio",
        "quality": best_video_quality or "best",
        "url": best_video_url,
        "ext": best_video_ext,
        "filesize": None,
    })
    if best_audio_url:
        formats.append({
            "type": "audio only",
            "quality": "best",
            "url": best_audio_url,
            "ext": best_audio_ext or "m4a",
            "filesize": None,
        })

    return {
        "success": True,
        "title":    _safe_str(info.get("title")),
        "thumbnail": _safe_str(info.get("thumbnail")),
        "duration":  _safe_int(info.get("duration")),
        "uploader":  _safe_str(
            info.get("uploader") or info.get("channel") or info.get("creator")
        ),
        "platform": _safe_str(info.get("extractor_key") or info.get("extractor")),
        "formats":  formats,
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


# ── Static / React Router fallback ────────────────────────────────────
# Registered only when the compiled frontend exists (i.e. in production).
# In Replit dev the Vite dev-server handles all frontend traffic.

if _SERVE_FRONTEND:
    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path):
        # Never intercept /api/* — those are handled above
        if path.startswith("api/"):
            return jsonify({"error": "Not found"}), 404

        # Serve real static assets (JS, CSS, images, favicon…)
        candidate = os.path.join(FRONTEND_DIST, path)
        if path and os.path.isfile(candidate):
            return send_from_directory(FRONTEND_DIST, path)

        # React Router: everything else → index.html
        return send_from_directory(FRONTEND_DIST, "index.html")


# ── Entrypoint ────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
