"""
main_window.py

This module defines the MainWindow class, which is the central GUI for the
step sequencer. It glues together:

    - The SequencerModel (data and pattern operations)
    - The MidiEngine (file export + live playback)
    - The StepButton widgets (per-cell UI)
    - Qt controls for tempo, bars, steps-per-bar, swing, etc.

The focus here is on user interaction and visual representation.
"""

import os
from typing import Dict, Tuple

from PyQt6.QtWidgets import (
    QWidget, QGridLayout, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QLineEdit, QSpinBox, QPushButton, QFileDialog,
    QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt, QTimer

from sequencer_model import SequencerModel
from midi_engine import MidiEngine
from step_button import StepButton


class MainWindow(QWidget):
    """
    MainWindow is the top-level PyQt6 widget for the sequencer.

    It creates:
        - A tempo control (slider + field)
        - A bars selector
        - A steps-per-bar selector (16/32/64)
        - A swing slider
        - A MIDI output port selector
        - The 2D grid of StepButton instances
        - Row controls (name + MIDI note per row)
        - Toolbar buttons for:
            * Play / Stop
            * Copy / Paste bar
            * Randomize / Humanize
            * Save / Load pattern (JSON)
            * Export MIDI file (.mid)

    The class holds:
        - A SequencerModel (pattern data)
        - A MidiEngine (MIDI I/O)
        - A QTimer to drive live playback
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Step Sequencer MIDI Generator (Extended)")

        # Core model and MIDI engine
        self.model = SequencerModel(num_rows=8, bars=4, steps_per_bar=16)
        self.midi_engine = MidiEngine(self.model)

        # Playback-related state
        self._is_playing = False
        self._current_bar = 0
        self._current_step = 0
        self._global_step = 0  # counts across bars, used for swing
        self._edit_bar = 0     # which bar is currently being edited in the UI

        # Timer for live playback
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._advance_step)

        # Storage for StepButton instances: grid_buttons[row][step]
        self.grid_buttons = []

        # Storage for row controls (name field + MIDI note spinner)
        self.row_name_fields = []
        self.row_note_spinners = []

        # UI elements that need to be accessed later
        self.tempo_slider = None
        self.tempo_field = None
        self.bars_spin = None
        self.steps_per_bar_combo = None
        self.swing_slider = None
        self.swing_field = None
        self.port_combo = None
        self.edit_bar_spin = None

        # Build all widgets and layouts
        self._build_ui()

        # Once the UI exists, populate initial ports list
        self._refresh_midi_ports()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        """
        Create all widgets, lay them out, and wire up signals/slots.
        """
        main_layout = QVBoxLayout()

        # ---------------- Tempo controls ----------------
        tempo_layout = QHBoxLayout()
        tempo_label = QLabel("Tempo (BPM):")

        self.tempo_slider = QSlider(Qt.Orientation.Horizontal)
        self.tempo_slider.setRange(40, 240)
        self.tempo_slider.setValue(120)

        self.tempo_field = QLineEdit("120")
        self.tempo_field.setFixedWidth(50)

        # Keep slider and text field in sync
        self.tempo_slider.valueChanged.connect(
            lambda val: self.tempo_field.setText(str(val))
        )
        self.tempo_field.textChanged.connect(self._update_tempo_from_text)

        tempo_layout.addWidget(tempo_label)
        tempo_layout.addWidget(self.tempo_slider)
        tempo_layout.addWidget(self.tempo_field)

        # ---------------- Bars and edit bar controls ----------------
        bars_layout = QHBoxLayout()
        bars_label = QLabel("Bars (length):")
        self.bars_spin = QSpinBox()
        self.bars_spin.setRange(1, 64)
        self.bars_spin.setValue(self.model.bars)
        self.bars_spin.valueChanged.connect(self._bars_changed)

        edit_bar_label = QLabel("Edit Bar:")
        self.edit_bar_spin = QSpinBox()
        self.edit_bar_spin.setRange(0, self.model.bars - 1)
        self.edit_bar_spin.setValue(0)
        self.edit_bar_spin.valueChanged.connect(self._edit_bar_changed)

        bars_layout.addWidget(bars_label)
        bars_layout.addWidget(self.bars_spin)
        bars_layout.addSpacing(20)
        bars_layout.addWidget(edit_bar_label)
        bars_layout.addWidget(self.edit_bar_spin)

        # ---------------- Steps per bar & Swing ----------------
        steps_swing_layout = QHBoxLayout()

        steps_label = QLabel("Steps / Bar:")
        self.steps_per_bar_combo = QComboBox()
        for val in [16, 32, 64]:
            self.steps_per_bar_combo.addItem(str(val))
        self.steps_per_bar_combo.setCurrentText(str(self.model.steps_per_bar))
        self.steps_per_bar_combo.currentTextChanged.connect(self._steps_per_bar_changed)

        swing_label = QLabel("Swing:")
        self.swing_slider = QSlider(Qt.Orientation.Horizontal)
        self.swing_slider.setRange(0, 50)  # 0..50 => 0.0..0.5
        self.swing_slider.setValue(0)
        self.swing_field = QLineEdit("0.0")
        self.swing_field.setFixedWidth(50)

        self.swing_slider.valueChanged.connect(self._swing_slider_changed)
        self.swing_field.textChanged.connect(self._swing_field_changed)

        steps_swing_layout.addWidget(steps_label)
        steps_swing_layout.addWidget(self.steps_per_bar_combo)
        steps_swing_layout.addSpacing(20)
        steps_swing_layout.addWidget(swing_label)
        steps_swing_layout.addWidget(self.swing_slider)
        steps_swing_layout.addWidget(self.swing_field)

        # ---------------- MIDI output port selection ----------------
        port_layout = QHBoxLayout()
        port_label = QLabel("MIDI Out Port:")
        self.port_combo = QComboBox()
        refresh_button = QPushButton("Refresh Ports")
        refresh_button.clicked.connect(self._refresh_midi_ports)

        self.port_combo.currentTextChanged.connect(self._port_selected)

        port_layout.addWidget(port_label)
        port_layout.addWidget(self.port_combo)
        port_layout.addWidget(refresh_button)

        # ---------------- Toolbar buttons ----------------
        toolbar_layout = QHBoxLayout()

        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self._toggle_play)

        copy_bar_button = QPushButton("Copy Bar")
        copy_bar_button.clicked.connect(self._copy_current_bar)

        paste_bar_button = QPushButton("Paste Bar")
        paste_bar_button.clicked.connect(self._paste_current_bar)

        randomize_button = QPushButton("Randomize Bar")
        randomize_button.clicked.connect(self._randomize_current_bar)

        humanize_button = QPushButton("Humanize Bar")
        humanize_button.clicked.connect(self._humanize_current_bar)

        save_pattern_button = QPushButton("Save Pattern")
        save_pattern_button.clicked.connect(self._save_pattern)

        load_pattern_button = QPushButton("Load Pattern")
        load_pattern_button.clicked.connect(self._load_pattern)

        export_midi_button = QPushButton("Export MIDI")
        export_midi_button.clicked.connect(self._export_midi)

        toolbar_layout.addWidget(self.play_button)
        toolbar_layout.addSpacing(15)
        toolbar_layout.addWidget(copy_bar_button)
        toolbar_layout.addWidget(paste_bar_button)
        toolbar_layout.addWidget(randomize_button)
        toolbar_layout.addWidget(humanize_button)
        toolbar_layout.addSpacing(15)
        toolbar_layout.addWidget(save_pattern_button)
        toolbar_layout.addWidget(load_pattern_button)
        toolbar_layout.addWidget(export_midi_button)

        # ---------------- Sequencer grid ----------------
        self.grid_layout = QGridLayout()
        self._build_grid()

        # ---------------- Assemble main layout ----------------
        main_layout.addLayout(tempo_layout)
        main_layout.addLayout(bars_layout)
        main_layout.addLayout(steps_swing_layout)
        main_layout.addLayout(port_layout)
        main_layout.addLayout(toolbar_layout)
        main_layout.addLayout(self.grid_layout)

        self.setLayout(main_layout)

    def _build_grid(self):
        """
        Construct the 2D grid: row metadata + StepButtons.

        This is called initially and whenever we change steps-per-bar
        in order to recreate the grid with the new width.
        """
        # Clear any existing widgets from the layout
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

        self.grid_buttons = []
        self.row_name_fields = []
        self.row_note_spinners = []

        # Header row
        header_label = QLabel("Part Name / Note")
        self.grid_layout.addWidget(header_label, 0, 0)

        # Step headers
        for col in range(self.model.steps_per_bar):
            lbl = QLabel(str(col + 1))
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.grid_layout.addWidget(lbl, 0, col + 1)

        # Rows of actual data
        for row in range(self.model.num_rows):
            meta = self.model.get_row_meta(row)

            # Row name field
            name_field = QLineEdit(meta.name)
            name_field.editingFinished.connect(
                lambda r=row, nf=name_field: self._row_name_changed(r, nf)
            )

            # MIDI note spinner
            note_spin = QSpinBox()
            note_spin.setRange(0, 127)
            note_spin.setValue(meta.midi_note)
            note_spin.valueChanged.connect(
                lambda val, r=row: self._row_note_changed(r, val)
            )

            row_box = QHBoxLayout()
            row_box.addWidget(name_field)
            row_box.addWidget(QLabel("Note:"))
            row_box.addWidget(note_spin)

            row_container = QWidget()
            row_container.setLayout(row_box)

            self.grid_layout.addWidget(row_container, row + 1, 0)

            self.row_name_fields.append(name_field)
            self.row_note_spinners.append(note_spin)

            # Step buttons for this row
            button_row = []
            for col in range(self.model.steps_per_bar):
                btn = StepButton()
                # Initialize from model's current data for the edit bar
                vel = self.model.get_velocity(row, self._edit_bar, col)
                btn.velocity = vel

                # When the StepButton velocity changes, update the model
                btn.velocityChanged.connect(
                    lambda v, r=row, c=col: self._cell_velocity_changed(r, c, v)
                )

                self.grid_layout.addWidget(btn, row + 1, col + 1)
                button_row.append(btn)

            self.grid_buttons.append(button_row)

    # ------------------------------------------------------------------
    # UI Callbacks / State Sync
    # ------------------------------------------------------------------

    def _update_tempo_from_text(self):
        """
        Keep tempo slider synced with the numeric text field.

        We keep error-handling simple: invalid entries are ignored.
        """
        try:
            val = int(self.tempo_field.text())
        except ValueError:
            return
        val = max(40, min(240, val))
        self.tempo_slider.setValue(val)

    def _bars_changed(self, value: int):
        """When the user changes the total bars, update the model."""
        self.model.set_bars(value)
        # Update edit-bar spin range so it stays valid
        self.edit_bar_spin.setRange(0, self.model.bars - 1)
        # If the current edit bar is now out of range, clamp it
        if self._edit_bar >= self.model.bars:
            self._edit_bar = self.model.bars - 1
            self.edit_bar_spin.setValue(self._edit_bar)
        # No need to rebuild grid; only length changed.

    def _edit_bar_changed(self, value: int):
        """
        When the user selects a different bar to edit, we keep the model
        intact, but we reload the UI's StepButtons from that bar.
        """
        self._edit_bar = value
        # Refresh grid buttons to show velocity for this bar
        for row in range(self.model.num_rows):
            for col in range(self.model.steps_per_bar):
                vel = self.model.get_velocity(row, self._edit_bar, col)
                self.grid_buttons[row][col].velocity = vel

    def _steps_per_bar_changed(self, text: str):
        """
        Handle change in steps-per-bar (e.g., from 16 to 32).

        We update the model, then rebuild the grid to reflect new width.
        """
        try:
            steps = int(text)
        except ValueError:
            return

        self.model.set_steps_per_bar(steps)
        self._edit_bar = 0
        self.edit_bar_spin.setValue(0)
        self._build_grid()

    def _swing_slider_changed(self, val: int):
        """Update swing text when slider changes."""
        swing = val / 100.0
        self.swing_field.setText(f"{swing:.2f}")

    def _swing_field_changed(self, text: str):
        """Update swing slider when text changes."""
        try:
            v = float(text)
        except ValueError:
            return
        v = max(0.0, min(0.5, v))
        self.swing_slider.setValue(int(v * 100))

    def _row_name_changed(self, row: int, name_field: QLineEdit):
        """Store updated row name in the model."""
        meta = self.model.get_row_meta(row)
        self.model.set_row_meta(row, name_field.text(), meta.midi_note)

    def _row_note_changed(self, row: int, new_note: int):
        """Store updated MIDI note in the model."""
        meta = self.model.get_row_meta(row)
        self.model.set_row_meta(row, meta.name, new_note)

    def _cell_velocity_changed(self, row: int, col: int, velocity: int):
        """
        Whenever any StepButton changes velocity, mirror that in the model
        for the currently edited bar.
        """
        self.model.set_velocity(row, self._edit_bar, col, velocity)

    def _refresh_midi_ports(self):
        """Query MidiEngine for port names and populate combo box."""
        ports = self.midi_engine.list_output_ports()
        current = self.port_combo.currentText()

        self.port_combo.blockSignals(True)
        self.port_combo.clear()
        self.port_combo.addItem("(None)")
        for p in ports:
            self.port_combo.addItem(p)
        self.port_combo.blockSignals(False)

        # Restore previously selected if possible
        if current and current in ports:
            self.port_combo.setCurrentText(current)
        else:
            self.port_combo.setCurrentText("(None)")
            self.midi_engine.set_output_port(None)

    def _port_selected(self, text: str):
        """Handle user selecting a new MIDI out port."""
        if text == "(None)":
            self.midi_engine.set_output_port(None)
        else:
            self.midi_engine.set_output_port(text)

    # ------------------------------------------------------------------
    # Playback Control
    # ------------------------------------------------------------------

    def _toggle_play(self):
        """Start or stop live playback."""
        if self._is_playing:
            self._stop_playback()
        else:
            self._start_playback()

    def _start_playback(self):
        """Initialize playback state and start the timer."""
        if self._is_playing:
            return

        # Reset playback positions
        self._current_bar = 0
        self._current_step = 0
        self._global_step = 0

        # Ensure no stuck notes
        self.midi_engine.stop_all_notes()

        # Compute initial interval and start timer
        bpm = self._current_bpm()
        swing = self._current_swing()
        interval = self.midi_engine.step_duration_ms(
            bpm, self.model.steps_per_bar, swing, self._global_step
        )
        if interval <= 0:
            interval = 1

        self.play_timer.start(interval)
        self._is_playing = True
        self.play_button.setText("Stop")

    def _stop_playback(self):
        """Stop timer and send note-off to all notes."""
        if not self._is_playing:
            return
        self.play_timer.stop()
        self.midi_engine.stop_all_notes()
        self._is_playing = False
        self.play_button.setText("Play")

    def _current_bpm(self) -> int:
        """Convenience: get the current BPM from the tempo field."""
        try:
            bpm = int(self.tempo_field.text())
        except ValueError:
            bpm = 120
        bpm = max(40, min(240, bpm))
        return bpm

    def _current_swing(self) -> float:
        """Get current swing value as a float (0.0..0.5)."""
        try:
            s = float(self.swing_field.text())
        except ValueError:
            s = 0.0
        s = max(0.0, min(0.5, s))
        return s

    def _advance_step(self):
        """
        Called on each timer tick. We:

            - Send notes for the current step via MidiEngine.
            - Advance step/bar counters.
            - Compute the next timer interval (for swing).
        """
        # Play the current step
        self.midi_engine.send_step(self._current_bar, self._current_step, metronome=True)

        # Advance step and wrap across bars
        self._current_step += 1
        self._global_step += 1

        if self._current_step >= self.model.steps_per_bar:
            self._current_step = 0
            self._current_bar += 1
            if self._current_bar >= self.model.bars:
                # Loop back to first bar
                self._current_bar = 0

        # Compute next interval based on BPM and swing
        bpm = self._current_bpm()
        swing = self._current_swing()
        interval = self.midi_engine.step_duration_ms(
            bpm, self.model.steps_per_bar, swing, self._global_step
        )
        if interval <= 0:
            interval = 1
        self.play_timer.start(interval)

    # ------------------------------------------------------------------
    # Bar operations (copy/paste/randomize/humanize)
    # ------------------------------------------------------------------

    def _copy_current_bar(self):
        """Copy the currently edited bar to the model's internal buffer."""
        self.model.copy_bar(self._edit_bar)

    def _paste_current_bar(self):
        """
        Paste the last copied bar into the currently edited bar, then
        update the UI to show it.
        """
        self.model.paste_bar(self._edit_bar)
        # Refresh buttons to reflect pasted data
        for row in range(self.model.num_rows):
            for col in range(self.model.steps_per_bar):
                vel = self.model.get_velocity(row, self._edit_bar, col)
                self.grid_buttons[row][col].velocity = vel

    def _randomize_current_bar(self):
        """Randomize the currently edited bar."""
        self.model.randomize_bar(self._edit_bar, density=0.3, min_vel=40, max_vel=120)
        # Sync UI
        for row in range(self.model.num_rows):
            for col in range(self.model.steps_per_bar):
                vel = self.model.get_velocity(row, self._edit_bar, col)
                self.grid_buttons[row][col].velocity = vel

    def _humanize_current_bar(self):
        """Humanize velocities (slight random variation) for current bar."""
        self.model.humanize_velocities(self._edit_bar, amount=10)
        # Sync UI
        for row in range(self.model.num_rows):
            for col in range(self.model.steps_per_bar):
                vel = self.model.get_velocity(row, self._edit_bar, col)
                self.grid_buttons[row][col].velocity = vel

    # ------------------------------------------------------------------
    # Pattern save/load and MIDI export
    # ------------------------------------------------------------------

    def _save_pattern(self):
        """Open a save dialog and write pattern JSON."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Pattern JSON", "pattern.json", "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            self.model.save_to_file(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save pattern:\n{e}")
        else:
            QMessageBox.information(self, "Saved", f"Pattern saved to:\n{path}")

    def _load_pattern(self):
        """Open a file dialog and load a pattern JSON file."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Pattern JSON", "", "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            loaded = SequencerModel.load_from_file(path)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load pattern:\n{e}")
            return

        # Replace current model with loaded one
        self.model = loaded
        self.midi_engine.model = self.model

        # Update UI elements to reflect loaded configuration
        self.bars_spin.setValue(self.model.bars)
        self.steps_per_bar_combo.setCurrentText(str(self.model.steps_per_bar))
        self.edit_bar_spin.setRange(0, self.model.bars - 1)
        self.edit_bar_spin.setValue(0)
        self._edit_bar = 0

        self._build_grid()

    def _export_midi(self):
        """Prompt for file path and ask MidiEngine to export .mid file."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export MIDI File", "sequence.mid", "MIDI Files (*.mid)"
        )
        if not path:
            return

        bpm = self._current_bpm()
        try:
            self.midi_engine.export_to_midi_file(path, bpm)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export MIDI:\n{e}")
            return

        QMessageBox.information(self, "Exported", f"MIDI file saved to:\n{path}")
