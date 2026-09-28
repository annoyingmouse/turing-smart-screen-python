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

# --test-pattern: validate the physical LCD path independently of HEDGECLOCK/the browser bridge.
import time
from typing import Iterable, Tuple

from PIL import Image, ImageDraw

from library.lcd_clock.writer import LcdWriter


def _solid(width: int, height: int, color: Tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", (width, height), color)


def _checkerboard(width: int, height: int, tile: int = 20) -> Image.Image:
    image = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y in range(0, height, tile):
        for x in range(0, width, tile):
            if ((x // tile) + (y // tile)) % 2 == 0:
                draw.rectangle([x, y, x + tile - 1, y + tile - 1], fill=(255, 255, 255))
    return image


def _text(width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.text((10, 10), "HEDGECLOCK LCD test", fill=(255, 255, 255))
    return image


def frames(width: int, height: int) -> Iterable[Tuple[str, Image.Image]]:
    yield "black", _solid(width, height, (0, 0, 0))
    yield "white", _solid(width, height, (255, 255, 255))
    yield "red", _solid(width, height, (255, 0, 0))
    yield "green", _solid(width, height, (0, 255, 0))
    yield "blue", _solid(width, height, (0, 0, 255))
    yield "checkerboard", _checkerboard(width, height)
    yield "text", _text(width, height)


def run(writer: LcdWriter, hold_seconds: float = 2.0) -> None:
    for name, image in frames(writer.width, writer.height):
        print(f"Test pattern: {name}")
        writer.display(image, 0, 0, writer.width, writer.height)
        time.sleep(hold_seconds)
