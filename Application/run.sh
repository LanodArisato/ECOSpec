#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  ECOSpec — Install & Run Script for Raspberry Pi 5
#  Run this script once to install dependencies, then again to launch.
#
#  Usage:
#    chmod +x run.sh
#    ./run.sh          → install deps (first time) + launch app
#    ./run.sh --run    → launch app only (skip install check)
# ─────────────────────────────────────────────────────────────────

set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON=python3
PIP=pip3

echo ""
echo "  ╔══════════════════════════════════╗"
echo "  ║         ECOSpec Launcher         ║"
echo "  ║   Raman · Microplastic · Pi 5    ║"
echo "  ╚══════════════════════════════════╝"
echo ""

# ── Dependency check / install ──────────────────────────────────
if [[ "$1" != "--run" ]]; then
    echo "[*] Checking system dependencies..."

    # GTK WebKit (required by PyWebView GTK backend)
    if ! dpkg -s python3-gi gir1.2-webkit2-4.1 &>/dev/null; then
        echo "[*] Installing GTK/WebKit system packages..."
        sudo apt-get update -qq
        sudo apt-get install -y \
            python3-gi \
            python3-gi-cairo \
            gir1.2-gtk-3.0 \
            gir1.2-webkit2-4.1 \
            libgtk-3-0 \
            libwebkit2gtk-4.1-0 \
            python3-pip
        echo "[✓] System packages installed."
    else
        echo "[✓] GTK/WebKit already installed."
    fi

    # PyWebView Python package
    if ! $PYTHON -c "import webview" &>/dev/null; then
        echo "[*] Installing pywebview..."
        $PIP install pywebview --break-system-packages
        echo "[✓] pywebview installed."
    else
        echo "[✓] pywebview already installed."
    fi
fi

# ── Touch display environment ────────────────────────────────────
# Enable touch input and set display target
export DISPLAY="${DISPLAY:-:0}"
export GDK_BACKEND=x11          # Use X11 backend (stable on Pi OS)
export WEBKIT_DISABLE_COMPOSITING_MODE=1   # Improves performance on Pi

# ── Launch ───────────────────────────────────────────────────────
echo "[*] Launching ECOSpec..."
cd "$APP_DIR"
exec $PYTHON ecospec.py
