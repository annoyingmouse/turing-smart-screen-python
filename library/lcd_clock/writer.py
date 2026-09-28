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

# Thin abstraction over the physical LCD, so the bridge/benchmark/test-pattern logic can run against a
# fake writer in tests without any hardware attached.
from abc import ABC, abstractmethod

from PIL import Image


class LcdWriter(ABC):
    @property
    @abstractmethod
    def width(self) -> int:
        """Screen width in the display's current orientation."""

    @property
    @abstractmethod
    def height(self) -> int:
        """Screen height in the display's current orientation."""

    @abstractmethod
    def display(self, image: Image.Image, x: int, y: int, width: int, height: int) -> None:
        """Write `image` (already cropped to width x height) at (x, y)."""


class RealLcdWriter(LcdWriter):
    """Wraps a library.lcd.lcd_comm.LcdComm instance (e.g. LcdCommRevA)."""

    def __init__(self, lcd_comm):
        self._lcd_comm = lcd_comm

    @property
    def width(self) -> int:
        return self._lcd_comm.get_width()

    @property
    def height(self) -> int:
        return self._lcd_comm.get_height()

    def display(self, image: Image.Image, x: int, y: int, width: int, height: int) -> None:
        self._lcd_comm.DisplayPILImage(image, x=x, y=y, image_width=width, image_height=height)
