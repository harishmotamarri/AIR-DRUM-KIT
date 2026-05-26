"""
╔══════════════════════════════════════════════════════════════╗
║         Procedural Drum Sound Synthesizer                   ║
║   Generates authentic drum sounds using DSP — no samples    ║
╚══════════════════════════════════════════════════════════════╝
"""

import numpy as np
from scipy import signal
import pygame
import os
from config import SAMPLE_RATE


def _to_stereo_sound(mono: np.ndarray, volume: float = 1.0) -> pygame.mixer.Sound:
    """Convert mono float32 array → pygame stereo Sound."""
    mono = np.clip(mono * volume, -1.0, 1.0)
    stereo = np.column_stack([mono, mono])
    pcm = (stereo * 32767).astype(np.int16)
    return pygame.sndarray.make_sound(pcm)


def gen_kick(duration=0.55, pitch=55, punch=0.85) -> pygame.mixer.Sound:
    """Deep, punchy kick drum with pitch sweep."""
    sr = SAMPLE_RATE
    t  = np.linspace(0, duration, int(sr * duration), False)

    # Pitch envelope: sharp drop
    freq_env  = pitch * np.exp(-t * 18) + 28
    phase     = 2 * np.pi * np.cumsum(freq_env) / sr
    body      = np.sin(phase)

    # Click transient
    click_env = np.exp(-t * 180)
    click     = click_env * np.sin(2 * np.pi * 180 * t)

    # Amplitude envelope
    amp_env   = np.exp(-t * 7) * (1 - np.exp(-t * 400))
    wave      = (body * punch + click * 0.35) * amp_env

    # Slight saturation
    wave      = np.tanh(wave * 1.8) / np.tanh(1.8)
    return _to_stereo_sound(wave, 0.95)


def gen_snare(duration=0.28, snap=0.7) -> pygame.mixer.Sound:
    """Snappy snare with wire buzz simulation."""
    sr  = SAMPLE_RATE
    t   = np.linspace(0, duration, int(sr * duration), False)

    # Tonal body (two tuned sine waves)
    body = (np.sin(2 * np.pi * 185 * t) * 0.6 +
            np.sin(2 * np.pi * 285 * t) * 0.3)
    body_env = np.exp(-t * 22)

    # Noise "wires"
    noise     = np.random.randn(len(t))
    b, a      = signal.butter(4, [1500 / (sr/2), 9000 / (sr/2)], btype='band')
    noise_bp  = signal.lfilter(b, a, noise)
    noise_env = np.exp(-t * 18) * (1 - np.exp(-t * 600))

    # Sharp attack crack
    crack     = np.random.randn(len(t)) * np.exp(-t * 350)

    wave      = (body * body_env * (1 - snap) +
                 noise_bp * noise_env * snap +
                 crack * 0.15)
    wave      = np.tanh(wave * 2.2) / np.tanh(2.2)
    return _to_stereo_sound(wave, 0.88)


def gen_hihat_closed(duration=0.07) -> pygame.mixer.Sound:
    """Tight closed hi-hat."""
    sr  = SAMPLE_RATE
    t   = np.linspace(0, duration, int(sr * duration), False)

    noise = np.random.randn(len(t))
    # Multi-band metallic filter
    b, a = signal.butter(5, 6000/(sr/2), btype='high')
    metal = signal.lfilter(b, a, noise)

    # Add metallic ring
    ring  = (np.sin(2*np.pi*8000*t) * 0.15 +
             np.sin(2*np.pi*11200*t) * 0.1)

    amp_env = np.exp(-t * 95)
    wave    = (metal * 0.85 + ring) * amp_env
    return _to_stereo_sound(wave, 0.72)


def gen_hihat_open(duration=0.45) -> pygame.mixer.Sound:
    """Open hi-hat with long decay."""
    sr  = SAMPLE_RATE
    t   = np.linspace(0, duration, int(sr * duration), False)

    noise = np.random.randn(len(t))
    b, a = signal.butter(5, 5000/(sr/2), btype='high')
    metal = signal.lfilter(b, a, noise)

    ring  = (np.sin(2*np.pi*7200*t) * 0.2 +
             np.sin(2*np.pi*10400*t) * 0.12 +
             np.sin(2*np.pi*13600*t) * 0.06)

    amp_env = np.exp(-t * 6) * (1 - np.exp(-t * 400))
    wave    = (metal * 0.7 + ring) * amp_env
    return _to_stereo_sound(wave, 0.75)


def gen_crash(duration=1.8) -> pygame.mixer.Sound:
    """Big, splashy crash cymbal."""
    sr  = SAMPLE_RATE
    t   = np.linspace(0, duration, int(sr * duration), False)

    noise = np.random.randn(len(t))
    b, a = signal.butter(3, 3000/(sr/2), btype='high')
    splash = signal.lfilter(b, a, noise)

    # Complex metallic partials
    ring = sum([
        np.sin(2*np.pi * f * t) * a_
        for f, a_ in [(518, .12),(1072,.09),(1843,.07),
                      (2671,.05),(4200,.04),(6800,.03)]
    ])

    amp_env = np.exp(-t * 3.2) * (1 - np.exp(-t * 500))
    wave    = (splash * 0.75 + ring) * amp_env
    return _to_stereo_sound(wave, 0.82)


def gen_ride(duration=1.2) -> pygame.mixer.Sound:
    """Ping-y ride cymbal."""
    sr  = SAMPLE_RATE
    t   = np.linspace(0, duration, int(sr * duration), False)

    noise = np.random.randn(len(t))
    b, a = signal.butter(4, 4000/(sr/2), btype='high')
    wash  = signal.lfilter(b, a, noise)

    ping  = (np.sin(2*np.pi*822*t)  * np.exp(-t*4)  * 0.30 +
             np.sin(2*np.pi*1640*t) * np.exp(-t*6)  * 0.15 +
             np.sin(2*np.pi*3200*t) * np.exp(-t*9)  * 0.08)

    amp_env = np.exp(-t * 2.8) * (1 - np.exp(-t * 500))
    wave    = (wash * 0.5 + ping) * amp_env
    return _to_stereo_sound(wave, 0.78)


def gen_tom(duration=0.38, pitch=160) -> pygame.mixer.Sound:
    """Floor/rack tom with resonant body."""
    sr  = SAMPLE_RATE
    t   = np.linspace(0, duration, int(sr * duration), False)

    freq_env = pitch * np.exp(-t * 12) + pitch * 0.4
    phase    = 2 * np.pi * np.cumsum(freq_env) / sr
    body     = np.sin(phase)

    noise    = np.random.randn(len(t))
    b, a     = signal.butter(3, [200/(sr/2), 4000/(sr/2)], btype='band')
    atk      = signal.lfilter(b, a, noise) * np.exp(-t * 60) * 0.2

    amp_env  = np.exp(-t * 10) * (1 - np.exp(-t * 500))
    wave     = (body * 0.9 + atk) * amp_env
    wave     = np.tanh(wave * 1.5) / np.tanh(1.5)
    return _to_stereo_sound(wave, 0.85)


def gen_clap(duration=0.18) -> pygame.mixer.Sound:
    """Human-sounding layered clap."""
    sr    = SAMPLE_RATE
    t     = np.linspace(0, duration, int(sr * duration), False)
    wave  = np.zeros(len(t))

    # 3 offset noise bursts to simulate multiple hands
    for delay_ms, amp in [(0, 1.0), (8, 0.7), (16, 0.5)]:
        d    = int(delay_ms * sr / 1000)
        body = np.random.randn(len(t))
        b, a = signal.butter(4, [600/(sr/2), 6000/(sr/2)], btype='band')
        body = signal.lfilter(b, a, body)
        env  = np.exp(-np.maximum(t - delay_ms/1000, 0) * 35)
        if d < len(t):
            wave[d:] += body[d:] * env[d:] * amp

    wave = np.tanh(wave * 2.0) / np.tanh(2.0)
    return _to_stereo_sound(wave, 0.82)


def gen_perc(duration=0.15) -> pygame.mixer.Sound:
    """Short percussion hit - conga/bongo style."""
    sr = SAMPLE_RATE
    t = np.linspace(0, duration, int(sr * duration), False)

    freq_env = 280 * np.exp(-t * 25) + 80
    phase = 2 * np.pi * np.cumsum(freq_env) / sr
    body = np.sin(phase)

    click = np.random.randn(len(t)) * np.exp(-t * 200) * 0.3

    amp_env = np.exp(-t * 18) * (1 - np.exp(-t * 800))
    wave = (body * 0.8 + click) * amp_env
    wave = np.tanh(wave * 2.0) / np.tanh(2.0)

    return _to_stereo_sound(wave, 0.8)


class SoundBank:
    """
    Loads and manages all drum sounds.
    Falls back to synthesized sounds if no samples found.
    """

    GENERATORS = {
        "kick":    lambda: gen_kick(),
        "snare":   lambda: gen_snare(),
        "hihat":   lambda: gen_hihat_closed(),
        "openhat": lambda: gen_hihat_open(),
        "crash":   lambda: gen_crash(),
        "ride":    lambda: gen_ride(),
        "tom1":    lambda: gen_tom(pitch=220),
        "tom2":    lambda: gen_tom(pitch=150),
        "clap":    lambda: gen_clap(),
        "perc":    lambda: gen_perc(),
    }

    def __init__(self):
        self.sounds: dict[str, pygame.mixer.Sound] = {}
        self._channels: dict[str, pygame.mixer.Channel] = {}
        self._load_all()

    def _load_all(self):
        print("🎵 Loading drum sounds...")
        pygame.mixer.set_num_channels(max(pygame.mixer.get_num_channels(), len(self.GENERATORS)))

        for i, (name, gen_fn) in enumerate(self.GENERATORS.items()):
            # Try loading from file first
            path = os.path.join("assets", "sounds", f"{name}.wav")
            if os.path.exists(path):
                try:
                    self.sounds[name] = pygame.mixer.Sound(path)
                    print(f"   ✓ {name:10s} [file]")
                except Exception:
                    self.sounds[name] = gen_fn()
                    print(f"   ✓ {name:10s} [synthesized]")
            else:
                # Synthesize
                self.sounds[name] = gen_fn()
                print(f"   ✓ {name:10s} [synthesized]")

            self._channels[name] = pygame.mixer.Channel(i)

        print(f"   ✅ {len(self.sounds)} sounds ready\n")

    def play(self, key: str, velocity: float = 1.0):
        """Ultra-low-latency playback using dedicated channels."""
        snd = self.sounds.get(key)
        if not snd:
            return

        vol = min(1.0, max(0.3, velocity))
        snd.set_volume(vol)

        channel = self._channels.get(key)
        if channel and not channel.get_busy():
            channel.play(snd)
        else:
            snd.play()

    def get_sound(self, key: str) -> pygame.mixer.Sound | None:
        return self.sounds.get(key)