#!/usr/bin/env bash
# bundle-python.sh — 下载 python-build-standalone 并安装 Temu 依赖
# 支持 macOS arm64 (Apple Silicon) 和 x64 (Intel)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ELECTRON_APP_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON_VERSION="3.12.9"
PYTHON_RELEASE="20250317"  # cpython-3.12.9+20250317
DEST_DIR="$ELECTRON_APP_DIR/resources/python"

# ── Detect arch ──────────────────────────────────────────────────────────────
ARCH=$(uname -m)
if [ "$ARCH" = "arm64" ]; then
  PLATFORM="aarch64-apple-darwin"
else
  PLATFORM="x86_64-apple-darwin"
fi

FILENAME="cpython-${PYTHON_VERSION}+${PYTHON_RELEASE}-${PLATFORM}-install_only.tar.gz"
URL="https://github.com/indygreg/python-build-standalone/releases/download/${PYTHON_RELEASE}/${FILENAME}"

echo "▶ Arch: $ARCH  →  $PLATFORM"
echo "▶ Python version: $PYTHON_VERSION"
echo "▶ Download URL: $URL"
echo "▶ Destination: $DEST_DIR"

# ── Already exists? ───────────────────────────────────────────────────────────
if [ -f "$DEST_DIR/bin/python3" ]; then
  echo "✓ Python already present at $DEST_DIR — skipping download"
else
  echo ""
  echo "▶ Downloading Python $PYTHON_VERSION for $PLATFORM …"
  TMPFILE=$(mktemp /tmp/python-standalone.XXXXXX.tar.gz)
  trap "rm -f '$TMPFILE'" EXIT

  curl -L --progress-bar -o "$TMPFILE" "$URL"

  echo "▶ Extracting to $DEST_DIR …"
  rm -rf "$DEST_DIR"
  mkdir -p "$DEST_DIR"
  tar -xzf "$TMPFILE" --strip-components=1 -C "$DEST_DIR"
  echo "✓ Python extracted"
fi

PYTHON_BIN="$DEST_DIR/bin/python3"

# ── Upgrade pip ───────────────────────────────────────────────────────────────
echo ""
echo "▶ Upgrading pip …"
"$PYTHON_BIN" -m pip install --upgrade pip --quiet

# ── Install Temu dependencies ─────────────────────────────────────────────────
echo "▶ Installing Temu dependencies …"
"$PYTHON_BIN" -m pip install \
  pyyaml \
  openpyxl \
  python-dateutil \
  requests \
  fastapi \
  "uvicorn[standard]" \
  websockets \
  --quiet

echo ""
echo "✅ Done! Python ready at: $DEST_DIR"
"$PYTHON_BIN" --version
echo ""
echo "Installed packages:"
"$PYTHON_BIN" -m pip list --format=columns | grep -E "PyYAML|openpyxl|python-dateutil|requests|fastapi|uvicorn|websockets"
