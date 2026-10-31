# GitHub Repository Verification (2026-10-31)

All 49 URLs were checked with `git ls-remote`, and **all resolved**. Last-commit date and licence file come from blob-less shallow clones.

| Repo | Type | Last commit | Licence | Notes |
|---|---|---|---|---|
| anthropics/skills | **Claude Skills** (plugin marketplace) | 2026-10-28 | Apache-2.0 (examples) / source-available (document skills) | installed |
| remotion-dev/skills | **Claude Skills** | 2026-10-26 | no root LICENSE file | installed |
| remotion-dev/remotion | framework (React video) | 2026-10-31 | Remotion License (free for individuals/small teams; company licence above that) | tested |
| anthropics/claude-code | CLI | 2026-10-31 | proprietary | present |
| agentskills/agentskills | spec/docs | 2026-08-09 | Apache-2.0 / CC-BY-4.0 | used for validation |
| FFmpeg/FFmpeg | library/CLI | 2026-10-31 | LGPL/GPL | installed (apt) |
| WyattBlue/auto-editor | CLI + **4 Claude Skills** | 2026-10-31 | Unlicense | installed |
| KDE/kdenlive | desktop app | 2026-10-31 | GPL-3 | GUI, not installed |
| mltframework/shotcut | desktop app (+1 dev skill) | 2026-10-30 | GPL-3 | GUI, not installed |
| OpenShot/openshot-qt | desktop app | 2026-10-22 | GPL-3 | GUI, not installed |
| Zulko/moviepy | Python library | 2026-08-26 | MIT | installed |
| Breakthrough/PySceneDetect | Python library | 2026-10-25 | BSD-3 | installed |
| mltframework/mlt | engine | 2026-10-29 | LGPL-2.1/GPL | `melt` installed |
| opentoonz/opentoonz | desktop app | 2026-10-28 | BSD-3 | GUI |
| synfig/synfig | app + CLI | 2026-10-27 | GPL-3 | CLI installed |
| pencil2d/pencil | desktop app | 2026-10-26 | GPL-2 (+Qt BSD) | GUI |
| KDE/krita | desktop app | 2026-10-31 | GPL-3 | GUI |
| blender/blender | app (headless capable) | 2026-10-31 | GPL-2+ | 4.0.2 installed |
| ManimCommunity/manim | Python library | 2026-10-27 | MIT | installed |
| motion-canvas/motion-canvas | TS library | 2026-07-02 | MIT | not installed (Remotion covers this role) |
| godotengine/godot | engine | 2026-10-30 | MIT | not installed |
| NatronGitHub/Natron | compositor (+2 dev skills) | 2026-07-24 | GPL-2 | GUI |
| opencv/opencv | library | 2026-10-31 | Apache-2.0 | installed (pip) |
| isl-org/Open3D | library (+2 Claude Skills) | 2026-09-16 | MIT | skill installed, package not yet |
| alicevision/Meshroom | photogrammetry app | 2026-10-29 | MPL-2.0 | needs CUDA GPU |
| audacity/audacity | desktop app | 2026-10-30 | GPL-2/3 | GUI |
| Ardour/ardour | DAW | 2026-10-30 | GPL-2 | GUI |
| LMMS/lmms | DAW | 2026-10-25 | GPL-2 | GUI |
| openai/whisper | model + library | 2026-08-31 | MIT | faster-whisper used instead (faster on CPU) |
| ggml-org/whisper.cpp | C++ ASR | 2026-10-30 | MIT | bundled inside auto-editor |
| SYSTRAN/faster-whisper | library | 2026-10-16 | MIT | installed |
| rhasspy/piper | TTS | 2025-08-26 | MIT | **archived; moved to OHF-Voice/piper1-gpl (GPL-3)**, which is what pip installs |
| coqui-ai/TTS | TTS library | 2024-02-10 | MPL-2.0 code; XTTS weights CPML (non-commercial) | **unmaintained** (company closed) |
| facebookresearch/demucs | model | 2023-11-16 | MIT | inactive; CPU works but slow |
| Anjok07/ultimatevocalremovergui | desktop app | 2026-10-06 | no LICENSE file found | GUI |
| facebookresearch/audiocraft | MusicGen | 2025-03-13 | MIT code; **weights CC-BY-NC 4.0** | GPU recommended |
| suno-ai/bark | TTS model | 2024-04-05 | MIT | inactive; slow on CPU |
| RVC-Project/Retrieval-based-Voice-Conversion-WebUI | voice conversion | 2026-08-04 | MIT | GPU; authorized voices only |
| DanielSWolf/rhubarb-lip-sync | CLI | 2025-04-03 | MIT | installed |
| comfyanonymous/ComfyUI | app | 2026-10-31 | GPL-3 | GPU recommended |
| guoyww/AnimateDiff | model | 2024-07-17 | Apache-2.0 | GPU only in practice |
| lllyasviel/ControlNet | model | 2023-09-09 | Apache-2.0 | GPU |
| xinntao/Real-ESRGAN | model | 2024-04-03 | BSD-3 | ncnn-vulkan build or GPU |
| hzwer/ECCV2022-RIFE | model | 2025-09-10 | MIT | superseded by Practical-RIFE |
| hzwer/Practical-RIFE | model | 2026-08-27 | MIT | GPU recommended |
| TencentARC/GFPGAN | model | 2024-04-03 | Apache-2.0 | inactive |
| danielgatis/rembg | library | 2026-10-21 | MIT | installed (separate venv) |
| facebookresearch/segment-anything | model | 2024-09-18 | Apache-2.0 | GPU recommended |
| Rudrabha/Wav2Lip | model | 2025-06-22 | no LICENSE file; README restricts to non-commercial/research and promotes the paid sync.so API | not installed |
