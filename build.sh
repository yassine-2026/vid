#!/usr/bin/env bash
# =====================================================================
#  Render Build Script — Video Downloader
#  Runs as root inside Render's Debian-based build container.
# =====================================================================
set -euo pipefail

echo "==================================================================="
echo " Video Downloader — Render Build"
echo "==================================================================="

# ── 1. Node.js ────────────────────────────────────────────────────────
echo ""
echo ">>> [1/5] Checking Node.js..."

NODE_MAJOR=0
if command -v node &>/dev/null; then
    NODE_MAJOR=$(node -e "process.stdout.write(String(parseInt(process.versions.node)))" 2>/dev/null || echo "0")
fi

if [ "$NODE_MAJOR" -lt 20 ]; then
    echo "    Node.js ${NODE_MAJOR} is too old or not found — installing Node.js 20 via NodeSource..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi

echo "    node: $(node --version)  |  npm: $(npm --version)"

# ── 2. pnpm ───────────────────────────────────────────────────────────
echo ""
echo ">>> [2/5] Installing pnpm@10 (matches lockfile version)..."
npm install -g pnpm@10 --silent
echo "    pnpm: $(pnpm --version)"

# ── 3. Node packages ──────────────────────────────────────────────────
echo ""
echo ">>> [3/5] Installing Node packages (frozen lockfile)..."
# --frozen-lockfile: exact versions from pnpm-lock.yaml, no metadata fetches,
# bypasses the minimumReleaseAge:1440 check in pnpm-workspace.yaml.
pnpm install --frozen-lockfile

# ── 4. Build React frontend ───────────────────────────────────────────
echo ""
echo ">>> [4/5] Building React frontend..."
export PORT=8080
export BASE_PATH=/
export NODE_ENV=production
pnpm --filter @workspace/video-downloader run build

# Verify output exists
DIST_INDEX="artifacts/video-downloader/dist/public/index.html"
if [ ! -f "$DIST_INDEX" ]; then
    echo "ERROR: $DIST_INDEX not found after build!"
    exit 1
fi
echo "    dist/public: $(ls artifacts/video-downloader/dist/public/)"

# ── 5. Python packages ────────────────────────────────────────────────
echo ""
echo ">>> [5/5] Installing Python packages..."
pip install --upgrade pip --quiet
pip install -r requirements.txt
echo "    flask:    $(python3 -c 'import flask; print(flask.__version__)')"
echo "    yt-dlp:   $(python3 -c 'import yt_dlp; print(yt_dlp.version.__version__)')"
echo "    gunicorn: $(gunicorn --version)"

echo ""
echo "==================================================================="
echo " Build complete."
echo "==================================================================="
