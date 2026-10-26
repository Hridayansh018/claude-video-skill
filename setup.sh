#!/usr/bin/env bash
# claude-video-skill setup for macOS / Linux (Windows: use setup.bat)
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
mkdir -p dist/claude-video-skill "$HOME/.claude/skills/claude-video-skill"
sed -e "s#{{VDO_HOME}}#$HERE#g" -e 's#\\vdo.bat#/vdo.sh#g; s#vdo.bat#vdo.sh#g' skill/claude-video-skill/SKILL.md > dist/claude-video-skill/SKILL.md
cp dist/claude-video-skill/SKILL.md "$HOME/.claude/skills/claude-video-skill/SKILL.md"
(cd dist && rm -f claude-video-skill.zip && zip -qr claude-video-skill.zip claude-video-skill)
chmod +x vdo.sh
./vdo.sh doctor
