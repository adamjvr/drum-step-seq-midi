# Drum Step Sequencer MIDI Generator (PyQt6)

> **Status:** Early prototype, work-in-progress  
> **Author:** Adam Vadala-Roth (GhostPCB / Roth Amplification)

---

## Overview

This project is a **drum step sequencer** with a **PyQt6 GUI** that can:

- Display an **8-row** (drum parts) × **N-step** (steps per bar) grid.
- Allow you to **edit patterns visually** using clickable step buttons.
- Assign **velocity levels per step** (not just on/off).
- Configure **MIDI note** and **name** for each row.
- Control **tempo**, **number of bars**, **steps per bar**, and **swing**.
- **Randomize and humanize** drum patterns.
- **Copy/paste** entire bars.
- **Save/load** patterns to/from JSON.
- **Export to MIDI file**.
- Optionally output **live MIDI** to hardware/softsynth ports (via `mido` + `python-rtmidi`).

The goal is to provide a lightweight, scriptable, open-source drum machine sequencer.

---

## Screenshot Placeholder

Insert a screenshot of the GUI here:


Recommended usage:


---

## Features

### 1. Grid-Based Sequencer

- **8 drum parts (rows)**.
- **16 / 32 / 64 steps per bar**.
- Multi-level velocity via `StepButton`:
  - Left click: cycle velocity (Off → Low → Mid → High).
  - Right click: turn off.
- Each row has:
  - Editable **name**.
  - Editable **MIDI note**.

### 2. Tempo, Swing, and Resolution

- **Tempo:** 40–240 BPM (slider + numeric field).
- **Swing:** 0.0–0.5 (slider + numeric field).
- **Steps per bar:** 16, 32, or 64.

Swing affects **live playback timing** (not MIDI export).

### 3. Bars and Pattern Editing

- Set total bars (1–64).
- Use “Edit Bar” spinbox to switch which bar is displayed in the grid.
- **Copy Bar** and **Paste Bar** allow fast duplication.
- **Randomize Bar:** auto-generate hits with density + velocity range.
- **Humanize Bar:** slightly perturb velocities for natural feel.

### 4. MIDI Output

#### Export to File
- Creates `.mid` files using:
  - Track 0
  - Channel 10 (GM drums)
  - Correct note-on/note-off timing per step
  - Row MIDI note assignments
  - Step velocity values

#### Live MIDI Output
- Uses `mido` with `python-rtmidi` backend.
- Select MIDI port from drop-down.
- If backend is unavailable or misconfigured, the GUI proceeds without crashing.

### 5. Playback Engine

- **Play/Stop** using Qt `QTimer`.
- On each tick:
  - Play notes for current step.
  - Optional metronome tick on quarter notes.
  - Apply swing to real-time timing.
- Loops over all bars.

### 6. Pattern Persistence

- **Save Pattern:** writes JSON file including:
  - Rows, bars, steps per bar
  - Velocity grid
  - MIDI note assignments
  - Row names
- **Load Pattern:** restores full sequencer state and rebuilds UI grid.

---

## File Structure

project-root/
└── src/
├── main.py
├── main_window.py
├── sequencer_model.py
├── midi_engine.py
├── step_button.py
└── README.md (this file)


### `main.py`
- Entry point.
- Creates QApplication, instantiates `MainWindow`, starts the app.

### `main_window.py`
- Full GUI.
- Builds UI, connects signals, manages playback timing, interacts with model + MIDI engine.

### `sequencer_model.py`
- Pure data model.
- Stores pattern structure.
- Handles:
  - Set/get velocity
  - Set bars / steps-per-bar
  - Copy/paste bar
  - Randomize / humanize
  - Save/load JSON

### `midi_engine.py`
- All MIDI I/O.
- Exports MIDI files.
- Handles live MIDI playback.
- Calculates swing-adjusted step durations.

### `step_button.py`
- Per-step UI widget.
- Stores velocity.
- Emits `velocityChanged(int)`.

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/<yourname>/drum-step-seq-midi.git
cd drum-step-seq-midi/src

```

### 2. Install Dependencies


```bash
pip install pyqt6 mido python-rtmidi

```

On Linux, ensure ALSA/JACK MIDI support is working.
On macOS, use the IAC Bus.
On Windows, use loopMIDI for virtual ports.

### Running the Program

```bash
python main.py

```

Basic Usage

1. Set the tempo
Adjust slider or type in BPM.

2. Select bars
Set total bars and choose which bar to edit.

3. Choose steps-per-bar resolution
16, 32, or 64.

4. Adjust swing
Useful for more groove feel during live playback.

5. Assign row names and MIDI notes
Name drum parts and choose MIDI notes.

6. Edit the step grid
Left-click = cycle velocity, Right-click = off.

7. Live playback
  - Select MIDI out port (optional).
  - Click Play.

8. Randomize / Humanize
Automatically generate or soften patterns.

9. Save / Load patterns
Everything goes into a JSON file.

10. Export MIDI
Produces a .mid ready for DAWs (Ableton, FL, Reaper, Logic, etc.)


### Troubleshooting
MIDI Ports Missing

You likely installed the wrong package (rtmidi instead of python-rtmidi):

```bash
pip uninstall rtmidi
pip install python-rtmidi mido
```

Live Playback Doesn’t Make Sound

Make sure a synth/drum machine is listening on the selected port.

Or import the exported MIDI file into your DAW.

GUI Works but Live MIDI Fails

Backend may not be available; the program stays functional regardless.

