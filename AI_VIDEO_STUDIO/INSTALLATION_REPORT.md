# Installation Report — Phase 1 (Claude Skills) + core tools

Date: 2026-10-31 · Machine: Ubuntu 24.04 cloud container, 4-core Xeon 2.1 GHz, 15 GB RAM, **no GPU**, ~31 GB free disk.

> Scope note: on request, video production/test rendering was **paused**. This pass installs skills and the core tools only.
> The cloud container is temporary. Everything under `/opt/ai_video_studio` must be reinstalled on your own machine with `bash AI_VIDEO_STUDIO/install.sh`.
> Skills live in the repo (`.claude/skills/`, `.claude/settings.json`) so they come with every clone.

## 1. Claude Skills installed (project scope)

All were checked against the Agent Skills spec: `name` matches the folder and is lowercase/hyphenated, and `description` is 1–1024 characters.

| Source repo | Method | Skills | Status |
|---|---|---|---|
| remotion-dev/skills | `npx skills add remotion-dev/skills` | remotion-best-practices, -captions, -create, -docs, -interactivity, -maps, -markup, -multimedia, -render, -saas, -studio, -upgrade (12) | ✅ installed, validated, loaded by Claude Code in this session |
| anthropics/skills | `claude plugin marketplace add anthropics/skills` + `claude plugin install … --scope project` | **example-skills**: algorithmic-art, brand-guidelines, canvas-design, doc-coauthoring, frontend-design, internal-comms, mcp-builder, skill-creator, slack-gif-creator, theme-factory, web-artifacts-builder, webapp-testing (12) | ✅ enabled in `.claude/settings.json` |
| anthropics/skills | same | **document-skills**: docx, pdf, pptx, xlsx (4) | ✅ enabled (source-available licence, not open source) |
| WyattBlue/auto-editor | `npx skills add WyattBlue/auto-editor` | auto-editor, auto-editor-effects, auto-editor-export, auto-editor-transcribe (4) | ✅ installed, validated |
| isl-org/Open3D | `npx skills add isl-org/Open3D -s open3d-python` | open3d-python (1) | ✅ installed (the Python package `open3d` itself is not installed yet) |

Skipped on purpose:
- `mltframework/shotcut` (new-filter-ui) and `NatronGitHub/Natron` (natron-maintainer, macports-natron-upgrade) are for developing those codebases, not for making videos.
- `open3d-cpp` targets the C++ API.
- The `claude-api`, `academy-guide` and `discernment-nudge` plugins aren't relevant to video. Also, upstream `claude-api` has a 1068-character description, which exceeds the spec.

Not Claude Skills (verified):
- `anthropics/claude-code` is the CLI itself (v2.1.316, already present).
- `agentskills/agentskills` is the open specification and docs (Apache-2.0). It was used to validate the skills above.
- `remotion-dev/remotion` is the framework, tested below.

## 2. Tools installed and functionally tested

| Tool | Version | Source | Test performed | Result |
|---|---|---|---|---|
| FFmpeg | 6.1.1 (libx264, aac, libass) | apt (preinstalled) | encoders/filters probe | ✅ |
| Blender | 4.0.2 | apt | headless render: Cycles CPU, Eevee (software EGL), Workbench | ✅ (Ubuntu build has **no OpenImageDenoise**, so keep denoising off) |
| Synfig CLI | 1.5.1 | apt | `--version` | ✅ installed (not exercised further) |
| MLT `melt` | 7.22.0 | apt | `--version` | ✅ installed |
| espeak-ng / sox | 1.51 / 14.4.2 | apt | used as TTS fallback | ✅ |
| Remotion | 4.0.536 | npm (template in `templates/remotion-title`) | rendered 72-frame 1920×1080 H.264 title on CPU with preinstalled Chromium | ✅ |
| auto-editor | 29.3.1 | pip (official binary) | `--version` | ✅ |
| MoviePy | 2.2.1 | pip | import | ✅ |
| PySceneDetect | 0.7.2 | pip | import | ✅ |
| OpenCV | 5.0.0 (headless) | pip | import | ✅ |
| Manim CE | 0.22.1 | pip (built manimpango from source) | import | ✅ |
| Piper TTS | 1.8.0 (OHF-Voice/piper1-gpl) | pip | synthesized speech with 3 voices, 2.6 s for 3.5 s of audio | ✅ |
| faster-whisper | 1.2.1 + tiny.en int8 | pip | transcribed the Piper test line exactly | ✅ (needed `av<16`, since newer PyAV breaks it) |
| Rhubarb Lip Sync | 1.14.0 | official GitHub release | mouth cues JSON from a wav | ✅ |
| rembg | 2.0.86 | pip in a **separate venv** (`venv-rembg`) | CLI help | ✅ installed. Its Pillow ≥12 requirement conflicts with MoviePy, hence the isolation. No model downloaded yet. |

Models downloaded (all small, CPU): Piper voices `en_US-lessac-medium`, `en_US-ryan-medium` and `en_GB-alan-medium` (~63 MB each), plus Whisper `tiny.en` (~75 MB).

## 3. Logged failures / fixes
1. `scenedetect[opencv-headless]` extra no longer exists. Installed `opencv-python-headless` separately.
2. faster-whisper failed with PyAV 19 (`open() got an unexpected keyword argument 'metadata_errors'`). Fixed by pinning `av<16`.
3. manimpango has no wheel for Python 3.13. Fixed by installing `libpango1.0-dev libcairo2-dev` and building from source.
4. Pillow conflict between rembg (≥12.1) and moviepy (<12). Fixed by moving rembg to its own venv.
5. Blender render failed with "Build without OpenImageDenoiser". Fixed by setting `cycles.use_denoising=False`.
6. GitHub REST API is blocked for third-party repos in this session. Repo metadata was collected with blob-less shallow `git clone` instead.

## 4. Not installed (yet) — needs your decision
- **GPU-heavy, impractical on this CPU box:** ComfyUI + AnimateDiff/ControlNet, MusicGen, Bark, RVC, Wav2Lip, GFPGAN, Real-ESRGAN (torch), Segment Anything, RIFE (torch).
- **Desktop GUI apps** (no display here; install on your PC): Kdenlive, Shotcut, OpenShot, OpenToonz, Pencil2D, Krita, Godot, Natron, Audacity, Ardour, LMMS, Meshroom (needs CUDA), UVR.
- **Large downloads awaiting approval:** larger Whisper models, Demucs weights, rembg `u2net` (176 MB).

## 5. Work in progress (paused on request)
`AI_VIDEO_STUDIO/studio/` contains a CPU filmmaking library:
- **Tested:** procedural SFX, ambience, music, multi-voice TTS, and a ducking mixer with two-pass loudnorm.
- **Written but not fully tested:** a 2D puppet rig, a parallax scene renderer, subtitles and lip-sync.

The 20 custom skills (Phase 7) and the test film have **not** been created yet.
