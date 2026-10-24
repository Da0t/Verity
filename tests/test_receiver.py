import asyncio
import struct
import unittest
import zlib

from receiver import COMMAND, STATUS, capture_jpeg


class Camera:
    def __init__(self, fault=None, chunk=18):
        self.image = b"\xff\xd8" + bytes(range(256)) * 3 + b"\xff\xd9"
        self.token = 0
        self.offset = 0
        self.fault = fault
        self.chunk = chunk

    async def write_gatt_char(self, uuid, data, response):
        assert uuid == COMMAND and response
        self.token = struct.unpack_from("<I", data, 1)[0]
        if data[0] == 2:
            self.offset = struct.unpack_from("<I", data, 5)[0]

    async def read_gatt_char(self, uuid):
        if uuid == STATUS:
            if self.fault == "malformed":
                return b""
            return struct.pack("<BIII", 3 if self.fault == "capture" else 2,
                               self.token ^ (1 if self.fault == "stale" else 0),
                               len(self.image), zlib.crc32(self.image) ^
                               (1 if self.fault == "crc" else 0))
        offset = self.offset + (1 if self.fault == "offset" else 0)
        payload = self.image[self.offset:self.offset+self.chunk]
        return struct.pack("<I", offset) + (b"" if self.fault == "empty" else payload)


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_minimum_and_larger_mtu(self):
        for chunk in (18, 242, 508):
            camera = Camera(chunk=chunk)
            self.assertEqual(await capture_jpeg(camera), camera.image)

    async def test_bad_packets_rejected(self):
        for fault in ("crc", "offset", "empty", "malformed"):
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                await capture_jpeg(Camera(fault))

    async def test_capture_error(self):
        with self.assertRaises(RuntimeError):
            await capture_jpeg(Camera("capture"))

    async def test_stale_frame_times_out(self):
        with self.assertRaises(asyncio.TimeoutError):
            await capture_jpeg(Camera("stale"), timeout=0.02)

    async def test_invalid_jpeg_rejected(self):
        camera = Camera()
        camera.image = b"not a jpeg"
        with self.assertRaisesRegex(ValueError, "JPEG markers"):
            await capture_jpeg(camera)

    async def test_disconnect_propagates(self):
        class Disconnected(Camera):
            async def read_gatt_char(self, uuid):
                raise ConnectionError("Disconnected")
        with self.assertRaises(ConnectionError):
            await capture_jpeg(Disconnected())


if __name__ == "__main__":
    unittest.main()
