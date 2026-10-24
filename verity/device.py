"""Windows-side Device adapter: verified JPEG snapshots and IMU nod events over BLE.

Smoke test: python -m verity.device --count 10
"""
import argparse
import asyncio
import struct
import time

import receiver
from receiver import NOD, SERVICE


class Device:
    def __init__(self, address=None, scan_timeout=15.0, nods=True, nod_max_age=1.5):
        """address: optional BLE address; otherwise the first camera advertising SERVICE.
        nods: require and subscribe to the firmware nod characteristic.
        nod_max_age: seconds after which an unconsumed nod is stale and discarded.
        """
        self.address = address
        self.scan_timeout = scan_timeout
        self.nods = nods
        self.nod_max_age = nod_max_age
        self._client = None
        self._closed = False
        self._last_sequence = None
        self._last_nod = 0.0
        self._queue = asyncio.Queue()  # receipt time of a nod, or None on disconnect
        self._connect_lock = asyncio.Lock()
        self._capture_lock = asyncio.Lock()

    async def _open(self):
        from bleak import BleakClient, BleakScanner
        found = await BleakScanner.find_device_by_filter(
            lambda d, ad: (d.address == self.address if self.address else
                           SERVICE in [u.lower() for u in ad.service_uuids]),
            timeout=self.scan_timeout, service_uuids=[SERVICE])
        if found is None:
            raise RuntimeError("Camera not found; check power, firmware, and Bluetooth")
        client = BleakClient(found, disconnected_callback=self._on_disconnect)
        await client.connect()
        return client

    async def connect(self):
        """Connect if not already connected. Also used to reconnect after a failure."""
        async with self._connect_lock:
            if self._client is not None and self._client.is_connected:
                return
            self._closed = False
            client = await self._open()
            try:
                if self.nods:
                    if client.services.get_characteristic(NOD) is None:
                        raise RuntimeError("Firmware has no nod characteristic; "
                                           "flash nod firmware or use nods=False")
                    await client.start_notify(NOD, self._on_nod)
            except BaseException:
                await client.disconnect()
                raise
            self._client = client
            self._last_sequence = None

    def _on_nod(self, _sender, data):
        if len(data) not in (4, 8):
            return
        sequence = struct.unpack_from('<I', data)[0]
        if sequence == self._last_sequence:
            return
        self._last_sequence = sequence
        self._last_nod = time.monotonic()
        # Coalesce: only the newest activation matters.
        while not self._queue.empty():
            self._queue.get_nowait()
        self._queue.put_nowait(time.monotonic())

    def _on_disconnect(self, client):
        if client is self._client:
            self._queue.put_nowait(None)

    async def wait_for_nod(self):
        """Return once per fresh deliberate nod. Reconnects after a disconnect."""
        while True:
            if self._closed:
                raise ConnectionError("Device closed")
            await self.connect()
            received = await self._queue.get()
            if received is not None and time.monotonic() - received <= self.nod_max_age:
                return

    async def capture_jpeg(self, timeout=30.0):
        """Return fresh verified JPEG bytes or raise. Never returns a cached image."""
        async with asyncio.timeout(timeout):
            async with self._capture_lock:
                await self.connect()
                await asyncio.sleep(max(0, 0.35-(time.monotonic()-self._last_nod)))
                return await receiver.capture_jpeg(self._client, timeout)

    async def close(self):
        self._closed = True
        client, self._client = self._client, None
        self._queue.put_nowait(None)  # release a pending wait_for_nod
        if client is not None:
            await client.disconnect()


async def main(args):
    device = Device(args.address, nods=not args.no_nods)
    await device.connect()
    print("Connected." + ("" if args.no_nods else " Nod to capture."))
    try:
        for i in range(1, args.count + 1):
            if not args.no_nods:
                await device.wait_for_nod()
                print("Nod received")
            start = time.monotonic()
            try:
                jpeg = await device.capture_jpeg(args.timeout)
            except Exception as exc:
                print(f"Photo {i} failed: {exc!r}")
                continue
            receiver.save_jpeg(args.output, jpeg)
            print(f"Photo {i}: {len(jpeg):,} bytes in {time.monotonic()-start:.1f}s")
    finally:
        await device.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address")
    parser.add_argument("--output", default="latest.jpg")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--no-nods", action="store_true",
                        help="capture back-to-back with camera-only firmware")
    try:
        asyncio.run(main(parser.parse_args()))
    except (Exception, KeyboardInterrupt) as exc:
        parser.exit(1, f"Device test stopped: {exc}\n")
