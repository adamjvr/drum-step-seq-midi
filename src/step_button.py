"""
step_button.py

This module defines the StepButton class, which is a custom Qt widget used
for each cell in the step sequencer grid.

Historically, the step cells were simple ON/OFF toggle buttons. To support
per-step velocity, this class now:

    - Stores a discrete velocity value (0..127), with several "levels"
    - Visually indicates the velocity level by changing color brightness
    - Notifies the sequencer when its velocity changes via a Qt signal

This makes StepButton super reusable: it does not know anything about bars
or rows; it only knows that "I am a cell with a velocity value that the
outside world can control and observe".
"""

from PyQt6.QtWidgets import QPushButton
from PyQt6.QtCore import pyqtSignal, Qt


class StepButton(QPushButton):
    """
    StepButton is a square button representing a single step in the sequencer.

    Key behavior:
    - Internally stores a "velocity level" instead of a simple checked/unchecked.
    - Velocity is represented as an integer in [0, 127].
    - A set of discrete velocity levels is used for quick cycling (e.g., 0, 40, 80, 120).
    - Left-click cycles through velocity levels.
    - The button's background color reflects velocity:
        * 0   => dark/offs
        * low => dim green
        * mid => medium green
        * high => bright green
    - Emits velocityChanged(int) whenever the internal velocity changes.
    """

    # This signal lets the main window / sequencer model know that
    # the velocity for this step was updated.
    velocityChanged = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        # Define the discrete velocity levels that this button cycles through.
        # You can tweak these values to taste. 0 = off.
        self.velocity_levels = [0, 40, 80, 120]

        # Start with the 'off' state (zero velocity)
        self._velocity_index = 0

        # Make the button square and visually consistent
        self.setFixedSize(30, 30)
        self.setCheckable(False)  # we now manage state manually, not with Qt's "checked"

        # Ensure no text clutter on the button
        self.setText("")

        # Render initial style based on starting velocity
        self.update_style()

    @property
    def velocity(self) -> int:
        """
        Return the current velocity value for this step.

        This is what the sequencer model will store and use when generating
        MIDI notes. A velocity of 0 means "this step is effectively off".
        """
        return self.velocity_levels[self._velocity_index]

    @velocity.setter
    def velocity(self, value: int):
        """
        Directly set the velocity of this button to the nearest defined level.

        This is used when loading patterns from disk or when sync'ing the UI
        from the underlying sequencer model.
        """
        # Find the closest velocity level index
        closest_index = 0
        closest_diff = 9999
        for i, lvl in enumerate(self.velocity_levels):
            diff = abs(lvl - value)
            if diff < closest_diff:
                closest_diff = diff
                closest_index = i

        if closest_index != self._velocity_index:
            self._velocity_index = closest_index
            self.update_style()
            self.velocityChanged.emit(self.velocity)

    def cycle_velocity(self):
        """
        Advance to the next velocity level in the list.

        This is called when the user left-clicks the button. Cycling behavior:
            0 -> low -> mid -> high -> back to 0 -> ...
        """
        self._velocity_index = (self._velocity_index + 1) % len(self.velocity_levels)
        self.update_style()
        self.velocityChanged.emit(self.velocity)

    def mousePressEvent(self, event):
        """
        Override the mousePressEvent to implement custom behavior.

        Interpretation:
        - Left click: cycle through velocity levels (primary interaction).
        - Right click: quickly reset to OFF (velocity = 0).

        Note: We still call the base class implementation so that Qt's
        internal event handling remains satisfied (e.g., focus changes).
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.cycle_velocity()
        elif event.button() == Qt.MouseButton.RightButton:
            # Reset to OFF state (index 0 corresponds to velocity_levels[0] == 0)
            self._velocity_index = 0
            self.update_style()
            self.velocityChanged.emit(self.velocity)

        super().mousePressEvent(event)

    def update_style(self):
        """
        Adjust the button's visual appearance based on its current velocity.

        Higher velocities use brighter green. OFF uses a dark/grayish color.
        """
        vel = self.velocity

        if vel == 0:
            # OFF state: a dark grey background
            color = "#333333"
        elif vel <= 40:
            # Low velocity: dim green
            color = "#227744"
        elif vel <= 80:
            # Medium velocity: medium green
            color = "#33aa55"
        else:
            # High velocity: bright green
            color = "#55ff88"

        self.setStyleSheet(
            f"background-color: {color};"
            "border: 1px solid black;"
        )

    def is_active(self) -> bool:
        """
        Convenience method used by some callers that conceptually
        treat the step as ON/OFF, regardless of actual velocity value.

        Returns True if velocity > 0, False otherwise.
        """
        return self.velocity > 0
