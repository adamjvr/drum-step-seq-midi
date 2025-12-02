"""
sequencer_model.py

This module defines the "pure logic" side of the step sequencer: no GUI,
no MIDI I/O, just data structures and operations.

Responsibilities:
- Store all pattern data: rows, bars, steps-per-bar, per-step velocity.
- Store per-row metadata: drum part name, MIDI note assignment.
- Provide methods for:
    * toggling / setting step velocity
    * resizing the grid (change steps-per-bar, change number of bars)
    * copying and pasting bars
    * randomizing / humanizing fills
    * serializing to/from JSON for saving/loading

Separating the model from the GUI makes the code more testable and easier
to extend in the future (e.g., different UIs using the same engine).
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Any
import json
import random


@dataclass
class RowMeta:
    """
    RowMeta holds metadata for each drum row.

    Attributes:
        name:     Human-readable part name (e.g., 'Kick', 'Snare').
        midi_note: MIDI note number that this row will trigger.
                   Typically 36 = kick, 38 = snare, etc., but fully configurable.
    """
    name: str
    midi_note: int


class SequencerModel:
    """
    SequencerModel holds an N-row x B-bar x S-steps grid of velocities.

    Internal representation:
        - rows:  number of drum/instrument lines
        - bars:  number of bars in the pattern
        - steps_per_bar: number of steps in each bar (e.g., 16, 32, 64)
        - data[row][bar][step] = velocity (0-127)

    The model does not know anything about windows, widgets, or timers.
    It is purely about data and transforms.
    """

    def __init__(self, num_rows: int = 8, bars: int = 4, steps_per_bar: int = 16):
        self.num_rows = num_rows
        self.bars = bars
        self.steps_per_bar = steps_per_bar

        # Initialize row metadata with default names and a simple GM drum map
        base_note = 36  # Kick starting note
        self.rows_meta: List[RowMeta] = [
            RowMeta(name=f"Part {i + 1}", midi_note=base_note + i)
            for i in range(num_rows)
        ]

        # Initialize grid with zeros (all steps off)
        self.data: List[List[List[int]]] = [
            [
                [0 for _ in range(steps_per_bar)]  # steps per bar
                for _ in range(bars)              # bars
            ]
            for _ in range(num_rows)              # rows
        ]

        # Internal copy buffer for copy/paste operations (one bar snapshot)
        self._copy_buffer: List[List[int]] = []

    # ------------------------------------------------------------------
    # Basic accessors and mutators
    # ------------------------------------------------------------------

    def set_velocity(self, row: int, bar: int, step: int, velocity: int):
        """
        Set the velocity for a given (row, bar, step).

        Velocity should be in the 0..127 range. Values outside this range
        are clamped to be safe.

        This method is typically used when the GUI's StepButton emits a
        velocityChanged signal and we want to mirror that change in the
        model.
        """
        velocity = max(0, min(127, velocity))
        self.data[row][bar][step] = velocity

    def get_velocity(self, row: int, bar: int, step: int) -> int:
        """Return the velocity for the given cell."""
        return self.data[row][bar][step]

    def set_row_meta(self, row: int, name: str, midi_note: int):
        """Update the row's part name and MIDI note assignment."""
        self.rows_meta[row].name = name
        self.rows_meta[row].midi_note = midi_note

    def get_row_meta(self, row: int) -> RowMeta:
        """Retrieve metadata for a given row."""
        return self.rows_meta[row]

    # ------------------------------------------------------------------
    # Resizing / structure-changing operations
    # ------------------------------------------------------------------

    def set_bars(self, bars: int):
        """
        Change the number of bars in the pattern, preserving existing data.

        - If increasing bars, new bars are appended and initialized to zeros.
        - If decreasing bars, extra bars are truncated.
        """
        bars = max(1, bars)
        if bars == self.bars:
            return

        for r in range(self.num_rows):
            row_bars = self.data[r]
            if bars > self.bars:
                # Add new bars filled with zeros
                for _ in range(bars - self.bars):
                    row_bars.append([0] * self.steps_per_bar)
            else:
                # Truncate extra bars
                del row_bars[bars:]

        self.bars = bars

    def set_steps_per_bar(self, steps_per_bar: int):
        """
        Change the number of steps per bar, preserving as much data as possible.

        When increasing, new steps at the end are zero-filled.
        When decreasing, extra steps are truncated.
        """
        steps_per_bar = max(1, steps_per_bar)
        if steps_per_bar == self.steps_per_bar:
            return

        for r in range(self.num_rows):
            for b in range(self.bars):
                old_steps = self.data[r][b]
                if steps_per_bar > self.steps_per_bar:
                    # Extend with zeros
                    old_steps.extend([0] * (steps_per_bar - self.steps_per_bar))
                else:
                    # Truncate
                    del old_steps[steps_per_bar:]

        self.steps_per_bar = steps_per_bar

    # ------------------------------------------------------------------
    # Copy/paste bars
    # ------------------------------------------------------------------

    def copy_bar(self, bar_index: int):
        """
        Copy the entire bar (all rows, all steps) into an internal buffer.

        The copy buffer is structured as [row][step] velocities for that bar.
        """
        if not (0 <= bar_index < self.bars):
            return

        buffer: List[List[int]] = []
        for r in range(self.num_rows):
            buffer.append(list(self.data[r][bar_index]))  # deep copy of step list

        self._copy_buffer = buffer

    def paste_bar(self, bar_index: int):
        """
        Paste previously copied bar into the specified bar index.

        If there is no copy buffer yet, this does nothing.
        """
        if not self._copy_buffer:
            return
        if not (0 <= bar_index < self.bars):
            return

        for r in range(self.num_rows):
            if r < len(self._copy_buffer):
                src_steps = self._copy_buffer[r]
                # Adjust length to current steps_per_bar
                steps = src_steps[:self.steps_per_bar]
                if len(steps) < self.steps_per_bar:
                    steps += [0] * (self.steps_per_bar - len(steps))
                self.data[r][bar_index] = steps

    # ------------------------------------------------------------------
    # Randomization / humanization
    # ------------------------------------------------------------------

    def randomize_bar(self, bar_index: int, density: float = 0.3,
                      min_vel: int = 40, max_vel: int = 120):
        """
        Fill a bar with random hits.

        Parameters:
            bar_index: which bar to randomize.
            density:  probability of a hit at each cell (0..1).
            min_vel, max_vel: inclusive range of random velocities.

        Any existing data in that bar is overwritten.
        """
        if not (0 <= bar_index < self.bars):
            return

        min_vel = max(1, min_vel)
        max_vel = min(127, max_vel)
        if min_vel > max_vel:
            min_vel, max_vel = max_vel, min_vel

        for r in range(self.num_rows):
            for s in range(self.steps_per_bar):
                if random.random() < density:
                    vel = random.randint(min_vel, max_vel)
                else:
                    vel = 0
                self.data[r][bar_index][s] = vel

    def humanize_velocities(self, bar_index: int,
                            amount: int = 10):
        """
        Slightly randomize velocities around their current values
        to make the pattern feel less robotic.

        Parameters:
            bar_index: which bar to humanize.
            amount:    max +/- change applied to each non-zero velocity.
        """
        if not (0 <= bar_index < self.bars):
            return

        for r in range(self.num_rows):
            for s in range(self.steps_per_bar):
                vel = self.data[r][bar_index][s]
                if vel > 0:
                    delta = random.randint(-amount, amount)
                    new_vel = max(1, min(127, vel + delta))
                    self.data[r][bar_index][s] = new_vel

    # ------------------------------------------------------------------
    # Serialization: save/load to JSON
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Convert the entire pattern to a serializable dictionary."""
        return {
            "num_rows": self.num_rows,
            "bars": self.bars,
            "steps_per_bar": self.steps_per_bar,
            "rows_meta": [asdict(m) for m in self.rows_meta],
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SequencerModel":
        """
        Create a SequencerModel instance from a dictionary produced by to_dict().
        """
        model = cls(
            num_rows=d["num_rows"],
            bars=d["bars"],
            steps_per_bar=d["steps_per_bar"],
        )
        model.rows_meta = [RowMeta(**rm) for rm in d["rows_meta"]]
        model.data = d["data"]
        return model

    def save_to_file(self, path: str):
        """Save the pattern as JSON."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load_from_file(cls, path: str) -> "SequencerModel":
        """Load a pattern from a JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return cls.from_dict(d)
