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

# Fake LcdWriter so tests never need physical hardware.
from typing import List, Tuple

from PIL import Image

from library.lcd_clock.writer import LcdWriter


class FakeLcdWriter(LcdWriter):
    def __init__(self, width: int = 480, height: int = 320):
        self._width = width
        self._height = height
        self.calls: List[Tuple[Image.Image, int, int, int, int]] = []

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    def display(self, image: Image.Image, x: int, y: int, width: int, height: int) -> None:
        self.calls.append((image, x, y, width, height))
