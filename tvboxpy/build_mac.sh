#!/bin/bash
# TVBox4Win —— macOS 一键构建脚本
#
#   ./build_mac.sh            构建 dist/TVBox4Win.app
#   ./build_mac.sh --run      构建后直接启动
#
# 依赖：Python 3.9+（需自带可用的 Tcl/Tk，见下方说明）
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"

if [ ! -x "$PY" ]; then
  echo "==> 创建虚拟环境 .venv"
  # 优先用带 Tcl/Tk 9 的 uv python；系统自带 python3 的 Tk 8.5 也可用但更旧
  BASE_PY="$(command -v python3.12 || command -v python3)"
  "$BASE_PY" -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/python" -m pip install -q --upgrade pip
fi

echo "==> 安装依赖"
"$PY" -m pip install -q requests Pillow pyinstaller \
  pyobjc-framework-Cocoa pyobjc-framework-AVFoundation

echo "==> 生成图标"
ICNS="$ROOT/build/tvbox4win.icns"
if [ ! -f "$ICNS" ]; then
  mkdir -p "$ROOT/build/icon.iconset"
  for s in 16 32 64 128 256 512; do
    sips -z $s $s "$ROOT/tvboxosc/assets/tvbox4win.png" \
      --out "$ROOT/build/icon.iconset/icon_${s}x${s}.png" >/dev/null
    sips -z $((s*2)) $((s*2)) "$ROOT/tvboxosc/assets/tvbox4win.png" \
      --out "$ROOT/build/icon.iconset/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$ROOT/build/icon.iconset" -o "$ICNS"
fi

echo "==> PyInstaller 打包"
"$PY" -m PyInstaller tvboxpy_mac.spec --noconfirm \
  --distpath "$ROOT/../dist" --workpath "$ROOT/../build/pyi"

APP="$ROOT/../dist/TVBox4Win.app"
echo "==> 冒烟自检（真实解码一段 HLS 测试流）"
"$APP/Contents/MacOS/TVBox4Win" --smoke || true

echo
echo "构建完成：$APP"
du -sh "$APP"
if [ "${1:-}" = "--run" ]; then
  open "$APP"
fi
