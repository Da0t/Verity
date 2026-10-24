"""BLE camera/IMU adapter. One connection and one capture at a time."""
import asyncio
import struct
import time
from receiver import SERVICE, capture_jpeg

NOD = "369f0005-7d5c-4f30-a16b-8c578d930001"


class Device:
    def __init__(self, *, address=None, settle=0.35, scan_timeout=15,
                 scanner=None, client_factory=None):
        self.address = address
        self.settle = settle
        self.scan_timeout = scan_timeout
        self.scanner = scanner
        self.client_factory = client_factory
        self.client = None
        self.events = asyncio.Queue(maxsize=1)
        self.capture_lock = asyncio.Lock()
        self.last_nod = 0.0
        self.last_sequence = None
        self.loop = None
        self.closing = False

    def _enqueue(self, value):
        if self.events.full():
            self.events.get_nowait()
        self.events.put_nowait(value)

    def _notification(self, sender, packet):
        if len(packet) != 8:
            return
        sequence, _device_millis = struct.unpack("<II", packet)
        if sequence == self.last_sequence:
            return
        self.last_sequence = sequence
        now = time.monotonic()
        self.last_nod = now
        self._enqueue(now)

    def _disconnect(self, client):
        if self.loop and not self.loop.is_closed() and not self.closing:
            self.loop.call_soon_threadsafe(self._enqueue, ConnectionError("Glasses disconnected"))

    async def connect(self):
        if self.client and self.client.is_connected:
            return
        if self.client:
            await self.close()
        self.loop = asyncio.get_running_loop()
        self.closing = False
        self.last_sequence = None
        while not self.events.empty():
            self.events.get_nowait()
        if self.scanner is None or self.client_factory is None:
            from bleak import BleakClient, BleakScanner
            self.scanner = self.scanner or BleakScanner
            self.client_factory = self.client_factory or BleakClient
        device = await self.scanner.find_device_by_filter(
            lambda d, ad: (d.address.lower() == self.address.lower() if self.address else
                           SERVICE in [u.lower() for u in ad.service_uuids]),
            timeout=self.scan_timeout, service_uuids=[SERVICE])
        if device is None:
            raise ConnectionError("Glasses not found; check power and Bluetooth")
        self.client = self.client_factory(device, disconnected_callback=self._disconnect)
        try:
            await self.client.connect()
            await self.client.start_notify(NOD, self._notification)
        except BaseException:
            await self.close()
            raise

    async def wait_for_nod(self):
        while True:
            if not self.client or not self.client.is_connected:
                raise ConnectionError("Glasses are not connected")
            event = await self.events.get()
            if isinstance(event, Exception):
                raise event
            if time.monotonic() - event <= 1.0:
                return

    async def capture_jpeg(self, timeout=30.0):
        async with self.capture_lock:
            async with asyncio.timeout(timeout):
                if not self.client or not self.client.is_connected:
                    raise ConnectionError("Glasses are not connected")
                await asyncio.sleep(max(0, self.settle - (time.monotonic()-self.last_nod)))
                return await capture_jpeg(self.client, timeout=timeout)

    async def close(self):
        self.closing = True
        self._enqueue(ConnectionError("Glasses closed"))
        client, self.client = self.client, None
        if client and client.is_connected:
            try:
                await client.stop_notify(NOD)
            finally:
                await client.disconnect()
