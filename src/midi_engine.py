"""
midi_engine.py

This module encapsulates everything related to MIDI I/O:

    - Converting a SequencerModel into a .mid file on disk.
    - Live playback using an output MIDI port (via mido + RtMidi backend).
    - Metronome tick generation.
    - Swing support applied to step timing (for live playback only).

The idea is to separate actual MIDI work from the GUI or data model.
"""

from typing import Optional, List, Tuple

import mido
from mido import Message, MidiFile, MidiTrack, MetaMessage

from sequencer_model import SequencerModel


class MidiEngine:
    """
    MidiEngine is responsible for:

        - Exporting the entire pattern as a MIDI file.
        - Sending live note-on/note-off messages to a hardware/software port.
        - Calculating per-step timing (including swing) for live playback.

    This class does not know about Qt or timers. The GUI layer calls
    its methods when appropriate (e.g., on each timer tick).
    """

    def __init__(self, model: SequencerModel):
        self.model = model

        # Currently selected MIDI output port name, if any.
        self._port_name: Optional[str] = None

        # Actual mido output port object, if open.
        self._port: Optional[mido.ports.BaseOutput] = None

        # To help handle note off, we track all currently active notes so
        # they can be turned off on the next step.
        self._active_notes: List[Tuple[int, int]] = []  # list of (note, row_index)

    # ------------------------------------------------------------------
    # Port management
    # ------------------------------------------------------------------

    def list_output_ports(self) -> List[str]:
        """Return a list of available MIDI output port names."""
        return mido.get_output_names()

    def set_output_port(self, port_name: Optional[str]):
        """
        Select a MIDI output port by name.

        Passing None closes any currently open port and disables live output.
        """
        # Close any existing port
        if self._port is not None:
            self._port.close()
            self._port = None

        self._port_name = port_name

        if port_name is not None:
            # Open the new port
            self._port = mido.open_output(port_name)

    def has_output_port(self) -> bool:
        """Return True if a MIDI output port is currently open and ready."""
        return self._port is not None

    # ------------------------------------------------------------------
    # Live playback helpers
    # ------------------------------------------------------------------

    def stop_all_notes(self):
        """
        Send 'note_off' for all currently active notes to avoid stuck notes.

        This should be called when stopping playback or when jumping between
        positions in the pattern.
        """
        if not self._port:
            self._active_notes.clear()
            return

        for note, _row in self._active_notes:
            self._port.send(Message('note_off', note=note, velocity=0, channel=9))
        self._active_notes.clear()

    def send_step(self, bar_index: int, step_index: int,
                  metronome: bool = True):
        """
        Trigger the notes for a single step (across all rows).

        - First, any previously active notes are turned off.
        - Then, for each row, if the step velocity > 0, we send note_on.
        - Optionally, we send a metronome tick on quarter notes.

        This function does not schedule anything; it should be called
        at each "step tick" by the GUI layer (QTimer, etc.).
        """
        if not self._port:
            # No port, nothing to send
            self._active_notes.clear()
            return

        # Turn off all previously active notes
        self.stop_all_notes()

        # Track which notes are active for this step
        currently_active: List[Tuple[int, int]] = []

        # Send musical notes
        for row in range(self.model.num_rows):
            vel = self.model.get_velocity(row, bar_index, step_index)
            if vel > 0:
                meta = self.model.get_row_meta(row)
                note = meta.midi_note
                self._port.send(
                    Message('note_on', note=note, velocity=vel, channel=9)
                )
                currently_active.append((note, row))

        # Optional metronome tick: send on quarter notes (assuming 16th grid)
        if metronome:
            steps_per_beat = 4  # 16th-note grid means 4 steps per quarter
            if step_index % steps_per_beat == 0:
                # High woodblock or something clicky; 76 is a good one
                self._port.send(
                    Message('note_on', note=76, velocity=70, channel=9)
                )
                # We don't track metronome notes in _active_notes because
                # they are short and not critical if stuck.

        # Replace active notes with current
        self._active_notes = currently_active

    # ------------------------------------------------------------------
    # Tempo / swing utilities (for live playback, called from GUI)
    # ------------------------------------------------------------------

    @staticmethod
    def step_duration_ms(bpm: int, steps_per_bar: int,
                         swing_amount: float = 0.0,
                         global_step_index: int = 0) -> int:
        """
        Compute duration (in milliseconds) for the current step,
        including swing.

        Conceptual model:
        - Without swing, we assume a 4/4 bar with 'steps_per_bar' subdivisions.
          At 16 steps, that means a 16th-note grid (4 steps per beat).
        - Swing is approximated by alternating between shorter and longer steps.

        Parameters:
            bpm: Beats per minute.
            steps_per_bar: number of steps in one bar (16, 32, 64, etc.).
            swing_amount: 0.0 for straight timing, up to ~0.5 for heavy swing.
                          For simplicity, we treat swing as the proportion of
                          offset between "even" and "odd" steps.
            global_step_index: the absolute step index over the whole pattern
                               (bar0..barN, step0..stepM). This is used to
                               decide if this step is "even" or "odd".

        Implementation detail:
            - Base step duration is the bar duration divided by steps_per_bar.
            - With swing, we slightly shrink "even" steps and expand "odd" steps.
        """
        # Duration of a beat in ms
        beat_ms = 60000.0 / max(1, bpm)

        # Assume 4 beats per bar (4/4)
        bar_ms = beat_ms * 4.0

        # Base step duration in ms (without swing)
        base_step_ms = bar_ms / float(steps_per_bar)

        # No swing -> constant step duration
        if swing_amount <= 0.0:
            return int(base_step_ms)

        # Clamp swing between 0 and 0.5 to avoid crazy values
        swing_amount = max(0.0, min(0.5, swing_amount))

        # Determine whether this is an "even" or "odd" step
        if (global_step_index % 2) == 0:
            # "Even" step: slightly shorter
            factor = 1.0 - swing_amount
        else:
            # "Odd" step: slightly longer
            factor = 1.0 + swing_amount

        return int(base_step_ms * factor)

    # ------------------------------------------------------------------
    # MIDI file export
    # ------------------------------------------------------------------

    def export_to_midi_file(self, path: str, bpm: int):
        """
        Render the entire pattern into a Standard MIDI File and save it.

        The resulting MIDI file:
            - Contains a single track.
            - Uses channel 9 for drums (GM convention).
            - Plays bars sequentially from bar 0 to bar N-1.
            - Uses the stored velocities and MIDI notes from the model.
        """
        mid = MidiFile()
        track = MidiTrack()
        mid.tracks.append(track)

        # Set tempo meta event
        us_per_beat = int(60_000_000 / max(1, bpm))
        track.append(MetaMessage('set_tempo', tempo=us_per_beat, time=0))

        # Simple fixed ticks-per-beat and ticks-per-step relationship
        # We'll let mido default ticks_per_beat (usually 480).
        ticks_per_beat = mid.ticks_per_beat
        # For a 16-step bar grid, 4 steps per beat =>  ticks_per_step = ticks_per_beat / 4
        steps_per_beat = self.model.steps_per_bar / 4.0
        if steps_per_beat <= 0:
            steps_per_beat = 4.0
        ticks_per_step = int(ticks_per_beat / steps_per_beat)

        current_time = 0

        # Iterate bars and steps in order
        for bar in range(self.model.bars):
            for step in range(self.model.steps_per_bar):
                # For each step, we collect note_on and note_off events
                # and adjust the delta time accordingly.
                for row in range(self.model.num_rows):
                    vel = self.model.get_velocity(row, bar, step)
                    if vel > 0:
                        meta = self.model.get_row_meta(row)
                        note = meta.midi_note

                        # Note on at current_time
                        track.append(
                            Message('note_on', note=note, velocity=vel, channel=9,
                                    time=current_time)
                        )
                        # Note off after one step
                        track.append(
                            Message('note_off', note=note, velocity=0, channel=9,
                                    time=ticks_per_step)
                        )
                        current_time = 0  # we've consumed 'time' with the events

                # If no notes, just advance time by one step
                current_time += ticks_per_step

        # Final dummy event just to flush time if needed
        if current_time > 0:
            track.append(Message('note_off', note=0, velocity=0, time=current_time))

        # Save file
        mid.save(path)
