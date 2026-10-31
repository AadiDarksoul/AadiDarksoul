"""Subtitles: build SRT from known dialogue timings, or transcribe audio with faster-whisper (CPU)."""
import srt
from datetime import timedelta

from .config import HF_HOME  # noqa: F401  (sets HF_HOME for model cache)


def _td(s):
    return timedelta(seconds=max(0.0, s))


def wrap(text, width=42):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    # keep max 2 lines per cue
    if len(lines) > 2:
        mid = len(words) // 2
        return wrap(" ".join(words[:mid]), 99) + "\n" + wrap(" ".join(words[mid:]), 99)
    return "\n".join(lines)


def split_long(start, end, text, max_chars=84):
    """Split long lines into several readable cues, time-proportional by characters."""
    if len(text) <= max_chars:
        return [(start, end, text)]
    import re
    parts = [p.strip() for p in re.split(r"(?<=[.!?,;])\s+", text) if p.strip()]
    chunks, cur = [], ""
    for p in parts:
        if len(cur) + len(p) + 1 > max_chars and cur:
            chunks.append(cur)
            cur = p
        else:
            cur = (cur + " " + p).strip()
    if cur:
        chunks.append(cur)
    total = sum(len(c) for c in chunks)
    out, t = [], start
    for c in chunks:
        d = (end - start) * len(c) / total
        out.append((t, t + d, c))
        t += d
    return out


def write_srt(cues, path, speaker_labels=False):
    """cues: list of dicts {start, end, text, speaker?}."""
    items = []
    for c in sorted(cues, key=lambda c: c["start"]):
        for (s, e, txt) in split_long(c["start"], c["end"], c["text"]):
            if speaker_labels and c.get("speaker"):
                txt = f"{c['speaker'].upper()}: {txt}"
            items.append(srt.Subtitle(index=len(items) + 1, start=_td(s), end=_td(e), content=wrap(txt)))
    with open(path, "w", encoding="utf-8") as f:
        f.write(srt.compose(items))
    return path


def transcribe(audio, model="tiny.en", word_timestamps=True, language="en"):
    """Return (segments, words) using faster-whisper int8 on CPU."""
    from faster_whisper import WhisperModel
    m = WhisperModel(model, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(audio, word_timestamps=word_timestamps, language=language, vad_filter=True)
    segments, words = [], []
    for s in segs:
        segments.append({"start": s.start, "end": s.end, "text": s.text.strip()})
        for w in (s.words or []):
            words.append({"start": w.start, "end": w.end, "text": w.word.strip()})
    return segments, words


def srt_from_audio(audio, path, model="tiny.en"):
    segs, words = transcribe(audio, model)
    write_srt(segs, path)
    return path, segs, words


def ass_word_captions(words, path, width=1080, height=1920, font_size=86, max_words=3,
                      color="&H00FFFFFF", highlight="&H0000E5FF"):
    """Bold, centred, short-form (Shorts/Reels) captions: groups of N words, active word highlighted."""
    def ts(t):
        h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
        return f"{h}:{m:02d}:{s:05.2f}"
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,DejaVu Sans,{font_size},{color},{color},&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,5,60,60,{int(height * 0.18)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for i in range(0, len(words), max_words):
        grp = words[i:i + max_words]
        for j, w in enumerate(grp):
            end = grp[j + 1]["start"] if j + 1 < len(grp) else w["end"]
            txt = " ".join((f"{{\\c{highlight}}}{g['text'].upper()}{{\\c{color}}}" if k == j else g["text"].upper())
                           for k, g in enumerate(grp))
            lines.append(f"Dialogue: 0,{ts(w['start'])},{ts(max(end, w['start'] + 0.05))},Cap,,0,0,0,,{txt}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(lines) + "\n")
    return path
