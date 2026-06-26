#!/usr/bin/env bash
set -euo pipefail

echo "==================================================================="
echo " Video Downloader — Render Build Script"
echo "==================================================================="

# ── 1. Node.js ────────────────────────────────────────────────────────
echo ""
echo ">>> [1/5] Checking Node.js..."
if command -v node &>/dev/null; then
    echo "    Found: $(node --version)"
else
    echo "    Node.js not found — installing via NodeSource..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
    echo "    Installed: $(node --version)"
fi

# ── 2. pnpm ───────────────────────────────────────────────────────────
echo ""
echo ">>> [2/5] Installing pnpm..."
npm install -g pnpm@9 --silent
echo "    pnpm $(pnpm --version)"

# ── 3. Node packages ──────────────────────────────────────────────────
echo ""
echo ">>> [3/5] Installing Node packages..."
# Use --no-frozen-lockfile because Render's platform may differ slightly
# from the lockfile generated on Replit (same arch: linux-x64-gnu).
pnpm install --no-frozen-lockfile 2>&1

# ── 4. Build React frontend ───────────────────────────────────────────
echo ""
echo ">>> [4/5] Building React frontend..."
export PORT=8080
export BASE_PATH=/
export NODE_ENV=production
pnpm --filter @workspace/video-downloader run build
echo "    Build output:"
ls -lh artifacts/video-downloader/dist/public/ 2>/dev/null || echo "    WARNING: dist/public not found!"

# ── 5. Python packages ────────────────────────────────────────────────
echo ""
echo ">>> [5/5] Installing Python packages..."
pip install --upgrade pip --quiet
pip install -r requirements.txt
echo "    yt-dlp: $(yt-dlp --version 2>/dev/null || python3 -c 'import yt_dlp; print(yt_dlp.version.__version__)')"
echo "    gunicorn: $(gunicorn --version)"

echo ""
echo "==================================================================="
echo " Build complete — ready to start."
echo "==================================================================="
