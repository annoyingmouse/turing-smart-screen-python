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
import unittest

import numpy as np

from library.lcd_clock.frame_diff import compute_update

WIDTH, HEIGHT = 20, 10  # small frame, purely for fast/clear test arithmetic


def _blank():
    return np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)


class TestComputeUpdate(unittest.TestCase):
    def test_no_previous_frame_is_a_full_update(self):
        curr = _blank()
        update = compute_update(None, curr)
        self.assertEqual(update.kind, "full")
        self.assertEqual((update.x, update.y, update.width, update.height), (0, 0, WIDTH, HEIGHT))

    def test_identical_frames_produce_no_update(self):
        prev = _blank()
        curr = _blank()
        update = compute_update(prev, curr)
        self.assertEqual(update.kind, "none")

    def test_single_pixel_change_produces_a_padded_region(self):
        prev = _blank()
        curr = _blank()
        curr[5, 10] = (255, 255, 255)  # row=5 (y), col=10 (x)

        update = compute_update(prev, curr, pixel_threshold=10, pad=1, full_frame_threshold=0.9)

        self.assertEqual(update.kind, "region")
        self.assertEqual((update.x, update.y, update.width, update.height), (9, 4, 3, 3))

    def test_large_change_exceeding_threshold_triggers_full_frame(self):
        prev = _blank()
        curr = _blank()
        curr[:, :] = (255, 255, 255)  # entire frame changed

        update = compute_update(prev, curr, full_frame_threshold=0.60)

        self.assertEqual(update.kind, "full")
        self.assertEqual((update.x, update.y, update.width, update.height), (0, 0, WIDTH, HEIGHT))

    def test_crop_coordinates_match_the_exact_changed_rectangle_with_no_padding(self):
        prev = _blank()
        curr = _blank()
        curr[2:4, 5:10] = (255, 255, 255)  # rows 2-3 (y), cols 5-9 (x) -> 5 wide, 2 tall

        update = compute_update(prev, curr, pad=0, full_frame_threshold=0.9)

        self.assertEqual(update.kind, "region")
        self.assertEqual((update.x, update.y, update.width, update.height), (5, 2, 5, 2))

    def test_pixel_difference_tolerance_ignores_sub_threshold_noise(self):
        prev = _blank()
        curr = _blank()
        curr[3, 3] = (10, 10, 10)  # exactly at the threshold, not over it

        update = compute_update(prev, curr, pixel_threshold=10)
        self.assertEqual(update.kind, "none")

        curr[3, 3] = (11, 11, 11)  # one over the threshold
        update = compute_update(prev, curr, pixel_threshold=10, pad=0, full_frame_threshold=0.9)
        self.assertEqual(update.kind, "region")
        self.assertEqual((update.x, update.y, update.width, update.height), (3, 3, 1, 1))

    def test_bounding_box_clamps_at_frame_edges(self):
        prev = _blank()
        curr = _blank()
        curr[0, 0] = (255, 255, 255)  # top-left corner

        update = compute_update(prev, curr, pad=4, full_frame_threshold=0.9)

        self.assertEqual(update.kind, "region")
        self.assertEqual((update.x, update.y, update.width, update.height), (0, 0, 5, 5))

    def test_mismatched_frame_shape_triggers_full_update(self):
        prev = np.zeros((HEIGHT, WIDTH - 1, 3), dtype=np.uint8)
        curr = _blank()
        update = compute_update(prev, curr)
        self.assertEqual(update.kind, "full")


if __name__ == "__main__":
    unittest.main()
