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
import tempfile
import unittest
from pathlib import Path

from library.lcd_clock.cli import DEFAULT_WEB_DIR, _resolve_web_dir, build_arg_parser


class TestArgDefaults(unittest.TestCase):
    def test_defaults(self):
        args = build_arg_parser().parse_args([])
        self.assertEqual(args.port, "AUTO")
        self.assertIsNone(args.web_dir)
        self.assertEqual(args.brightness, 10)
        self.assertEqual(args.host, "127.0.0.1")
        self.assertEqual(args.port_http, 8765)
        self.assertEqual(args.update_ms, 250)
        self.assertAlmostEqual(args.full_frame_threshold, 0.60)
        self.assertEqual(args.pixel_threshold, 10)
        self.assertFalse(args.open_browser)
        self.assertFalse(args.no_headless)
        self.assertIsNone(args.browser_path)
        self.assertFalse(args.reset_on_exit)
        self.assertFalse(args.debug)
        self.assertFalse(args.test_pattern)
        self.assertFalse(args.benchmark)

    def test_port_and_web_dir_can_be_overridden(self):
        args = build_arg_parser().parse_args(["--port", "COM6", "--web-dir", "C:\\some\\path"])
        self.assertEqual(args.port, "COM6")
        self.assertEqual(args.web_dir, Path("C:\\some\\path"))


class TestResolveWebDir(unittest.TestCase):
    def test_valid_dir_with_lcd_html_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "lcd.html").write_text("<html></html>")
            resolved = _resolve_web_dir(Path(tmp))
            self.assertEqual(resolved, Path(tmp))

    def test_dir_without_lcd_html_raises_a_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(SystemExit):
                _resolve_web_dir(Path(tmp))

    def test_none_falls_back_to_the_default_or_raises_a_clear_error(self):
        # The personal default path may not exist on the machine running the tests; either outcome is
        # correct as long as a missing default fails with a clear SystemExit, not an unhandled crash.
        if DEFAULT_WEB_DIR.exists():
            resolved = _resolve_web_dir(None)
            self.assertEqual(resolved, DEFAULT_WEB_DIR)
        else:
            with self.assertRaises(SystemExit):
                _resolve_web_dir(None)


if __name__ == "__main__":
    unittest.main()
