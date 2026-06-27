"""
VideoNeste — Universal video downloader (Flask + yt-dlp + Invidious fallback)

Works on Render without any environment variables required for basic operation.

── How YouTube works on Render ───────────────────────────────────────────────
  Render's IP ranges are blocked by YouTube.  VideoNeste solves this by:
  1. Trying yt-dlp normally (works for TikTok, Instagram, Twitter, etc.).
  2. If yt-dlp fails with a login/bot error on a YouTube URL, falling back
     to the Invidious public API — a privacy-respecting YouTube frontend that
     proxies video metadata and stream URLs from YouTube servers.
  3. Trying multiple Invidious instances in sequence until one responds.

── Optional environment variables ────────────────────────────────────────────
  COOKIES_BASE64 — base64-encoded Netscape cookie file for age-gated content.
  PROXY          — HTTP/SOCKS proxy URL for geo-restricted content.
"""
import os
import re
import sys
import atexit
import base64
import subprocess
import tempfile
import time

import requests as _req

from flask import (
    Flask, request, jsonify, render_template,
    redirect, Response, stream_with_context, send_from_directory,
)
from flask_cors import CORS

# ── App setup ─────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="templates", static_folder="static")
CORS(app, resources={r"/api/*": {"origins": "*"}, r"/download": {"origins": "*"}})

_APP_DIR    = os.path.dirname(os.path.abspath(__file__))
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# ── Invidious — public YouTube API mirrors ────────────────────────────
# These are community-run Invidious instances. VideoNeste tries each in
# order; if one is down the next is tried automatically.
_INVIDIOUS_INSTANCES = [
    "https://inv.nadeko.net",
    "https://yewtu.be",
    "https://vid.puffyan.us",
    "https://invidious.flokinet.to",
    "https://invidious.kavin.rocks",
    "https://iv.melmac.space",
    "https://invidious.snopyta.org",
    "https://invidio.xamh.de",
    "https://invidious.nerdvpn.de",
    "https://ytb.trom.tf",
    "https://inv.riverside.rocks",
    "https://invidious.protokolla.fi",
]

# Regex to extract YouTube video ID from any YouTube URL form
_YT_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:[^&]*&)*v=|shorts/|embed/)|youtu\.be/)"
    r"([a-zA-Z0-9_-]{11})"
)

def _extract_yt_id(url: str) -> str | None:
    m = _YT_RE.search(url)
    return m.group(1) if m else None

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

# ── Generic helpers ───────────────────────────────────────────────────

def _err(msg: str, code: str | None = None) -> dict:
    r: dict = {"success": False, "error": msg}
    if code:
        r["code"] = code
    return r

def _classify_ytdlp(raw: str) -> dict:
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

def _is_ytdlp_login_err(raw: str) -> bool:
    """Returns True if yt-dlp failed because YouTube blocked the request."""
    e = raw.lower()
    return any(kw in e for kw in (
        "login required", "sign in", "bot", "private",
        "confirm your age", "requires authentication",
        "http error 403", "http error 429", "precondition",
    ))

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

def _qlabel_to_height(ql: str) -> int:
    m = re.match(r"(\d+)p", ql or "")
    return int(m.group(1)) if m else 0

# ── yt-dlp format parser ───────────────────────────────────────────────

def _parse_ytdlp_formats(info: dict) -> list:
    fmts   = info.get("formats") or []
    combined: list = []
    audios:   list = []

    for f in fmts:
        url    = f.get("url") or f.get("manifest_url")
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
        h = f.get("height") or 0
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
            "direct_url":   None,
        })
        if len(result) >= 8:
            break

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
            "direct_url":   None,
        })

    return result

# ── Invidious fetcher ─────────────────────────────────────────────────

def _fetch_invidious(video_id: str) -> tuple:
    """
    Query Invidious instances in order.
    Returns (data_dict, instance_base_url) or (None, None).
    """
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept":     "application/json",
    }
    for base in _INVIDIOUS_INSTANCES:
        try:
            r = _req.get(
                f"{base}/api/v1/videos/{video_id}",
                headers=headers,
                timeout=9,
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("title"):
                    print(f"[VideoNeste] Invidious OK: {base}")
                    return data, base
        except Exception as exc:
            print(f"[VideoNeste] Invidious {base} failed: {exc}")
            continue
    return None, None

def _parse_invidious(data: dict) -> dict:
    """Convert Invidious API response → VideoNeste standard result dict."""

    # Best thumbnail
    thumbs = data.get("videoThumbnails") or []
    thumb  = None
    for pref in ("maxresdefault", "maxres", "sddefault", "high", "medium", "default"):
        for t in thumbs:
            if (t.get("quality") == pref or pref in (t.get("url") or "")) and t.get("url"):
                thumb = t["url"]
                break
        if thumb:
            break
    if not thumb and thumbs:
        thumb = thumbs[-1].get("url")

    formats: list = []
    seen_h:  set  = set()

    # ── formatStreams: combined video+audio (best for direct download) ──
    for f in data.get("formatStreams") or []:
        url = f.get("url")
        if not url:
            continue
        ql = f.get("qualityLabel") or f.get("quality") or "best"
        h  = _qlabel_to_height(ql)
        if h > 0 and h in seen_h:
            continue
        seen_h.add(h)
        formats.append({
            "format_id":    str(f.get("itag", "fs")),
            "label":        _quality_label(h) if h else ql,
            "height":       h,
            "ext":          f.get("container") or "mp4",
            "filesize":     None,
            "filesize_str": None,
            "has_audio":    True,
            "type":         "video",
            "direct_url":   url,   # served via /download?direct_url=...
        })

    # ── adaptiveFormats: video-only for 1080p+ ──────────────────────────
    adaptive = sorted(
        data.get("adaptiveFormats") or [],
        key=lambda x: x.get("bitrate") or 0,
        reverse=True,
    )
    for f in adaptive:
        ftype = (f.get("type") or "")
        if not ftype.startswith("video/"):
            continue
        url = f.get("url")
        if not url:
            continue
        ql = f.get("qualityLabel") or f.get("quality") or ""
        h  = _qlabel_to_height(ql)
        if h <= 720 or (h > 0 and h in seen_h):
            continue
        seen_h.add(h)
        container = "webm" if "webm" in ftype else "mp4"
        sz = _safe_int(f.get("contentLength"))
        formats.append({
            "format_id":    str(f.get("itag", "ad")),
            "label":        _quality_label(h),
            "height":       h,
            "ext":          container,
            "filesize":     sz,
            "filesize_str": _fmt_size(sz),
            "has_audio":    False,
            "type":         "video",
            "direct_url":   url,
        })

    # ── Best audio ──────────────────────────────────────────────────────
    for f in adaptive:
        ftype = (f.get("type") or "")
        if ftype.startswith("audio/") and f.get("url"):
            sz = _safe_int(f.get("contentLength"))
            formats.append({
                "format_id":    str(f.get("itag", "ba")),
                "label":        "Best Audio",
                "height":       0,
                "ext":          "m4a",
                "filesize":     sz,
                "filesize_str": _fmt_size(sz),
                "has_audio":    True,
                "type":         "audio",
                "direct_url":   f["url"],
            })
            break

    # Sort: video by height desc, audio last
    formats.sort(key=lambda x: (0 if x["type"] == "audio" else 1, -(x["height"] or 0)))
    # Re-sort: highest-height first, then audio
    vid_fmts  = sorted([f for f in formats if f["type"] == "video"],
                       key=lambda x: -(x["height"] or 0))
    aud_fmts  = [f for f in formats if f["type"] == "audio"]
    formats   = vid_fmts + aud_fmts

    return {
        "success":   True,
        "title":     (data.get("title") or "")[:300],
        "thumbnail": thumb,
        "duration":  _safe_int(data.get("lengthSeconds")),
        "uploader":  (data.get("author") or "")[:200],
        "platform":  "YouTube",
        "formats":   formats,
        "source":    "invidious",
    }

# ── Core extraction logic ─────────────────────────────────────────────

def _extract_info(url: str) -> dict:
    """
    Main extraction pipeline:
      1. yt-dlp (works for 1800+ platforms).
      2. If YouTube AND yt-dlp fails → Invidious API.
      3. If all Invidious instances fail → structured error.
    """
    ytdlp_err: str | None = None

    # ── 1. Try yt-dlp ──────────────────────────────────────────────────
    try:
        import yt_dlp
        opts = _base_ydl_opts()
        opts["skip_download"] = True
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        fmts = _parse_ytdlp_formats(info)
        if not fmts and info.get("url"):
            fmts = [{
                "format_id": "best", "label": "Best",
                "height": 0, "ext": info.get("ext") or "mp4",
                "filesize": None, "filesize_str": None,
                "has_audio": True, "type": "video", "direct_url": None,
            }]
        if fmts:
            return {
                "success":   True,
                "title":     (info.get("title") or "")[:300],
                "thumbnail": info.get("thumbnail"),
                "duration":  _safe_int(info.get("duration")),
                "uploader":  (info.get("uploader") or info.get("channel") or "")[:200],
                "platform":  info.get("extractor_key") or info.get("extractor"),
                "formats":   fmts,
                "source":    "ytdlp",
            }
    except Exception as exc:
        ytdlp_err = str(exc)

    # ── 2. YouTube fallback: Invidious ─────────────────────────────────
    yt_id = _extract_yt_id(url)
    if yt_id:
        data, _inst = _fetch_invidious(yt_id)
        if data:
            return _parse_invidious(data)
        # All instances failed
        return _err(
            "YouTube is currently unavailable. "
            "All Invidious proxy servers are down. Please try again later.",
            code="invidious_unavailable",
        )

    # ── 3. Non-YouTube yt-dlp failure ─────────────────────────────────
    return _classify_ytdlp(ytdlp_err or "unknown error")


# ── Routes ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/healthz")
def healthz():
    return jsonify({"status": "ok", "service": "VideoNeste"})

@app.route("/lang/<path:filename>")
def serve_lang(filename):
    return send_from_directory(os.path.join(_APP_DIR, "lang"), filename,
                               mimetype="application/json")

@app.route("/api/download", methods=["POST"])
def api_download():
    body = request.get_json(silent=True) or {}
    url  = str(body.get("url", "")).strip()
    if not url:
        return jsonify(_err("Please enter a video URL.")), 400
    if not url.startswith(("http://", "https://")):
        return jsonify(_err("Invalid URL — must start with http:// or https://")), 400

    result = _extract_info(url)
    status = 200 if result.get("success") else 400
    if result.get("code") == "invidious_unavailable":
        status = 503
    return jsonify(result), status

@app.route("/api/formats", methods=["POST"])
def api_formats():
    return api_download()

@app.route("/api/preview", methods=["POST"])
def api_preview():
    """
    Return a direct stream URL for in-browser HTML5 preview.
    For YouTube: uses Invidious to get a 720p or best available stream.
    For others:  uses yt-dlp.
    """
    body = request.get_json(silent=True) or {}
    url  = str(body.get("url", "")).strip()
    if not url:
        return jsonify(_err("URL required")), 400

    # ── YouTube via Invidious ──────────────────────────────────────────
    yt_id = _extract_yt_id(url)
    if yt_id:
        data, _inst = _fetch_invidious(yt_id)
        if data:
            stream_url: str | None = None
            for f in data.get("formatStreams") or []:
                ql = f.get("qualityLabel", "")
                if "720" in ql and f.get("url"):
                    stream_url = f["url"]
                    break
            if not stream_url:
                for f in data.get("formatStreams") or []:
                    if f.get("url"):
                        stream_url = f["url"]
                        break

            thumbs = data.get("videoThumbnails") or []
            thumb  = thumbs[0].get("url") if thumbs else None

            return jsonify({
                "success":    True,
                "stream_url": stream_url,
                "thumbnail":  thumb,
                "title":      (data.get("title") or "")[:300],
                "duration":   _safe_int(data.get("lengthSeconds")),
            })
        # Invidious down — return thumbnail from YouTube CDN directly
        return jsonify({
            "success":    True,
            "stream_url": None,
            "thumbnail":  f"https://i.ytimg.com/vi/{yt_id}/hqdefault.jpg",
            "title":      "",
            "duration":   None,
        })

    # ── Non-YouTube via yt-dlp ─────────────────────────────────────────
    try:
        import yt_dlp
        opts = _base_ydl_opts()
        opts["skip_download"] = True
        opts["format"] = "best[height<=720][ext=mp4]/best[height<=720]/best"
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        stream_url = info.get("url")
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
        }), 200


@app.route("/download")
def download_stream():
    """
    Streaming download endpoint. Two modes:

    A. direct_url is set (Invidious format):
       Proxies the remote CDN URL via requests streaming. No yt-dlp used.

    B. direct_url not set (yt-dlp format):
       Runs yt-dlp with -o - to pipe stdout to the browser.
    """
    url        = request.args.get("url",        "").strip()
    fmt        = request.args.get("format",     "best")
    ext        = request.args.get("ext",        "mp4")
    title      = request.args.get("title",      "VideoNeste")
    direct_url = request.args.get("direct_url", "").strip()

    if not url or not url.startswith(("http://", "https://")):
        return jsonify({"error": "Invalid URL"}), 400

    safe  = "".join(c if c.isalnum() or c in " ._-" else "_" for c in title).strip("_")
    fname = f"{safe[:60] or 'VideoNeste'}.{ext}"

    _MIME = {
        "mp4":  "video/mp4",
        "webm": "video/webm",
        "mkv":  "video/x-matroska",
        "mov":  "video/quicktime",
        "m4a":  "audio/mp4",
        "mp3":  "audio/mpeg",
        "ogg":  "audio/ogg",
        "flac": "audio/flac",
    }
    mime = _MIME.get(ext, "application/octet-stream")

    # ── Mode A: direct CDN proxy (Invidious) ───────────────────────────
    if direct_url and direct_url.startswith(("http://", "https://")):
        def gen_direct():
            try:
                r = _req.get(
                    direct_url,
                    stream=True,
                    headers={"User-Agent": _USER_AGENT},
                    timeout=30,
                )
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        yield chunk
            except Exception as exc:
                print(f"[VideoNeste] Direct stream error: {exc}")

        return Response(
            stream_with_context(gen_direct()),
            headers={
                "Content-Disposition": f'attachment; filename="{fname}"',
                "Content-Type":        mime,
                "X-Accel-Buffering":   "no",
                "Cache-Control":       "no-cache",
            },
        )

    # ── Mode B: yt-dlp stdout pipe ─────────────────────────────────────
    def gen_ytdlp():
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

    return Response(
        stream_with_context(gen_ytdlp()),
        headers={
            "Content-Disposition": f'attachment; filename="{fname}"',
            "Content-Type":        mime,
            "X-Accel-Buffering":   "no",
            "Cache-Control":       "no-cache",
        },
    )


@app.route("/api/download-file")
def download_file_redirect():
    url = request.args.get("url", "").strip()
    if not url or not url.startswith(("http://", "https://")):
        return jsonify({"error": "Invalid URL"}), 400
    return redirect(url, code=302)


@app.errorhandler(404)
def not_found(_):
    return render_template("index.html"), 200


# ── Dev entry-point ───────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
