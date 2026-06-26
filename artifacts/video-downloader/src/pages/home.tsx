import { useState, useCallback, useRef } from "react";
import { useExtractVideo } from "@workspace/api-client-react";
import { Loader2, Download, Video, Music, AlertTriangle, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function Home() {
  const [url, setUrl] = useState("");
  const extractVideo = useExtractVideo();

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    setUrl(e.target.value);
    if (extractVideo.data || extractVideo.isError) {
      extractVideo.reset();
    }
  }, [extractVideo]);

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) return;
    extractVideo.mutate({ data: { url: url.trim() } });
  }, [url, extractVideo]);

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
    if (type.includes("audio")) return <Music className="w-4 h-4 mr-2" />;
    return <Video className="w-4 h-4 mr-2" />;
  };

  const isError = extractVideo.isError || (extractVideo.data && !extractVideo.data.success);
  const errorMessage = extractVideo.isError 
    ? "Network error or service unavailable. Please try again."
    : extractVideo.data?.error || "Unknown error occurred";

  return (
    <div className="min-h-[100dvh] w-full flex flex-col items-center py-12 px-4 md:px-8 lg:px-12 selection:bg-primary selection:text-primary-foreground">
      <main className="w-full max-w-4xl flex-1 flex flex-col items-center justify-center">
        
        {/* Hero Section */}
        <div className="w-full text-center space-y-6 mb-12">
          <div className="inline-flex items-center justify-center space-x-3 mb-4">
            <div className="w-12 h-12 bg-primary rounded-xl flex items-center justify-center text-primary-foreground shadow-[0_0_30px_rgba(0,229,255,0.3)]">
              <Download className="w-6 h-6 stroke-[2.5]" />
            </div>
            <h1 className="text-3xl md:text-4xl font-extrabold tracking-tight">Downloader</h1>
          </div>
          <h2 className="text-4xl md:text-6xl font-extrabold tracking-tighter text-foreground max-w-3xl mx-auto leading-tight" dir="auto">
            Extract and download <span className="text-primary">any video</span> instantly.
          </h2>
          <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto" dir="auto">
            Paste a link from 1800+ platforms. Fast, confident, and universally supported.
            <br className="hidden md:block" />
            <span className="text-sm md:text-base mt-2 inline-block">حمل أي فيديو برابط واحد فقط. سريع وموثوق.</span>
          </p>
        </div>

        {/* Input Form */}
        <form onSubmit={handleSubmit} className="w-full max-w-3xl mb-12 relative group" dir="auto">
          <div className="absolute -inset-1 bg-gradient-to-r from-primary/30 to-accent/30 rounded-2xl blur-lg opacity-0 group-hover:opacity-100 transition duration-500"></div>
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
                  <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                  Extracting...
                </>
              ) : (
                <>
                  Extract <ArrowRight className="w-5 h-5 ml-2" />
                </>
              )}
            </Button>
          </div>
        </form>

        {/* Loading State */}
        {extractVideo.isPending && (
          <div className="w-full max-w-3xl flex flex-col items-center justify-center py-12 space-y-4 animate-in fade-in zoom-in duration-300">
            <Loader2 className="w-12 h-12 text-primary animate-spin" />
            <p className="text-muted-foreground text-lg text-center" dir="auto">
              Extracting links from 1800+ supported platforms...
            </p>
          </div>
        )}

        {/* Error State */}
        {isError && !extractVideo.isPending && (
          <div className="w-full max-w-3xl bg-destructive/10 border border-destructive/20 rounded-2xl p-6 md:p-8 flex items-start space-x-4 animate-in slide-in-from-bottom-4 fade-in duration-300">
            <AlertTriangle className="w-8 h-8 text-destructive shrink-0 mt-1" />
            <div className="flex-1" dir="auto">
              <h3 className="text-xl font-bold text-destructive mb-2">Extraction Failed</h3>
              <p className="text-destructive/80 text-lg">
                {errorMessage}
              </p>
            </div>
          </div>
        )}

        {/* Success State */}
        {extractVideo.data?.success && !extractVideo.isPending && (
          <div className="w-full max-w-4xl bg-card border border-border rounded-3xl overflow-hidden shadow-2xl animate-in slide-in-from-bottom-8 fade-in duration-500">
            <div className="flex flex-col md:flex-row">
              {/* Thumbnail Area */}
              <div className="w-full md:w-2/5 aspect-video md:aspect-auto bg-muted relative overflow-hidden shrink-0 group">
                {extractVideo.data.thumbnail ? (
                  <img 
                    src={extractVideo.data.thumbnail} 
                    alt={extractVideo.data.title || "Video thumbnail"} 
                    className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                  />
                ) : (
                  <div className="w-full h-full flex flex-col items-center justify-center text-muted-foreground">
                    <Video className="w-12 h-12 mb-2 opacity-50" />
                    <span className="text-sm">No thumbnail available</span>
                  </div>
                )}
                {extractVideo.data.duration && (
                  <div className="absolute bottom-3 right-3 bg-background/90 backdrop-blur text-foreground px-2.5 py-1 text-sm font-mono font-bold rounded-md">
                    {formatDuration(extractVideo.data.duration)}
                  </div>
                )}
              </div>

              {/* Content Area */}
              <div className="flex-1 p-6 md:p-8 flex flex-col" dir="auto">
                <div className="mb-6">
                  {extractVideo.data.platform && (
                    <div className="inline-block px-3 py-1 bg-secondary text-secondary-foreground text-xs font-bold uppercase tracking-wider rounded-full mb-3">
                      {extractVideo.data.platform}
                    </div>
                  )}
                  <h3 className="text-2xl font-bold leading-tight mb-2 line-clamp-2" title={extractVideo.data.title || "Unknown Title"}>
                    {extractVideo.data.title || "Unknown Title"}
                  </h3>
                  {extractVideo.data.uploader && (
                    <p className="text-muted-foreground flex items-center">
                      <span className="opacity-70 mr-2">by</span>
                      <span className="font-semibold text-foreground">{extractVideo.data.uploader}</span>
                    </p>
                  )}
                </div>

                <div className="space-y-4 mt-auto">
                  <h4 className="text-sm font-bold text-muted-foreground uppercase tracking-wider border-b border-border pb-2">Available Formats</h4>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[300px] overflow-y-auto pr-2 custom-scrollbar">
                    {extractVideo.data.formats?.map((format, i) => (
                      <a 
                        key={i}
                        href={format.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center justify-between p-3 rounded-xl bg-secondary/50 hover:bg-primary/20 border border-transparent hover:border-primary/30 transition-all group/btn"
                        data-testid={`link-download-${i}`}
                      >
                        <div className="flex items-center truncate mr-3">
                          <span className="text-primary group-hover/btn:scale-110 transition-transform">
                            {getFormatIcon(format.type)}
                          </span>
                          <span className="font-bold truncate text-sm">
                            {format.quality} {format.ext && <span className="uppercase text-muted-foreground ml-1">({format.ext})</span>}
                          </span>
                        </div>
                        {format.filesize && (
                          <span className="text-xs font-mono text-muted-foreground shrink-0">
                            {formatSize(format.filesize)}
                          </span>
                        )}
                      </a>
                    ))}
                    {(!extractVideo.data.formats || extractVideo.data.formats.length === 0) && (
                      <p className="text-muted-foreground text-sm py-4">No download formats could be extracted.</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="w-full max-w-4xl mt-16 pt-8 border-t border-border text-center pb-8" dir="auto">
        <div className="bg-secondary/30 rounded-2xl p-6 backdrop-blur-sm">
          <p className="text-sm text-muted-foreground leading-relaxed max-w-3xl mx-auto">
            Supports 1800+ websites including YouTube, TikTok, Facebook, Instagram, Twitter/X, Vimeo, Dailymotion, and more. 
            <strong className="text-foreground ml-1 font-semibold">Does not support DRM-protected content (Netflix, etc.).</strong>
          </p>
        </div>
      </footer>
    </div>
  );
}
