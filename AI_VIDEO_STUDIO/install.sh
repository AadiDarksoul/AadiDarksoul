#!/usr/bin/env bash
# Reinstall the AI Video Studio toolchain + Claude skills on a fresh Ubuntu 24.04 machine (CPU-only).
# Usage: bash AI_VIDEO_STUDIO/install.sh        (run from the repo root; needs sudo for apt)
set -euo pipefail
DATA=${STUDIO_DATA:-/opt/ai_video_studio}
REPO=$(cd "$(dirname "$0")/.." && pwd)
SUDO=$([ "$(id -u)" = 0 ] && echo "" || echo sudo)

echo "== system packages (apt)"
$SUDO apt-get update -qq
$SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
  ffmpeg blender synfig melt espeak-ng sox libsox-fmt-all fonts-dejavu-core \
  libpango1.0-dev libcairo2-dev pkg-config python3-dev python3-venv build-essential unzip

echo "== python venv (main)"
$SUDO mkdir -p "$DATA" && $SUDO chown "$(id -u):$(id -g)" "$DATA"
python3 -m venv "$DATA/venv"
"$DATA/venv/bin/pip" install -q --upgrade pip
"$DATA/venv/bin/pip" install -q numpy "pillow<12" scipy moviepy scenedetect opencv-python-headless \
  piper-tts faster-whisper "av<16" srt pyyaml manim auto-editor

echo "== python venv (rembg, isolated: needs pillow>=12)"
python3 -m venv "$DATA/venv-rembg"
"$DATA/venv-rembg/bin/pip" install -q "rembg[cpu,cli]"

echo "== Rhubarb Lip Sync 1.14.0"
mkdir -p "$DATA/bin" && tmp=$(mktemp -d)
curl -sSLf -o "$tmp/rh.zip" https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v1.14.0/Rhubarb-Lip-Sync-1.14.0-Linux.zip
unzip -q "$tmp/rh.zip" -d "$tmp" && rm -rf "$DATA/rhubarb" && mv "$tmp"/Rhubarb-Lip-Sync-1.14.0-Linux "$DATA/rhubarb"
ln -sf "$DATA/rhubarb/rhubarb" "$DATA/bin/rhubarb"; rm -rf "$tmp"

echo "== small CPU models (~260 MB total)"
mkdir -p "$DATA/models/piper"
for v in en_US-lessac-medium en_US-ryan-medium en_GB-alan-medium; do
  "$DATA/venv/bin/python" -m piper.download_voices --download-dir "$DATA/models/piper" "$v"
done
HF_HOME="$DATA/models/hf" "$DATA/venv/bin/python" -c "from faster_whisper import WhisperModel; WhisperModel('tiny.en', device='cpu', compute_type='int8')"

echo "== Claude skills (project scope, already vendored in .claude/skills; this refreshes them)"
cd "$REPO"
npx -y skills add remotion-dev/skills -a claude-code -s '*' --copy -y
npx -y skills add WyattBlue/auto-editor -a claude-code -s '*' --copy -y
npx -y skills add isl-org/Open3D -a claude-code -s open3d-python --copy -y
if command -v claude >/dev/null; then
  claude plugin marketplace add anthropics/skills --scope project || true
  claude plugin install example-skills@anthropic-agent-skills --scope project || true
  claude plugin install document-skills@anthropic-agent-skills --scope project || true
fi
echo "== done"
