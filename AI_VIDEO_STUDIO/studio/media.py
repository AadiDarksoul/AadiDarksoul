"""Thin, checked wrappers around ffmpeg/ffprobe."""
import json
import os
import subprocess

from .config import FPS, HEIGHT, WIDTH, require


class MediaError(RuntimeError):
    pass


def run(cmd, quiet=True):
    """Run a command; raise MediaError with stderr tail on failure."""
    cmd = [str(c) for c in cmd]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        tail = "\n".join(p.stderr.strip().splitlines()[-15:])
        raise MediaError(f"Command failed ({p.returncode}): {' '.join(cmd[:6])} ...\n{tail}")
    if not quiet:
        print(p.stdout)
    return p.stdout


def ffmpeg(*args):
    return run([require("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", *args])


def probe(path):
    out = run([require("ffprobe"), "-v", "error", "-print_format", "json",
               "-show_format", "-show_streams", path])
    return json.loads(out)


def duration(path):
    return float(probe(path)["format"]["duration"])


def describe(path):
    """Compact human summary of a media file (used by tests / verification)."""
    info = probe(path)
    parts = []
    for s in info["streams"]:
        if s["codec_type"] == "video":
            parts.append(f"video {s['codec_name']} {s['width']}x{s['height']} @{s.get('r_frame_rate')} {s.get('pix_fmt')}")
        elif s["codec_type"] == "audio":
            parts.append(f"audio {s['codec_name']} {s.get('sample_rate')}Hz ch={s.get('channels')}")
        elif s["codec_type"] == "subtitle":
            parts.append(f"subtitle {s['codec_name']}")
    return f"{os.path.basename(path)}: {float(info['format']['duration']):.2f}s | " + " | ".join(parts)


# Delivery presets (H.264 High, yuv420p, AAC 48k stereo, faststart)
X264 = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
AAC = ["-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2"]


class FrameWriter:
    """Pipe raw RGB frames into ffmpeg -> H.264 file."""

    def __init__(self, path, width=WIDTH, height=HEIGHT, fps=FPS, crf=18, preset="medium"):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        cmd = [require("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps),
               "-i", "-", "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", path]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    def write(self, rgb_bytes):
        self.proc.stdin.write(rgb_bytes)

    def close(self):
        self.proc.stdin.close()
        err = self.proc.stderr.read().decode(errors="replace")
        if self.proc.wait() != 0:
            raise MediaError(f"ffmpeg encode failed for {self.path}: {err[-800:]}")
        return self.path


def mux(video, audio, out, subtitles=None, burn=False, sub_style=None, extra_vf=None):
    """Combine video + audio (+ optional SRT soft track or burned-in subs) into a delivery MP4."""
    args = ["-i", video, "-i", audio]
    vf = []
    if extra_vf:
        vf.append(extra_vf)
    if subtitles and burn:
        style = sub_style or ("FontName=DejaVu Sans,FontSize=20,PrimaryColour=&H00F0F0F0,"
                              "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=40")
        esc = subtitles.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        vf.append(f"subtitles='{esc}':force_style='{style}'")
    maps = ["-map", "0:v:0", "-map", "1:a:0"]
    if subtitles and not burn:
        args += ["-i", subtitles]
        maps += ["-map", "2:s:0"]
    cmd = args + maps
    if vf:
        cmd += ["-vf", ",".join(vf)] + X264
    else:
        cmd += ["-c:v", "copy"]
    cmd += AAC
    if subtitles and not burn:
        cmd += ["-c:s", "mov_text", "-metadata:s:s:0", "language=eng"]
    cmd += ["-shortest", out]
    ffmpeg(*cmd)
    return out
