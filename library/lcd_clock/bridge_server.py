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

# Local-only HTTP bridge: serves the HEDGECLOCK LCD page as static files, and accepts posted canvas
# frames on /frame. Frame handling and LCD writes happen on a dedicated writer thread so a burst of
# frames never queues more than the single newest one, and so serial writes are never overlapped.
import functools
import http.server
import io
import threading
import time
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, UnidentifiedImageError

from library.lcd_clock.frame_diff import compute_update
from library.lcd_clock.writer import LcdWriter
from library.log import logger

MAX_FRAME_BYTES = 2 * 1024 * 1024  # generous for an uncompressed 480x320 PNG; rejects anything absurd


class FrameError(ValueError):
    """A malformed/invalid incoming frame - the HTTP handler turns this into a clean 4xx response."""


def decode_frame(body: bytes, expected_width: int, expected_height: int) -> np.ndarray:
    if not body:
        raise FrameError("Empty frame body")

    try:
        image = Image.open(io.BytesIO(body))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise FrameError(f"Could not decode frame as an image: {exc}") from exc

    if image.size != (expected_width, expected_height):
        raise FrameError(
            f"Frame is {image.size[0]}x{image.size[1]}, expected {expected_width}x{expected_height}"
        )

    return np.array(image.convert("RGB"))


class FrameProcessor:
    """Owns the dirty-region diff against the last frame actually written, and pushes updates to the
    LcdWriter. Only ever called from the bridge server's single writer thread - not thread-safe on its
    own."""

    def __init__(self, writer: LcdWriter, pixel_threshold: int, full_frame_threshold: float, pad: int = 4):
        self._writer = writer
        self._pixel_threshold = pixel_threshold
        self._full_frame_threshold = full_frame_threshold
        self._pad = pad
        self._prev_frame: Optional[np.ndarray] = None

    def process(self, frame: np.ndarray) -> None:
        update = compute_update(
            self._prev_frame, frame,
            pixel_threshold=self._pixel_threshold,
            full_frame_threshold=self._full_frame_threshold,
            pad=self._pad,
        )
        if update.kind == "none":
            return

        crop = frame[update.y:update.y + update.height, update.x:update.x + update.width]
        image = Image.fromarray(crop, mode="RGB")

        start = time.perf_counter()
        self._writer.display(image, update.x, update.y, update.width, update.height)
        elapsed = time.perf_counter() - start

        self._prev_frame = frame
        location = "" if update.kind == "full" else f" @ {update.x},{update.y}"
        print(f"Frame: {update.kind} {update.width}x{update.height}{location} - {elapsed:.2f}s")


class _FrameHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/frame":
            self.send_error(404)
            return

        if not self.server.accepting_frames:
            self.send_error(503, "Shutting down")
            return

        content_length = self.headers.get("Content-Length")
        if content_length is None:
            self.send_error(411, "Content-Length required")
            return
        try:
            length = int(content_length)
        except ValueError:
            self.send_error(400, "Invalid Content-Length")
            return
        if length > MAX_FRAME_BYTES:
            self.send_error(413, "Frame too large")
            return

        body = self.rfile.read(length)

        try:
            frame = decode_frame(body, self.server.frame_width, self.server.frame_height)
        except FrameError as exc:
            self.send_error(400, str(exc))
            return

        self.server.submit_frame(frame)
        self.send_response(204)
        self.end_headers()

    def log_message(self, format_, *args):
        if self.server.debug:
            logger.debug("bridge: " + (format_ % args))


class LcdBridgeServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, host: str, http_port: int, web_dir: Path, frame_width: int, frame_height: int,
                 processor: FrameProcessor, update_interval_ms: int, debug: bool = False):
        handler_cls = functools.partial(_FrameHandler, directory=str(web_dir))
        super().__init__((host, http_port), handler_cls)
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.debug = debug
        self.accepting_frames = True

        self._first_frame_seen = False
        self._processor = processor
        self._update_interval = update_interval_ms / 1000.0
        self._pending_frame: Optional[np.ndarray] = None
        self._pending_lock = threading.Lock()
        self._new_frame_event = threading.Event()
        self._stop_event = threading.Event()
        self._writer_thread = threading.Thread(target=self._writer_loop, name="lcd-clock-writer", daemon=True)

    def start_writer(self) -> None:
        self._writer_thread.start()

    def submit_frame(self, frame: np.ndarray) -> None:
        if not self._first_frame_seen:
            self._first_frame_seen = True
            print("Browser connected")
        with self._pending_lock:
            self._pending_frame = frame
        self._new_frame_event.set()

    def _writer_loop(self) -> None:
        last_sent = 0.0
        while not self._stop_event.is_set():
            got_frame = self._new_frame_event.wait(timeout=0.5)
            if self._stop_event.is_set():
                break
            if not got_frame:
                continue  # periodic wake to re-check _stop_event

            elapsed = time.monotonic() - last_sent
            if elapsed < self._update_interval:
                time.sleep(self._update_interval - elapsed)
            if self._stop_event.is_set():
                break

            with self._pending_lock:
                frame = self._pending_frame
                self._pending_frame = None
                self._new_frame_event.clear()

            if frame is None:
                continue

            last_sent = time.monotonic()
            try:
                self._processor.process(frame)
            except Exception:
                logger.exception("Failed to write frame to LCD")

    def stop(self) -> None:
        """Stop accepting new frames, let any in-flight transfer finish, then tear the server down."""
        self.accepting_frames = False
        self._stop_event.set()
        self._new_frame_event.set()
        self._writer_thread.join(timeout=max(5.0, self._update_interval * 4))
        self.shutdown()
        self.server_close()
