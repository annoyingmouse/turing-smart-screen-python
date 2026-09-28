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
import http.client
import io
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from library.lcd_clock import bridge_server
from library.lcd_clock.bridge_server import FrameError, FrameProcessor, LcdBridgeServer, decode_frame
from tests.lcd_clock.fakes import FakeLcdWriter

WIDTH, HEIGHT = 4, 2


def _png_bytes(width: int, height: int, color=(1, 2, 3)) -> bytes:
    image = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


class TestDecodeFrame(unittest.TestCase):
    def test_valid_png_of_expected_size_decodes_to_an_rgb_array(self):
        array = decode_frame(_png_bytes(WIDTH, HEIGHT), WIDTH, HEIGHT)
        self.assertEqual(array.shape, (HEIGHT, WIDTH, 3))

    def test_malformed_body_raises_frame_error(self):
        with self.assertRaises(FrameError):
            decode_frame(b"not a png", WIDTH, HEIGHT)

    def test_empty_body_raises_frame_error(self):
        with self.assertRaises(FrameError):
            decode_frame(b"", WIDTH, HEIGHT)

    def test_wrong_dimensions_raise_frame_error(self):
        with self.assertRaises(FrameError):
            decode_frame(_png_bytes(WIDTH + 1, HEIGHT), WIDTH, HEIGHT)


class TestFrameProcessor(unittest.TestCase):
    def test_first_frame_triggers_exactly_one_full_write(self):
        writer = FakeLcdWriter(width=WIDTH, height=HEIGHT)
        processor = FrameProcessor(writer, pixel_threshold=10, full_frame_threshold=0.6)
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

        processor.process(frame)

        self.assertEqual(len(writer.calls), 1)
        _, x, y, w, h = writer.calls[0]
        self.assertEqual((x, y, w, h), (0, 0, WIDTH, HEIGHT))

    def test_identical_second_frame_triggers_no_write(self):
        writer = FakeLcdWriter(width=WIDTH, height=HEIGHT)
        processor = FrameProcessor(writer, pixel_threshold=10, full_frame_threshold=0.6)
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)

        processor.process(frame)
        processor.process(frame.copy())

        self.assertEqual(len(writer.calls), 1)  # only the initial full write


class TestBridgeServerHttp(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        Path(self.tmpdir.name, "lcd.html").write_text("<html></html>")
        self.writer = FakeLcdWriter(width=WIDTH, height=HEIGHT)
        processor = FrameProcessor(self.writer, pixel_threshold=10, full_frame_threshold=0.6)
        self.server = LcdBridgeServer(
            host="127.0.0.1", http_port=0, web_dir=Path(self.tmpdir.name),
            frame_width=WIDTH, frame_height=HEIGHT, processor=processor,
            update_interval_ms=10,
        )
        self.server.start_writer()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.stop()
        self.thread.join(timeout=2)
        self.tmpdir.cleanup()

    def _post(self, body: bytes) -> http.client.HTTPResponse:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        conn.request("POST", "/frame", body=body, headers={"Content-Length": str(len(body))})
        response = conn.getresponse()
        response.read()
        conn.close()
        return response

    def _wait_for_writer_calls(self, count: int, timeout: float = 2.0):
        deadline = time.time() + timeout
        while len(self.writer.calls) < count and time.time() < deadline:
            time.sleep(0.01)

    def test_valid_frame_is_written_exactly_once(self):
        response = self._post(_png_bytes(WIDTH, HEIGHT))
        self.assertEqual(response.status, 204)

        self._wait_for_writer_calls(1)
        self.assertEqual(len(self.writer.calls), 1)
        _, x, y, w, h = self.writer.calls[0]
        self.assertEqual((x, y, w, h), (0, 0, WIDTH, HEIGHT))

    def test_malformed_body_is_rejected_and_writer_never_called(self):
        response = self._post(b"not a png")
        self.assertEqual(response.status, 400)

        time.sleep(0.1)
        self.assertEqual(self.writer.calls, [])

    def test_wrong_dimensions_are_rejected_and_writer_never_called(self):
        response = self._post(_png_bytes(WIDTH + 1, HEIGHT + 1))
        self.assertEqual(response.status, 400)

        time.sleep(0.1)
        self.assertEqual(self.writer.calls, [])

    def test_oversized_content_length_is_rejected_before_reading_the_body(self):
        # Deliberately lie about Content-Length so a correctly-behaving server must reject based on the
        # header alone, without blocking trying to read bytes that were never sent.
        oversized_length = bridge_server.MAX_FRAME_BYTES + 1
        request = (
            f"POST /frame HTTP/1.1\r\n"
            f"Host: 127.0.0.1\r\n"
            f"Content-Length: {oversized_length}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        with socket.create_connection(("127.0.0.1", self.port), timeout=2) as sock:
            sock.sendall(request)
            sock.settimeout(2)
            response = sock.recv(4096)

        self.assertIn(b"413", response)
        self.assertEqual(self.writer.calls, [])


class TestFrameCoalescing(unittest.TestCase):
    """The writer thread must only ever act on the newest pending frame, never build a backlog."""

    def test_frames_submitted_before_the_writer_starts_collapse_to_the_latest(self):
        tmpdir = tempfile.TemporaryDirectory()
        try:
            Path(tmpdir.name, "lcd.html").write_text("<html></html>")
            writer = FakeLcdWriter(width=WIDTH, height=HEIGHT)
            processor = FrameProcessor(writer, pixel_threshold=10, full_frame_threshold=0.6)
            server = LcdBridgeServer(
                host="127.0.0.1", http_port=0, web_dir=Path(tmpdir.name),
                frame_width=WIDTH, frame_height=HEIGHT, processor=processor,
                update_interval_ms=500,
            )
            # server.stop() waits on serve_forever() to acknowledge shutdown, so it must be running
            # even though this test never sends it an HTTP request.
            serve_thread = threading.Thread(target=server.serve_forever, daemon=True)
            serve_thread.start()
            try:
                frame_a = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
                frame_b = np.full((HEIGHT, WIDTH, 3), 100, dtype=np.uint8)
                frame_c = np.full((HEIGHT, WIDTH, 3), 200, dtype=np.uint8)  # this one should "win"

                # Submitted before the writer thread exists, so all three are queued into the single
                # pending slot before anything can be consumed.
                server.submit_frame(frame_a)
                server.submit_frame(frame_b)
                server.submit_frame(frame_c)

                server.start_writer()

                deadline = time.time() + 2
                while not writer.calls and time.time() < deadline:
                    time.sleep(0.01)

                self.assertEqual(len(writer.calls), 1)
                image, x, y, w, h = writer.calls[0]
                self.assertEqual((x, y, w, h), (0, 0, WIDTH, HEIGHT))
                self.assertEqual(image.getpixel((0, 0)), (200, 200, 200))
            finally:
                server.stop()
                serve_thread.join(timeout=2)
        finally:
            tmpdir.cleanup()


if __name__ == "__main__":
    unittest.main()
