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

from library.lcd_clock.headless_browser import (
    HeadlessBrowser,
    _DEFAULT_CANDIDATES,
    build_launch_args,
    find_browser_executable,
)


class TestFindBrowserExecutable(unittest.TestCase):
    def test_returns_the_first_existing_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp, "does-not-exist.exe")
            present = Path(tmp, "present.exe")
            present.write_text("")

            found = find_browser_executable([missing, present])
            self.assertEqual(found, present)

    def test_returns_none_when_nothing_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing_a = Path(tmp, "a.exe")
            missing_b = Path(tmp, "b.exe")
            self.assertIsNone(find_browser_executable([missing_a, missing_b]))

    def test_default_candidate_list_checks_chrome_before_edge(self):
        chrome_index = next(i for i, c in enumerate(_DEFAULT_CANDIDATES) if "Chrome" in c)
        edge_index = next(i for i, c in enumerate(_DEFAULT_CANDIDATES) if "Edge" in c)
        self.assertLess(chrome_index, edge_index)


class TestBuildLaunchArgs(unittest.TestCase):
    def test_headless_mode_includes_headless_and_anti_throttling_flags(self):
        args = build_launch_args(
            Path("browser.exe"), "http://127.0.0.1:8765/lcd.html", 480, 320,
            Path("C:/tmp/profile"), visible=False,
        )
        self.assertIn("--headless=new", args)
        self.assertIn("--disable-gpu", args)
        self.assertIn("--window-size=480,320", args)
        self.assertIn("--hide-scrollbars", args)
        for flag in (
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=CalculateNativeWinOcclusion",
        ):
            self.assertIn(flag, args)

    def test_visible_mode_omits_headless_only_flags(self):
        args = build_launch_args(
            Path("browser.exe"), "http://127.0.0.1:8765/lcd.html", 480, 320,
            Path("C:/tmp/profile"), visible=True,
        )
        self.assertNotIn("--headless=new", args)
        self.assertNotIn("--disable-gpu", args)
        self.assertNotIn("--hide-scrollbars", args)
        # Anti-throttling flags are still useful even for a visible-but-unfocused window.
        self.assertIn("--disable-background-timer-throttling", args)

    def test_always_includes_a_dedicated_user_data_dir_and_ends_with_the_url(self):
        url = "http://127.0.0.1:8765/lcd.html"
        user_data_dir = Path("C:/tmp/profile-x")
        for visible in (False, True):
            args = build_launch_args(
                Path("browser.exe"), url, 480, 320, user_data_dir, visible=visible,
            )
            self.assertIn(f"--user-data-dir={user_data_dir}", args)
            self.assertEqual(args[-1], url)


class TestHeadlessBrowserStop(unittest.TestCase):
    def test_stop_without_start_is_a_safe_no_op(self):
        browser = HeadlessBrowser(Path("browser.exe"), "http://127.0.0.1:8765/lcd.html", 480, 320)
        browser.stop()  # must not raise


if __name__ == "__main__":
    unittest.main()
