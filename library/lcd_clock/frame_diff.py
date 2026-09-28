# SPDX-License-Identifier: GPL-3.0-or-later
#
# turing-smart-screen-python - a Python system monitor and library for USB-C displays like Turing Smart Screen or XuanFang
# https://github.com/mathoudebine/turing-smart-screen-python/
#
# Copyright (C) 2021 Matthieu Houdebine (mathoudebine)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# Pure dirty-region diffing between two RGB frames: no I/O, no hardware, so it can be unit-tested
# without a physical display.
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass(frozen=True)
class Update:
    """What to send to the LCD for one frame. `kind` is "none" (nothing changed), "region" (send just
    the x/y/width/height crop) or "full" (send the whole screen)."""
    kind: str
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0


def compute_update(
        prev: Optional[np.ndarray],
        curr: np.ndarray,
        pixel_threshold: int = 10,
        full_frame_threshold: float = 0.60,
        pad: int = 4,
) -> Update:
    """Compare `curr` against `prev` (both HxWx3 uint8 RGB arrays of the same shape) and decide what
    needs to be sent to the LCD.

    - No `prev` (first frame): always a full-frame update.
    - No pixel differs by more than `pixel_threshold`: no update (ignores antialiasing/encoder noise).
    - Otherwise: the padded bounding box of changed pixels, clamped to the frame - or a full-frame
      update if that box covers more than `full_frame_threshold` of the screen area.
    """
    height, width = curr.shape[0], curr.shape[1]

    if prev is None or prev.shape != curr.shape:
        return Update(kind="full", x=0, y=0, width=width, height=height)

    diff = np.abs(curr.astype(np.int16) - prev.astype(np.int16)).max(axis=2)
    changed = diff > pixel_threshold

    if not changed.any():
        return Update(kind="none")

    rows = np.flatnonzero(np.any(changed, axis=1))
    cols = np.flatnonzero(np.any(changed, axis=0))
    y0, y1 = int(rows[0]), int(rows[-1])
    x0, x1 = int(cols[0]), int(cols[-1])

    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(width - 1, x1 + pad)
    y1 = min(height - 1, y1 + pad)

    box_width = x1 - x0 + 1
    box_height = y1 - y0 + 1

    if (box_width * box_height) / (width * height) > full_frame_threshold:
        return Update(kind="full", x=0, y=0, width=width, height=height)

    return Update(kind="region", x=x0, y=y0, width=box_width, height=box_height)
