import { useState, useCallback, useEffect, useRef } from "react";
import confetti from "canvas-confetti";
import { useExtractVideo } from "@workspace/api-client-react";
import { Loader2, Download, Video, Music, AlertTriangle, ArrowRight, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

// ── Download helper ────────────────────────────────────────────────────
// Routes download clicks through /api/download-file which performs a
// 302 redirect to the actual CDN URL, giving the browser a clean download.
function buildDownloadUrl(cdnUrl: string): string {
  return `/api/download-file?url=${encodeURIComponent(cdnUrl)}`;
}

// ── Confetti ───────────────────────────────────────────────────────────
function fireConfetti() {
  const count  = 180;
  const origin = { y: 0.7 };
  const fire   = (particleRatio: number, opts: confetti.Options) =>
    confetti({ origin, count: Math.floor(count * particleRatio), ...opts });

  fire(0.25, { spread: 26, startVelocity: 55 });
  fire(0.2,  { spread: 60 });
  fire(0.35, { spread: 100, decay: 0.91, scalar: 0.8 });
  fire(0.1,  { spread: 120, startVelocity: 25, decay: 0.92, scalar: 1.2 });
  fire(0.1,  { spread: 120, startVelocity: 45 });
}

export default function Home() {
  const [url, setUrl]           = useState("");
  const [errorPopup, setErrorPopup] = useState<string | null>(null);
  const prevSuccessRef          = useRef(false);
  const extractVideo            = useExtractVideo();

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setUrl(e.target.value);
    if (extractVideo.data || extractVideo.isError) {
      extractVideo.reset();
      setErrorPopup(null);
    }
  }, [extractVideo]);

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) return;
    setErrorPopup(null);
    extractVideo.mutate({ data: { url: trimmed } });
  }, [url, extractVideo]);

  // ── Fire confetti once on first success ───────────────────────────
  useEffect(() => {
    const isSuccess = !!(extractVideo.data?.success && !extractVideo.isPending);
    if (isSuccess && !prevSuccessRef.current) {
      fireConfetti();
    }
    prevSuccessRef.current = isSuccess;
  }, [extractVideo.data?.success, extractVideo.isPending]);

  // ── Show error popup when extraction fails ─────────────────────────
  useEffect(() => {
    if (!extractVideo.isPending) {
      if (extractVideo.isError) {
        setErrorPopup("خطأ في الشبكة أو الخادم غير متاح. يرجى المحاولة مجدداً.");
      } else if (extractVideo.data && !extractVideo.data.success) {
        setErrorPopup(extractVideo.data.error || "تعذّر استخراج الفيديو من هذا الرابط.");
      }
    }
  }, [extractVideo.data, extractVideo.isError, extractVideo.isPending]);

  const formatDuration = (seconds?: number | null) => {
    if (!seconds) return "";
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
    return `${m}:${s.toString().padStart(2, "0")}`;
  };

  const formatSize = (bytes?: number | null) => {
    if (!bytes) return "";
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
  };

  const getFormatIcon = (type: string) => {
    if (type.includes("audio")) return <Music className="w-4 h-4 ml-2" />;
    return <Video className="w-4 h-4 ml-2" />;
  };

  const isSuccess = !!(extractVideo.data?.success && !extractVideo.isPending);

  return (
    <div className="min-h-[100dvh] w-full flex flex-col items-center py-12 px-4 md:px-8 lg:px-12 selection:bg-primary selection:text-primary-foreground">

      {/* ── Error popup (glassmorphism) ─────────────────────────────── */}
      {errorPopup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4" dir="rtl">
          <div
            className="absolute inset-0 bg-background/60 backdrop-blur-sm"
            onClick={() => setErrorPopup(null)}
          />
          <div className="relative w-full max-w-md rounded-2xl border border-destructive/30 bg-destructive/10 backdrop-blur-xl p-6 shadow-2xl animate-in zoom-in-90 fade-in duration-200">
            <button
              onClick={() => setErrorPopup(null)}
              className="absolute top-4 left-4 text-muted-foreground hover:text-foreground transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
            <div className="flex items-start gap-4">
              <AlertTriangle className="w-8 h-8 text-destructive shrink-0 mt-0.5" />
              <div>
                <h3 className="text-lg font-bold text-destructive mb-1">فشل الاستخراج</h3>
                <p className="text-destructive/80 text-sm leading-relaxed">{errorPopup}</p>
              </div>
            </div>
            <Button
              variant="destructive"
              size="sm"
              className="mt-4 w-full"
              onClick={() => setErrorPopup(null)}
            >
              حسناً
            </Button>
          </div>
        </div>
      )}

      <main className="w-full max-w-4xl flex-1 flex flex-col items-center justify-center">

        {/* ── Hero ─────────────────────────────────────────────────── */}
        <div className="w-full text-center space-y-6 mb-12">
          <div className="inline-flex items-center justify-center space-x-3 mb-4">
            <div className="w-12 h-12 bg-primary rounded-xl flex items-center justify-center text-primary-foreground shadow-[0_0_30px_rgba(0,229,255,0.3)]">
              <Download className="w-6 h-6 stroke-[2.5]" />
            </div>
            <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight">Downloader</h1>
          </div>
          <h2
            className="text-4xl md:text-6xl font-extrabold tracking-tighter text-foreground max-w-3xl mx-auto leading-tight"
            dir="auto"
          >
            استخرج وحمّل <span className="text-primary">أي فيديو</span> فوراً.
          </h2>
          <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto" dir="auto">
            الصق أي رابط من أكثر من 1800 منصة. سريع وموثوق وبدون قيود.
            <br className="hidden md:block" />
            <span className="text-sm md:text-base mt-2 inline-block">
              YouTube, TikTok, Instagram, Twitter/X, Facebook, Vimeo وغيرها.
            </span>
          </p>
        </div>

        {/* ── Input form ───────────────────────────────────────────── */}
        <form onSubmit={handleSubmit} className="w-full max-w-3xl mb-12 relative group" dir="auto">
          <div className="absolute -inset-1 bg-gradient-to-r from-primary/30 to-accent/30 rounded-2xl blur-lg opacity-0 group-hover:opacity-100 transition duration-500" />
          <div className="relative flex flex-col sm:flex-row gap-3 bg-card p-2 md:p-3 rounded-2xl border border-border shadow-xl">
            <div className="flex-1 relative flex items-center">
              <Input
                type="url"
                value={url}
                onChange={handleInputChange}
                placeholder="https://youtube.com/watch?v=..."
                className="w-full h-14 bg-transparent border-0 focus-visible:ring-0 text-base md:text-lg px-4 md:px-6 placeholder:text-muted-foreground"
                data-testid="input-url"
              />
            </div>
            <Button
              type="submit"
              disabled={extractVideo.isPending || !url.trim()}
              className="h-14 px-8 text-base font-bold tracking-wide rounded-xl shadow-[0_0_20px_rgba(0,229,255,0.2)] hover:shadow-[0_0_30px_rgba(0,229,255,0.4)] transition-all"
              data-testid="button-extract"
            >
              {extractVideo.isPending ? (
                <>
                  <Loader2 className="w-5 h-5 ml-2 animate-spin" />
                  جارٍ الاستخراج...
                </>
              ) : (
                <>
                  استخراج <ArrowRight className="w-5 h-5 mr-2 rotate-180" />
                </>
              )}
            </Button>
          </div>
        </form>

        {/* ── Loading ───────────────────────────────────────────────── */}
        {extractVideo.isPending && (
          <div className="w-full max-w-3xl flex flex-col items-center justify-center py-12 space-y-4 animate-in fade-in zoom-in duration-300">
            <Loader2 className="w-12 h-12 text-primary animate-spin" />
            <p className="text-muted-foreground text-lg text-center" dir="rtl">
              يتم استخراج الروابط من أكثر من 1800 منصة...
            </p>
          </div>
        )}

        {/* ── Success card ─────────────────────────────────────────── */}
        {isSuccess && (
          <div className="w-full max-w-4xl bg-card border border-border rounded-3xl overflow-hidden shadow-2xl animate-in slide-in-from-bottom-8 fade-in duration-500">
            <div className="flex flex-col md:flex-row">

              {/* Thumbnail */}
              <div className="w-full md:w-2/5 aspect-video md:aspect-auto bg-muted relative overflow-hidden shrink-0 group">
                {extractVideo.data!.thumbnail ? (
                  <img
                    src={extractVideo.data!.thumbnail}
                    alt={extractVideo.data!.title || "صورة مصغرة للفيديو"}
                    className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                  />
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center text-muted-foreground">
                    <Video className="w-12 h-12 mb-2 opacity-50" />
                    <span className="text-sm">لا توجد صورة مصغرة</span>
                  </div>
                )}
                {extractVideo.data!.duration && (
                  <div className="absolute bottom-3 right-3 bg-background/90 backdrop-blur text-foreground px-2.5 py-1 text-sm font-mono font-bold rounded-md">
                    {formatDuration(extractVideo.data!.duration)}
                  </div>
                )}
              </div>

              {/* Content */}
              <div className="flex-1 p-6 md:p-8 flex flex-col" dir="rtl">
                <div className="mb-6">
                  {extractVideo.data!.platform && (
                    <div className="inline-block px-3 py-1 bg-secondary text-secondary-foreground text-xs font-bold uppercase tracking-wider rounded-full mb-3">
                      {extractVideo.data!.platform}
                    </div>
                  )}
                  <h3
                    className="text-2xl font-bold leading-tight mb-2 line-clamp-2"
                    title={extractVideo.data!.title || "عنوان غير متاح"}
                  >
                    {extractVideo.data!.title || "عنوان غير متاح"}
                  </h3>
                  {extractVideo.data!.uploader && (
                    <p className="text-muted-foreground flex items-center gap-2">
                      <span className="opacity-70">بواسطة</span>
                      <span className="font-semibold text-foreground">{extractVideo.data!.uploader}</span>
                    </p>
                  )}
                </div>

                {/* Format buttons */}
                <div className="space-y-4 mt-auto">
                  <h4 className="text-sm font-bold text-muted-foreground uppercase tracking-wider border-b border-border pb-2">
                    الصيغ المتاحة للتحميل
                  </h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[300px] overflow-y-auto pl-2 custom-scrollbar">
                    {extractVideo.data!.formats?.map((format, i) => (
                      <a
                        key={i}
                        href={buildDownloadUrl(format.url)}
                        target="_blank"
                        rel="noopener noreferrer"
                        download
                        className="flex items-center justify-between p-3 rounded-xl bg-secondary/50 hover:bg-primary/20 border border-transparent hover:border-primary/30 transition-all group/btn"
                        data-testid={`link-download-${i}`}
                      >
                        <div className="flex items-center truncate gap-2">
                          <span className="text-primary group-hover/btn:scale-110 transition-transform">
                            {getFormatIcon(format.type)}
                          </span>
                          <span className="font-bold text-sm truncate">
                            {format.quality}
                            {format.ext && (
                              <span className="uppercase text-muted-foreground mr-1 text-xs">
                                ({format.ext})
                              </span>
                            )}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          {format.filesize ? (
                            <span className="text-xs font-mono text-muted-foreground">
                              {formatSize(format.filesize)}
                            </span>
                          ) : null}
                          <Download className="w-3.5 h-3.5 text-muted-foreground group-hover/btn:text-primary transition-colors" />
                        </div>
                      </a>
                    ))}
                    {(!extractVideo.data!.formats || extractVideo.data!.formats.length === 0) && (
                      <p className="text-muted-foreground text-sm py-4" dir="rtl">
                        لم يتم العثور على صيغ متاحة للتحميل.
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* ── Footer ───────────────────────────────────────────────────── */}
      <footer className="w-full max-w-4xl mt-16 pt-8 border-t border-border text-center pb-8" dir="rtl">
        <div className="bg-secondary/30 rounded-2xl p-6 backdrop-blur-sm">
          <p className="text-sm text-muted-foreground leading-relaxed max-w-3xl mx-auto">
            يدعم أكثر من 1800 موقع بما فيها YouTube, TikTok, Facebook, Instagram, Twitter/X,
            Vimeo, Dailymotion, Twitch, Reddit, Bilibili, Rumble, VK وغيرها.
            <strong className="text-foreground mr-1 font-semibold">
              لا يدعم المحتوى المحمي بـ DRM (مثل Netflix وDisney+).
            </strong>
          </p>
        </div>
      </footer>
    </div>
  );
}
