#!/usr/bin/env bash
# =====================================================================
#  Render Build Script — Video Downloader
#  Runs inside Render's Debian-based build container (root user).
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
    echo "    Node.js ${NODE_MAJOR} found — installing Node.js 20 via NodeSource..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi
echo "    node: $(node --version)"

# ── 2. pnpm ───────────────────────────────────────────────────────────
# We never use 'npm install -g' because:
#   - It requires npm global write permissions (unreliable as root in some envs)
#   - '--silent' hides the real error making failures invisible
# Strategy: Corepack (bundled with Node 16.9+) first, standalone installer fallback.
echo ""
echo ">>> [2/5] Installing pnpm@10.26.1..."

# --- Attempt 1: Corepack ---
# 'corepack enable pnpm' creates a pnpm shim in the system bin directory.
# On Render (Debian, root, writable /usr/local/bin) this always succeeds.
# On NixOS (read-only /nix/store) this may fail — hence the '|| true'.
corepack enable pnpm 2>&1 || true

# 'corepack prepare --activate' downloads the exact pnpm version from the
# npm registry and marks it as active. Works independently of 'enable'.
corepack prepare pnpm@10.26.1 --activate 2>&1 || true

# --- Attempt 2: official standalone installer (fallback) ---
# Runs only if pnpm is still not accessible after the Corepack steps.
if ! command -v pnpm &>/dev/null; then
    echo "    Corepack did not expose pnpm — using official standalone installer..."
    export PNPM_HOME="${HOME}/.local/share/pnpm"
    export PATH="${PNPM_HOME}:${PATH}"
    # PNPM_VERSION env var controls which version the installer fetches.
    curl -fsSL https://get.pnpm.io/install.sh | PNPM_VERSION=10.26.1 sh -
fi

echo "    pnpm: $(pnpm --version)"

# ── 3. Node packages ──────────────────────────────────────────────────
echo ""
echo ">>> [3/5] Installing Node packages (frozen lockfile)..."
# --frozen-lockfile installs exact versions from pnpm-lock.yaml.
# This skips all metadata fetches and bypasses the minimumReleaseAge:1440
# setting in pnpm-workspace.yaml — safe and fast on CI.
pnpm install --frozen-lockfile

# ── 4. Build React frontend ───────────────────────────────────────────
echo ""
echo ">>> [4/5] Building React frontend..."
export PORT=8080
export BASE_PATH=/
export NODE_ENV=production
pnpm --filter @workspace/video-downloader run build

DIST_INDEX="artifacts/video-downloader/dist/public/index.html"
if [ ! -f "$DIST_INDEX" ]; then
    echo "ERROR: $DIST_INDEX not found after build."
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
echo " Build complete — ready to start."
echo "==================================================================="
