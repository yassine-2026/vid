import os
import sys
import subprocess
import json
import re
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

def format_error(msg: str) -> dict:
    return {"success": False, "error": msg}

def classify_error(error_str: str) -> str:
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

def build_ydl_opts() -> dict:
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

    if os.path.isfile("cookies.txt"):
        opts["cookiefile"] = "cookies.txt"

    return opts

def safe_int(val):
    try:
        return int(val) if val is not None else None
    except (TypeError, ValueError):
        return None

def safe_str(val):
    if val is None:
        return None
    return str(val)[:500]

def extract_video_info(url: str) -> dict:
    try:
        import yt_dlp
    except ImportError:
        return format_error("yt-dlp غير مثبت على الخادم.")

    opts = build_ydl_opts()

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        return format_error(classify_error(str(e)))
    except yt_dlp.utils.ExtractorError as e:
        return format_error(classify_error(str(e)))
    except Exception as e:
        err = str(e).lower()
        if "connection" in err or "network" in err or "timeout" in err:
            return format_error("خطأ في الاتصال بالشبكة. يرجى المحاولة مرة أخرى.")
        return format_error(f"حدث خطأ غير متوقع: {str(e)[:150]}")

    if info is None:
        return format_error("لم يتم العثور على معلومات الفيديو.")

    title = safe_str(info.get("title"))
    thumbnail = safe_str(info.get("thumbnail"))
    duration = safe_int(info.get("duration"))
    uploader = safe_str(info.get("uploader") or info.get("channel") or info.get("creator"))
    platform = safe_str(info.get("extractor_key") or info.get("extractor"))

    formats_raw = info.get("formats") or []
    formats = []

    best_video_url = None
    best_video_quality = None
    best_video_ext = None

    best_audio_url = None
    best_audio_ext = None
    best_audio_tbr = 0

    for f in formats_raw:
        furl = f.get("url")
        if not furl:
            continue

        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        height = f.get("height")
        tbr = f.get("tbr") or 0
        ext = f.get("ext", "")

        has_video = vcodec not in (None, "none", "")
        has_audio = acodec not in (None, "none", "")

        if has_video and has_audio:
            quality = f"{height}p" if height else "best"
            if best_video_url is None or (height and (best_video_quality is None or height > int(best_video_quality.replace("p", "") or 0))):
                best_video_url = furl
                best_video_quality = quality
                best_video_ext = ext

        elif has_audio and not has_video:
            if tbr > best_audio_tbr:
                best_audio_tbr = tbr
                best_audio_url = furl
                best_audio_ext = ext

    if not best_video_url:
        direct_url = info.get("url")
        if direct_url:
            best_video_url = direct_url
            best_video_quality = "best"
            best_video_ext = info.get("ext", "mp4")

    if best_video_url:
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

    if not formats:
        return format_error("لم يتم العثور على روابط تحميل متاحة لهذا الفيديو.")

    return {
        "success": True,
        "title": title,
        "thumbnail": thumbnail,
        "duration": duration,
        "uploader": uploader,
        "platform": platform,
        "formats": formats,
    }

@app.route("/api/healthz", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"})

@app.route("/api/download", methods=["POST"])
def download():
    data = request.get_json(silent=True)
    if not data or not data.get("url"):
        return jsonify(format_error("الرجاء إدخال رابط الفيديو.")), 400

    url = str(data["url"]).strip()
    if not url.startswith(("http://", "https://")):
        return jsonify(format_error("الرابط غير صالح. يجب أن يبدأ بـ http:// أو https://")), 400

    result = extract_video_info(url)
    status = 200 if result.get("success") else 400
    return jsonify(result), status

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
