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

# CLI wiring for lcd-clock.py. Kept in an importable module (rather than in the hyphenated entry point
# script itself) so `build_arg_parser()` can be unit-tested directly.
import argparse
import logging
import os
import signal
import sys
import threading
import time
from pathlib import Path

from library.lcd.lcd_comm_rev_a import LcdCommRevA, Orientation
from library.lcd_clock import benchmark, testpattern
from library.lcd_clock.bridge_server import FrameProcessor, LcdBridgeServer
from library.lcd_clock.headless_browser import HeadlessBrowser, find_browser_executable
from library.lcd_clock.writer import RealLcdWriter
from library.log import logger

LCD_WIDTH = 480
LCD_HEIGHT = 320

# Personal convenience default for the one machine this was built on; anyone else must pass --web-dir.
DEFAULT_WEB_DIR = Path(r"C:\Users\annoy\WebstormProjects\WireFrameJS\000-MISCELLANEOUS\HEDGECLOCK")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lcd-clock.py",
        description="Drive a physical Turing rev-A USB LCD with a live HEDGECLOCK render from a browser.",
    )
    parser.add_argument("--port", default="AUTO",
                         help="Serial COM port, e.g. COM6 (default: AUTO)")
    parser.add_argument("--web-dir", type=Path, default=None,
                         help="Path to the HEDGECLOCK directory (containing lcd.html). "
                              f"Defaults to {DEFAULT_WEB_DIR} if it exists.")
    parser.add_argument("--brightness", type=int, default=10,
                         help="Brightness percent 0-100 (default: 10 - keep modest on rev. A)")
    parser.add_argument("--host", default="127.0.0.1",
                         help="Bridge bind address (default: 127.0.0.1, localhost only)")
    parser.add_argument("--port-http", type=int, default=8765,
                         help="Bridge HTTP port (default: 8765)")
    parser.add_argument("--update-ms", type=int, default=250,
                         help="Minimum milliseconds between LCD updates (default: 250)")
    parser.add_argument("--full-frame-threshold", type=float, default=0.60,
                         help="Dirty-area fraction of the screen above which a full frame is sent "
                              "instead of a region (default: 0.60)")
    parser.add_argument("--pixel-threshold", type=int, default=10,
                         help="Per-channel pixel difference tolerance before a pixel counts as changed "
                              "(default: 10)")
    parser.add_argument("--open-browser", action="store_true",
                         help="Launch the auto-managed browser visibly instead of headlessly")
    parser.add_argument("--no-headless", action="store_true",
                         help="Don't auto-launch a browser at all - wait for one to be opened manually")
    parser.add_argument("--browser-path", type=Path, default=None,
                         help="Path to a Chrome/Edge executable, overriding auto-detection")
    parser.add_argument("--reset-on-exit", action="store_true",
                         help="Clear the LCD on shutdown instead of leaving the last frame shown")
    parser.add_argument("--debug", action="store_true", help="Verbose logging")
    parser.add_argument("--test-pattern", action="store_true",
                         help="Send a hardware test pattern (independent of HEDGECLOCK) and exit")
    parser.add_argument("--benchmark", action="store_true",
                         help="Run the transfer benchmark (independent of HEDGECLOCK) and exit")
    return parser


def _resolve_web_dir(web_dir: "Path | None") -> Path:
    if web_dir is None:
        if not DEFAULT_WEB_DIR.exists():
            raise SystemExit(
                "No --web-dir given and the default HEDGECLOCK location was not found. "
                "Pass --web-dir <path-to-HEDGECLOCK> (the folder containing lcd.html)."
            )
        web_dir = DEFAULT_WEB_DIR

    if not (web_dir / "lcd.html").is_file():
        raise SystemExit(f"--web-dir {web_dir} does not contain lcd.html - point it at the HEDGECLOCK folder.")

    return web_dir


def _open_lcd(port: str, brightness: int) -> LcdCommRevA:
    lcd_comm = LcdCommRevA(com_port=port, display_width=320, display_height=480)
    lcd_comm.Reset()
    lcd_comm.InitializeComm()
    lcd_comm.SetBrightness(level=brightness)
    lcd_comm.SetOrientation(orientation=Orientation.LANDSCAPE)
    return lcd_comm


def _run_standalone_mode(args) -> int:
    """Handles --test-pattern / --benchmark, which need the LCD but not the bridge server."""
    lcd_comm = _open_lcd(args.port, args.brightness)
    try:
        writer = RealLcdWriter(lcd_comm)
        if args.test_pattern:
            testpattern.run(writer)
        else:
            benchmark.run(writer)
    finally:
        lcd_comm.closeSerial()
    return 0


def main(argv=None) -> int:
    # Force line-buffered stdout: this process is often run detached/redirected to a log file, where
    # Python otherwise fully buffers stdout and the compact per-frame lines never show up until exit.
    sys.stdout.reconfigure(line_buffering=True)

    args = build_arg_parser().parse_args(argv)

    if args.debug:
        logger.setLevel(logging.DEBUG)

    if args.test_pattern or args.benchmark:
        return _run_standalone_mode(args)

    web_dir = _resolve_web_dir(args.web_dir)
    lcd_comm = _open_lcd(args.port, args.brightness)
    writer = RealLcdWriter(lcd_comm)
    processor = FrameProcessor(
        writer,
        pixel_threshold=args.pixel_threshold,
        full_frame_threshold=args.full_frame_threshold,
    )

    server = LcdBridgeServer(
        host=args.host,
        http_port=args.port_http,
        web_dir=web_dir,
        frame_width=LCD_WIDTH,
        frame_height=LCD_HEIGHT,
        processor=processor,
        update_interval_ms=args.update_ms,
        debug=args.debug,
    )
    server.start_writer()
    server_thread = threading.Thread(target=server.serve_forever, name="lcd-clock-http", daemon=True)
    server_thread.start()

    url = f"http://{args.host}:{args.port_http}/lcd.html"
    print("HEDGECLOCK LCD")
    print(f"Display: Turing/UsbMonitor rev A ({lcd_comm.get_width()}x{lcd_comm.get_height()})")
    print(f"Port: {args.port}")
    print(f"Resolution: {LCD_WIDTH} x {LCD_HEIGHT}")
    print(f"Brightness: {args.brightness}%")
    print(f"Bridge: http://{args.host}:{args.port_http}")

    browser: "HeadlessBrowser | None" = None
    if not args.no_headless:
        browser_path = args.browser_path or find_browser_executable()
        if browser_path is None:
            print("No Chrome/Edge found for the automatic browser launch - pass --browser-path, "
                  f"open {url} yourself, or use --no-headless to silence this.")
        else:
            browser = HeadlessBrowser(browser_path, url, LCD_WIDTH, LCD_HEIGHT, visible=args.open_browser)
            try:
                browser.start()
                print(f"Launched {'visible' if args.open_browser else 'headless'} browser automatically "
                      f"({browser_path.name})")
            except OSError as exc:
                print(f"Failed to launch the browser automatically: {exc}")
                browser = None

    if browser is None:
        print(f"Waiting for browser... open {url}")

    stop_requested = threading.Event()

    def _sighandler(signum, frame):
        stop_requested.set()

    signal.signal(signal.SIGINT, _sighandler)
    signal.signal(signal.SIGTERM, _sighandler)
    if os.name == "posix":
        signal.signal(signal.SIGQUIT, _sighandler)

    try:
        while not stop_requested.is_set():
            time.sleep(0.2)
    finally:
        print("Shutting down...")
        if browser is not None:
            browser.stop()
        server.stop()
        if args.reset_on_exit:
            lcd_comm.Clear()
        lcd_comm.closeSerial()

    return 0


if __name__ == "__main__":
    sys.exit(main())
