"""WAV I/O helpers (float32 stereo @ 48 kHz internally)."""
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

from .config import SAMPLE_RATE as SR


def load(path, sr=SR):
    rate, data = wavfile.read(path)
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float32) / 2147483648.0
    elif data.dtype == np.uint8:
        data = (data.astype(np.float32) - 128) / 128.0
    data = data.astype(np.float32)
    if data.ndim == 1:
        data = np.stack([data, data], axis=1)
    if rate != sr:
        g = np.gcd(rate, sr)
        data = resample_poly(data, sr // g, rate // g, axis=0).astype(np.float32)
    return data


def save(path, data, sr=SR):
    data = np.asarray(data, dtype=np.float32)
    if data.ndim == 1:
        data = np.stack([data, data], axis=1)
    peak = np.max(np.abs(data)) if data.size else 0
    if peak > 0.999:
        data = data / peak * 0.999
    wavfile.write(path, sr, (data * 32767).astype(np.int16))
    return path


def stereo(mono, pan=0.0):
    """Constant-power pan, pan in [-1, 1]."""
    a = (pan + 1) * np.pi / 4
    return np.stack([mono * np.cos(a), mono * np.sin(a)], axis=1).astype(np.float32)
