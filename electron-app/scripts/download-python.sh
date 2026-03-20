#!/bin/bash
# scripts/download-python.sh
# 下载 python-build-standalone 到 python-dist/，用于打包进 Electron
# 用法: bash scripts/download-python.sh [mac-arm64] [mac-x64] [win-x64]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DIST_DIR="$SCRIPT_DIR/../python-dist"
VERSION="20260310"
PY_VERSION="3.12.13"
BASE="https://github.com/astral-sh/python-build-standalone/releases/download/${VERSION}"
PROXY="${GITHUB_PROXY:-}"  # 可设置 https://ghproxy.net/ 加速

mkdir -p "$DIST_DIR"

download_and_extract() {
  local name="$1"
  local file="$2"
  local dest="$DIST_DIR/$name"

  if [ -d "$dest/bin" ] || [ -d "$dest/python" ]; then
    echo "✅ $name already exists, skip"
    return
  fi

  echo "⬇️  Downloading $name..."
  local url="${PROXY}${BASE}/${file}"
  curl -L -o "/tmp/${file}" "$url" --progress-bar

  echo "📦 Extracting $name..."
  mkdir -p "$dest"
  tar -xzf "/tmp/${file}" -C "$dest" --strip-components=1
  rm -f "/tmp/${file}"

  # 安装 openpyxl
  local pip
  if [ -f "$dest/bin/pip3" ]; then
    pip="$dest/bin/pip3"
  elif [ -f "$dest/python/pip.exe" ]; then
    pip="$dest/python/pip.exe"
  elif [ -f "$dest/pip3" ]; then
    pip="$dest/pip3"
  fi

  if [ -n "$pip" ]; then
    echo "📦 Installing openpyxl into $name..."
    "$pip" install openpyxl --quiet
  else
    echo "⚠️  pip not found in $name, skip openpyxl install"
  fi

  echo "✅ $name ready"
}

TARGETS="${*:-mac-arm64 mac-x64 win-x64}"

for target in $TARGETS; do
  case "$target" in
    mac-arm64)
      download_and_extract "mac-arm64" "cpython-${PY_VERSION}+${VERSION}-aarch64-apple-darwin-install_only_stripped.tar.gz"
      ;;
    mac-x64)
      download_and_extract "mac-x64" "cpython-${PY_VERSION}+${VERSION}-x86_64-apple-darwin-install_only_stripped.tar.gz"
      ;;
    win-x64)
      download_and_extract "win-x64" "cpython-${PY_VERSION}+${VERSION}-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
      ;;
    *)
      echo "Unknown target: $target"
      ;;
  esac
done

echo ""
echo "🎉 All done! python-dist contents:"
ls -lh "$DIST_DIR"
