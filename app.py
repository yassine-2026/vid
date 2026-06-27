"""
VideoNeste — Universal video downloader (Flask + yt-dlp)
Supports 1800+ platforms. Streams video directly; no temp files on Render.

── COOKIES_BASE64 (for login-required / age-restricted content) ──────────
 1. Export browser cookies as Netscape HTTP Cookie File format.
 2. Encode:  base64 -w 0 cookies.txt
 3. In Render dashboard → Environment → add key COOKIES_BASE64 with that value.
 Cookies are decoded to a temp file on startup and auto-deleted on shutdown.
"""
import os
import sys
import atexit
import base64
import subprocess
import tempfile

from flask import (
    Flask, request, jsonify, render_template,
    redirect, Response, stream_with_context, send_from_directory,
)
from flask_cors import CORS

# ── App setup ─────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app, resources={r"/api/*": {"origins": "*"}, r"/download": {"origins": "*"}})

_APP_DIR   = os.path.dirname(os.path.abspath(__file__))
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ── Cookies ───────────────────────────────────────────────────────────
_COOKIE_FILE: str | None = None

def _setup_cookies() -> None:
    global _COOKIE_FILE
    b64 = os.environ.get("COOKIES_BASE64", "").strip()
    if b64:
        try:
            data = base64.b64decode(b64)
            fd, path = tempfile.mkstemp(suffix=".txt", prefix="vn_cookies_")
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            _COOKIE_FILE = path
            atexit.register(_cleanup_cookies)
            print("[VideoNeste] Cookies decoded from COOKIES_BASE64.")
        except Exception as exc:
            print(f"[VideoNeste] Warning – COOKIES_BASE64 decode failed: {exc}")
        return
    # Fallback: static cookies.txt in project root
    local = os.path.join(_APP_DIR, "cookies.txt")
    if os.path.isfile(local):
        _COOKIE_FILE = local
        print("[VideoNeste] Using cookies.txt from project root.")

def _cleanup_cookies() -> None:
    if _COOKIE_FILE and _COOKIE_FILE.startswith(tempfile.gettempdir()):
        try:
            os.unlink(_COOKIE_FILE)
        except Exception:
            pass

_setup_cookies()

# ── Helpers ───────────────────────────────────────────────────────────

def _err(msg: str, code: str | None = None) -> dict:
    r: dict = {"success": False, "error": msg}
    if code:
        r["code"] = code
    return r


def _classify(raw: str) -> dict:
    """Map raw yt-dlp error text to a structured error dict."""
    e = raw.lower()
    if "cookie" in e and ("expire" in e or "invalid" in e):
        return _err("Cookie file is expired or invalid.", code="cookie_expired")
    if "unsupported url" in e or "no suitable extractor" in e:
        return _err("This platform is not supported.", code="unsupported")
    if "private" in e or "login required" in e or "sign in" in e or "members only" in e:
        return _err("The video is private or requires login.", code="login_required")
    if "deleted" in e or "removed" in e:
        return _err("The video has been deleted or is unavailable.", code="deleted")
    if "geo" in e or "not available in your country" in e:
        return _err("The video is geo-restricted.", code="geo_restricted")
    if "connection" in e or "network" in e or "timeout" in e or "timed out" in e:
        return _err("Network error. Please check your connection.", code="network")
    if "drm" in e or "copyright" in e:
        return _err("DRM-protected content cannot be downloaded.", code="drm")
    if "rate" in e and "limit" in e:
        return _err("Rate limit exceeded. Please wait and retry.", code="rate_limit")
    return _err("Could not extract video from this URL.", code="unknown")


def _base_ydl_opts() -> dict:
    opts: dict = {
        "quiet":        True,
        "no_warnings":  True,
        "ignoreerrors": False,
        "noplaylist":   True,
        "http_headers": {"User-Agent": _USER_AGENT},
    }
    if _COOKIE_FILE:
        opts["cookiefile"] = _COOKIE_FILE
    proxy = os.environ.get("PROXY") or os.environ.get("HTTP_PROXY")
    if proxy:
        opts["proxy"] = proxy
    return opts


def _safe_int(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _fmt_size(b) -> str | None:
    if not b:
        return None
    try:
        b = int(b)
        if b < 1024 * 1024:
            return f"{b / 1024:.1f} KB"
        if b < 1024 ** 3:
            return f"{b / (1024 ** 2):.1f} MB"
        return f"{b / (1024 ** 3):.1f} GB"
    except Exception:
        return None


def _quality_label(h: int) -> str:
    if h >= 4320: return f"8K ({h}p)"
    if h >= 2160: return f"4K ({h}p)"
    if h >= 1440: return f"2K ({h}p)"
    if h >= 1080: return f"Full HD ({h}p)"
    if h >= 720:  return f"HD ({h}p)"
    if h >= 480:  return f"SD ({h}p)"
    if h > 0:     return f"{h}p"
    return "best"


def _parse_formats(info: dict) -> list:
    fmts    = info.get("formats") or []
    combined: list = []
    audios:   list = []

    for f in fmts:
        url     = f.get("url") or f.get("manifest_url")
        if not url:
            continue
        vcodec = (f.get("vcodec") or "none").lower()
        acodec = (f.get("acodec") or "none").lower()
        has_v  = vcodec not in ("none", "")
        has_a  = acodec not in ("none", "")
        if has_v:
            combined.append(f)
        elif has_a:
            audios.append(f)

    combined.sort(key=lambda x: x.get("height") or 0, reverse=True)

    result: list = []
    seen_h: set  = set()
    for f in combined:
        h    = f.get("height") or 0
        if h > 0 and h in seen_h:
            continue
        seen_h.add(h)
        acodec = (f.get("acodec") or "none").lower()
        sz     = f.get("filesize") or f.get("filesize_approx")
        result.append({
            "format_id":    f.get("format_id", "best"),
            "label":        _quality_label(h),
            "height":       h,
            "ext":          f.get("ext") or "mp4",
            "filesize":     sz,
            "filesize_str": _fmt_size(sz),
            "has_audio":    acodec not in ("none", ""),
            "type":         "video",
        })
        if len(result) >= 8:
            break

    # Best audio-only
    if audios:
        best = max(audios, key=lambda x: x.get("tbr") or x.get("abr") or 0)
        sz   = best.get("filesize") or best.get("filesize_approx")
        result.append({
            "format_id":    best.get("format_id", "bestaudio"),
            "label":        "Best Audio",
            "height":       0,
            "ext":          best.get("ext") or "m4a",
            "filesize":     sz,
            "filesize_str": _fmt_size(sz),
            "has_audio":    True,
            "type":         "audio",
        })

    return result


# ── Routes ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/healthz")
def healthz():
    return jsonify({"status": "ok", "service": "VideoNeste"})


@app.route("/lang/<path:filename>")
def serve_lang(filename):
    """Serve lang/*.json files — needed because static/ folder is separate."""
    return send_from_directory(os.path.join(_APP_DIR, "lang"), filename,
                               mimetype="application/json")


@app.route("/api/download", methods=["POST"])
def api_download():
    """Extract video info: title, thumbnail, all available formats."""
    body = request.get_json(silent=True) or {}
    url  = str(body.get("url", "")).strip()
    if not url:
        return jsonify(_err("Please enter a video URL.")), 400
    if not url.startswith(("http://", "https://")):
        return jsonify(_err("Invalid URL — must start with http:// or https://")), 400

    try:
        import yt_dlp
        opts = _base_ydl_opts()
        opts["skip_download"] = True

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = _parse_formats(info)
        if not formats:
            # fallback: top-level url
            if info.get("url"):
                formats = [{
                    "format_id": "best", "label": "Best",
                    "height": 0, "ext": info.get("ext") or "mp4",
                    "filesize": None, "filesize_str": None,
                    "has_audio": True, "type": "video",
                }]
            else:
                return jsonify(_err("No downloadable formats found.")), 400

        return jsonify({
            "success":   True,
            "title":     (info.get("title") or "")[:300],
            "thumbnail": info.get("thumbnail"),
            "duration":  _safe_int(info.get("duration")),
            "uploader":  (info.get("uploader") or info.get("channel") or "")[:200],
            "platform":  info.get("extractor_key") or info.get("extractor"),
            "formats":   formats,
        })
    except Exception as exc:
        return jsonify(_classify(str(exc))), 400


@app.route("/api/formats", methods=["POST"])
def api_formats():
    """Identical to /api/download — returns full format list."""
    return api_download()


@app.route("/api/preview", methods=["POST"])
def api_preview():
    """Return a direct-stream URL suitable for HTML5 <video>."""
    body = request.get_json(silent=True) or {}
    url  = str(body.get("url", "")).strip()
    if not url:
        return jsonify(_err("URL required")), 400

    try:
        import yt_dlp
        opts = _base_ydl_opts()
        opts["skip_download"] = True
        opts["format"] = "best[height<=720][ext=mp4]/best[height<=720]/best"

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        stream_url: str | None = info.get("url")
        if not stream_url:
            for f in reversed(info.get("formats") or []):
                vcodec = (f.get("vcodec") or "none").lower()
                if f.get("url") and vcodec not in ("none", ""):
                    h = f.get("height") or 9999
                    if h <= 720:
                        stream_url = f["url"]
                        break

        return jsonify({
            "success":    True,
            "stream_url": stream_url,
            "thumbnail":  info.get("thumbnail"),
            "title":      (info.get("title") or "")[:300],
            "duration":   _safe_int(info.get("duration")),
        })
    except Exception as exc:
        return jsonify({
            "success":    False,
            "stream_url": None,
            "thumbnail":  None,
            "error":      str(exc),
        }), 200  # 200 so JS can read the body


@app.route("/download")
def download_stream():
    """
    Streaming download — pipes yt-dlp stdout directly to the browser.
    No file is ever written to disk.

    Query params:
        url     — Video URL (required)
        format  — yt-dlp format code (default: best)
        ext     — Expected file extension (default: mp4)
        title   — Filename hint (default: VideoNeste)
    """
    url   = request.args.get("url", "").strip()
    fmt   = request.args.get("format", "best")
    ext   = request.args.get("ext",    "mp4")
    title = request.args.get("title",  "VideoNeste")

    if not url or not url.startswith(("http://", "https://")):
        return jsonify({"error": "Invalid URL"}), 400

    safe  = "".join(c if c.isalnum() or c in " ._-" else "_" for c in title).strip("_")
    fname = f"{safe[:60] or 'VideoNeste'}.{ext}"

    def generate():
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--no-playlist",
            "--output",  "-",
            "--format",  fmt,
            "--quiet",
            "--no-warnings",
            "--http-header", f"User-Agent:{_USER_AGENT}",
        ]
        if _COOKIE_FILE:
            cmd += ["--cookies", _COOKIE_FILE]
        proxy = os.environ.get("PROXY") or os.environ.get("HTTP_PROXY")
        if proxy:
            cmd += ["--proxy", proxy]
        cmd.append(url)

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            while True:
                chunk = proc.stdout.read(65536)
                if not chunk:
                    break
                yield chunk
        except GeneratorExit:
            proc.kill()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    _MIME = {
        "mp4": "video/mp4", "webm": "video/webm",
        "mkv": "video/x-matroska", "mov": "video/quicktime",
        "m4a": "audio/mp4",  "mp3": "audio/mpeg",
        "ogg": "audio/ogg",  "flac": "audio/flac",
    }
    return Response(
        stream_with_context(generate()),
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "Content-Type":        _MIME.get(ext, "application/octet-stream"),
            "X-Accel-Buffering":   "no",
            "Cache-Control":       "no-cache",
        },
    )


@app.route("/api/download-file")
def download_file_redirect():
    """Legacy: redirect to a direct CDN URL."""
    url = request.args.get("url", "").strip()
    if not url or not url.startswith(("http://", "https://")):
        return jsonify({"error": "Invalid URL"}), 400
    return redirect(url, code=302)


@app.errorhandler(404)
def not_found(_):
    return render_template("index.html"), 200


# ── Dev entry-point (Gunicorn ignores this block) ─────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
