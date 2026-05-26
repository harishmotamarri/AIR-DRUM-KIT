"""
╔══════════════════════════════════════════════════════════════╗
║                    Beat Recorder & Player                   ║
║   Record your groove, quantize to grid, loop playback       ║
╚══════════════════════════════════════════════════════════════╝
"""

import time
import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional
from config import (DEFAULT_BPM, BEATS_PER_BAR, MAX_RECORD_BARS,
                    RECORDINGS_DIR, MIN_BPM, MAX_BPM)


@dataclass
class BeatEvent:
    """One quantized drum hit."""
    sound_key : str
    beat_pos  : float   # position in beats (0.0 – loop_length)
    velocity  : float   # 0.0 – 1.0
    timestamp : float   # raw time when hit occurred


@dataclass
class RecordedPattern:
    """A complete recorded loop."""
    events      : list[BeatEvent]
    bpm         : float
    loop_beats  : float   # total loop length in beats
    name        : str
    created_at  : float

    def to_dict(self) -> dict:
        return {
            "bpm":       self.bpm,
            "loop_beats":self.loop_beats,
            "name":      self.name,
            "created_at":self.created_at,
            "events":    [asdict(e) for e in self.events],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RecordedPattern":
        events = [BeatEvent(**e) for e in d["events"]]
        return cls(events=events, bpm=d["bpm"],
                   loop_beats=d["loop_beats"],
                   name=d["name"], created_at=d["created_at"])


class BeatRecorder:
    """
    Records drum hits in real-time, quantizes to grid,
    and plays back in a loop.
    """

    def __init__(self):
        self.bpm             : float = DEFAULT_BPM
        self._state          : str   = "idle"   # idle/recording/playing
        self._record_start   : float = 0.0
        self._play_start     : float = 0.0
        self._raw_events     : list[BeatEvent] = []
        self.pattern         : Optional[RecordedPattern] = None
        self._next_event_idx : int   = 0
        self._due_events     : list[BeatEvent] = []

        # Loop length = 4 bars * 4 beats
        self._loop_beats : float = MAX_RECORD_BARS * BEATS_PER_BAR / 4

        os.makedirs(RECORDINGS_DIR, exist_ok=True)

    @property
    def state(self) -> str:
        return self._state

    @property
    def bpm(self) -> float:
        return self._bpm

    @bpm.setter
    def bpm(self, value: float):
        self._bpm = max(MIN_BPM, min(MAX_BPM, float(value)))

    @property
    def beat_duration(self) -> float:
        """Seconds per beat."""
        return 60.0 / self._bpm

    @property
    def loop_duration(self) -> float:
        """Total loop duration in seconds."""
        return self._loop_beats * self.beat_duration

    @property
    def is_recording(self) -> bool:
        return self._state == "recording"

    @property
    def is_playing(self) -> bool:
        return self._state == "playing"

    @property
    def record_progress(self) -> float:
        """0.0–1.0 progress through current recording."""
        if not self.is_recording:
            return 0.0
        elapsed = time.time() - self._record_start
        return min(1.0, elapsed / self.loop_duration)

    @property
    def play_progress(self) -> float:
        """0.0–1.0 position in playback loop."""
        if not self.is_playing:
            return 0.0
        elapsed = (time.time() - self._play_start) % self.loop_duration
        return elapsed / self.loop_duration

    @property
    def current_beat_pos(self) -> float:
        """Current position in beats within the loop."""
        if self.is_recording:
            elapsed = time.time() - self._record_start
        elif self.is_playing:
            elapsed = (time.time() - self._play_start) % self.loop_duration
        else:
            return 0.0
        return (elapsed / self.beat_duration) % self._loop_beats

    # ── Control ───────────────────────────────────────────────

    def start_recording(self):
        """Begin a new recording."""
        self._state        = "recording"
        self._record_start = time.time()
        self._raw_events   = []
        self.pattern       = None
        print("⏺  Recording started")

    def stop_recording(self) -> Optional[RecordedPattern]:
        """Finish recording, quantize, and return pattern."""
        if not self.is_recording:
            return None

        self._state = "idle"
        if not self._raw_events:
            print("⬛  Nothing recorded")
            return None

        pattern = self._quantize()
        self.pattern = pattern
        print(f"⬛  Recording stopped — {len(pattern.events)} events")
        return pattern

    def start_playback(self):
        """Begin looped playback of recorded pattern."""
        if not self.pattern or not self.pattern.events:
            return
        self._state        = "playing"
        self._play_start   = time.time()
        self._sort_events()
        self._next_event_idx = 0
        print("▶  Playback started")

    def stop_playback(self):
        """Stop playback."""
        self._state = "idle"
        print("⏹  Playback stopped")

    def toggle_playback(self):
        if self.is_playing:
            self.stop_playback()
        elif self.pattern:
            self.start_playback()

    # ── Record ────────────────────────────────────────────────

    def record_hit(self, sound_key: str, velocity: float = 1.0):
        """Log a hit during recording."""
        if not self.is_recording:
            return

        now     = time.time()
        elapsed = now - self._record_start

        # Stop auto at loop end
        if elapsed >= self.loop_duration:
            self.stop_recording()
            return

        beat_pos = elapsed / self.beat_duration
        self._raw_events.append(BeatEvent(
            sound_key = sound_key,
            beat_pos  = beat_pos,
            velocity  = velocity,
            timestamp = now,
        ))

    def _quantize(self, grid: float = 0.25) -> RecordedPattern:
        """Snap events to nearest grid position."""
        quantized = []
        for ev in self._raw_events:
            q_beat = round(ev.beat_pos / grid) * grid
            quantized.append(BeatEvent(
                sound_key = ev.sound_key,
                beat_pos  = q_beat,
                velocity  = ev.velocity,
                timestamp = ev.timestamp,
            ))
        # Remove exact duplicates (same sound, same position)
        seen  = set()
        dedup = []
        for ev in quantized:
            key = (ev.sound_key, ev.beat_pos)
            if key not in seen:
                seen.add(key)
                dedup.append(ev)

        return RecordedPattern(
            events     = sorted(dedup, key=lambda e: e.beat_pos),
            bpm        = self._bpm,
            loop_beats = self._loop_beats,
            name       = f"beat_{int(time.time())}",
            created_at = time.time(),
        )

    # ── Playback ──────────────────────────────────────────────

    def _sort_events(self):
        if self.pattern:
            self.pattern.events.sort(key=lambda e: e.beat_pos)

    def get_due_events(self) -> list[BeatEvent]:
        """
        Return events that should fire this frame.
        Call once per frame during playback.
        """
        if not self.is_playing or not self.pattern:
            return []

        current_pos   = self.current_beat_pos
        due           = []
        events        = self.pattern.events
        n             = len(events)

        if n == 0:
            return []

        # Check for loop wraparound
        prev_idx = self._next_event_idx

        while True:
            idx = self._next_event_idx % n
            ev  = events[idx]

            # Simple forward check (handles loop wrap)
            if self._should_fire(ev.beat_pos, current_pos):
                due.append(ev)
                self._next_event_idx = (self._next_event_idx + 1) % n
                if self._next_event_idx == prev_idx:
                    break  # Full loop safety
            else:
                break

        return due

    def _should_fire(self, event_beat: float,
                     current_beat: float, window: float = 0.15) -> bool:
        """Check if event is within the current play window."""
        events = self.pattern.events
        idx    = self._next_event_idx % len(events)
        return abs(events[idx].beat_pos - current_beat) < window or \
               (current_beat < window and
                events[idx].beat_pos > self._loop_beats - window)

    # ── Persistence ──────────────────────────────────────────

    def save(self, name: Optional[str] = None) -> str:
        """Save pattern to JSON."""
        if not self.pattern:
            return ""
        if name:
            self.pattern.name = name
        path = os.path.join(RECORDINGS_DIR,
                            f"{self.pattern.name}.json")
        with open(path, "w") as f:
            json.dump(self.pattern.to_dict(), f, indent=2)
        print(f"💾  Saved: {path}")
        return path

    def load(self, path: str) -> bool:
        """Load pattern from JSON."""
        try:
            with open(path) as f:
                data = json.load(f)
            self.pattern = RecordedPattern.from_dict(data)
            self._bpm    = self.pattern.bpm
            print(f"📂  Loaded: {path} "
                  f"({len(self.pattern.events)} events)")
            return True
        except Exception as e:
            print(f"❌  Load failed: {e}")
            return False

    # ── Beat Grid Visualizer Data ─────────────────────────────

    def get_grid_data(self) -> dict:
        """
        Return data for drawing the beat grid UI.
        """
        steps = int(self._loop_beats * 4)   # 16th note steps per loop
        grid  = {}

        if self.pattern:
            for ev in self.pattern.events:
                step = int(ev.beat_pos * 4) % steps
                if ev.sound_key not in grid:
                    grid[ev.sound_key] = set()
                grid[ev.sound_key].add(step)

        return {
            "steps"      : steps,
            "filled"     : grid,
            "current_step": int(self.current_beat_pos * 4) % steps
                            if (self.is_playing or self.is_recording)
                            else -1,
        }
