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

# --benchmark: measure real transfer performance for a full frame and several partial-update sizes, so
# the LCD update interval and full-frame threshold are chosen from evidence rather than guessed.
import time
from dataclasses import dataclass
from typing import List, Tuple

from PIL import Image

from library.lcd_clock.writer import LcdWriter

# (label, x, y, width, height) - sizes required by the feature spec, plus a clock-digit-sized region.
_REGIONS: List[Tuple[str, int, int, int, int]] = [
    ("full 480x320", 0, 0, 480, 320),
    ("region 240x160", 40, 40, 240, 160),
    ("region 120x80", 0, 0, 120, 80),
    ("clock-sized 118x73", 182, 94, 118, 73),
]


@dataclass(frozen=True)
class BenchmarkResult:
    label: str
    width: int
    height: int
    approx_bytes: int
    elapsed_seconds: float

    @property
    def updates_per_second(self) -> float:
        return 1.0 / self.elapsed_seconds if self.elapsed_seconds > 0 else float("inf")


def _pattern(width: int, height: int) -> Image.Image:
    # A busy per-pixel pattern, so RGB565 conversion/transfer isn't measuring a trivially empty image.
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            pixels[x, y] = (x % 256, y % 256, (x + y) % 256)
    return image


def run(writer: LcdWriter) -> List[BenchmarkResult]:
    results = []
    for label, x, y, width, height in _REGIONS:
        image = _pattern(width, height)
        start = time.perf_counter()
        writer.display(image, x, y, width, height)
        elapsed = time.perf_counter() - start
        approx_bytes = width * height * 2  # RGB565 on the wire

        result = BenchmarkResult(label, width, height, approx_bytes, elapsed)
        results.append(result)
        print(f"{label:>20}: {approx_bytes:>7} bytes  {elapsed:6.3f}s  {result.updates_per_second:5.2f} updates/s")

    return results
