#!/usr/bin/env bash
# vdo-skill setup for macOS / Linux (Windows: use setup.bat)
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$HERE"
PY=$(command -v python3.12 || command -v python3.11 || command -v python3)
echo "== Python: $($PY --version)"
command -v ffmpeg >/dev/null || { echo "!! ffmpeg not found - install it (brew install ffmpeg / sudo apt install ffmpeg); using imageio-ffmpeg meanwhile"; }
[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt
mkdir -p models
B=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
for f in kokoro-v1.0.onnx voices-v1.0.bin; do
  [ -s "models/$f" ] || curl -L --fail -o "models/$f" "$B/$f"
done
mkdir -p dist/vdo-video "$HOME/.claude/skills/vdo-video"
sed -e "s#{{VDO_HOME}}#$HERE#g" -e 's#\\vdo.bat#/vdo.sh#g; s#vdo.bat#vdo.sh#g' skill/vdo-video/SKILL.md > dist/vdo-video/SKILL.md
cp dist/vdo-video/SKILL.md "$HOME/.claude/skills/vdo-video/SKILL.md"
(cd dist && rm -f vdo-video-skill.zip && zip -qr vdo-video-skill.zip vdo-video)
chmod +x vdo.sh
./vdo.sh doctor
