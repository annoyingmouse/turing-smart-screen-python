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

# Auto-launches and manages a Chromium-based browser process so lcd-clock.py never needs a human to
# open lcd.html by hand. Headless by default; the JS pipeline (lcd-sketch.js/lcd-bridge.js) is
# completely unaware of and unchanged by this - it's just another browser tab to it.
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from library.log import logger

# Chrome first (more common on other machines), Edge as fallback - this machine only has Edge.
_DEFAULT_CANDIDATES = [
    "%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe",
    "%ProgramFiles(x86)%\\Google\\Chrome\\Application\\chrome.exe",
    "%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe",
    "%ProgramFiles%\\Microsoft\\Edge\\Application\\msedge.exe",
    "%ProgramFiles(x86)%\\Microsoft\\Edge\\Application\\msedge.exe",
]


def find_browser_executable(candidates: Optional[List[Path]] = None) -> Optional[Path]:
    """Returns the first existing browser executable from `candidates` (default: the built-in
    Chrome-then-Edge Windows install locations, environment-variable expanded)."""
    if candidates is None:
        candidates = [Path(os.path.expandvars(c)) for c in _DEFAULT_CANDIDATES]

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    return None


def build_launch_args(
        browser_path: Path,
        url: str,
        width: int,
        height: int,
        user_data_dir: Path,
        visible: bool = False,
) -> List[str]:
    """Builds the full argv for launching `browser_path` against `url`. Always uses a dedicated
    --user-data-dir so this instance is fully independent of any browser window the user already has
    open - critical, since otherwise the launch could just open a tab in their real browser instead of
    a separate, cleanly-terminable process."""
    args = [str(browser_path)]

    if not visible:
        args += [
            "--headless=new",
            "--disable-gpu",
            f"--window-size={width},{height}",
            "--hide-scrollbars",
        ]

    args += [
        "--no-first-run",
        "--disable-extensions",
        # Headless/background renderer processes are otherwise throttled as if the tab were an
        # unfocused background tab, which cuts HEDGECLOCK's ~1/sec redraw rate significantly.
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=CalculateNativeWinOcclusion",
        f"--user-data-dir={user_data_dir}",
        url,
    ]
    return args


class HeadlessBrowser:
    """Owns the lifecycle of one auto-launched browser process."""

    def __init__(self, browser_path: Path, url: str, width: int, height: int, visible: bool = False):
        self._browser_path = browser_path
        self._url = url
        self._width = width
        self._height = height
        self._visible = visible
        self._process: Optional[subprocess.Popen] = None
        self._user_data_dir: Optional[str] = None

    def start(self) -> None:
        self._user_data_dir = tempfile.mkdtemp(prefix="lcd-clock-browser-")
        args = build_launch_args(
            self._browser_path, self._url, self._width, self._height,
            Path(self._user_data_dir), visible=self._visible,
        )
        self._process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop(self, timeout: float = 5.0) -> None:
        if self._process is not None and self._process.poll() is None:
            pid = self._process.pid
            if os.name == "nt":
                # A plain terminate() only signals the one process handle; Chromium spawns a tree of
                # child processes that would otherwise be orphaned. taskkill /T /F already force-kills
                # the whole tree, so the wait() below just confirms it.
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            else:
                self._process.terminate()

            try:
                self._process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self._process.kill()
                try:
                    self._process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    logger.warning("Auto-launched browser process (PID %s) did not exit cleanly", pid)

        self._process = None

        if self._user_data_dir is not None:
            shutil.rmtree(self._user_data_dir, ignore_errors=True)
            self._user_data_dir = None
