import asyncio
import struct
import unittest

from receiver import NOD
from test_receiver import Camera
from verity.device import Device


class Client(Camera):
    def __init__(self, fault=None, has_nod=True):
        super().__init__(fault)
        self.is_connected = True
        self.has_nod = has_nod
        self.services = self

    def get_characteristic(self, uuid):
        return object() if uuid == NOD and self.has_nod else None

    async def start_notify(self, uuid, callback):
        self.notify = callback

    async def disconnect(self):
        self.is_connected = False


class FakeDevice(Device):
    def __init__(self, *clients, **options):
        super().__init__(**options)
        self.clients = list(clients)
        self.opened = 0

    async def _open(self):
        self.opened += 1
        return self.clients.pop(0)

    def nod(self, seq=1):
        self._client.notify(None, struct.pack("<I", seq))


class DeviceTests(unittest.IsolatedAsyncioTestCase):
    async def test_capture(self):
        client = Client()
        device = FakeDevice(client)
        self.assertEqual(await device.capture_jpeg(), client.image)
        self.assertEqual(device.opened, 1)

    async def test_nods_coalesce(self):
        device = FakeDevice(Client())
        await device.connect()
        device.nod(1)
        device.nod(2)
        await asyncio.wait_for(device.wait_for_nod(), 1)
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(device.wait_for_nod(), 0.05)

    async def test_stale_nod_discarded(self):
        device = FakeDevice(Client(), nod_max_age=0.01)
        await device.connect()
        device.nod()
        await asyncio.sleep(0.03)
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(device.wait_for_nod(), 0.05)

    async def test_disconnect_mid_transfer_then_fresh_photo(self):
        class Dropping(Client):
            async def read_gatt_char(self, uuid):
                self.is_connected = False
                raise ConnectionError("Disconnected")
        first, second = Dropping(), Client()
        device = FakeDevice(first, second)
        with self.assertRaises(ConnectionError):
            await device.capture_jpeg()
        device._on_disconnect(first)
        self.assertEqual(await device.capture_jpeg(), second.image)
        self.assertEqual(device.opened, 2)

    async def test_nod_waiter_reconnects_after_disconnect(self):
        first, second = Client(), Client()
        device = FakeDevice(first, second)
        await device.connect()
        waiter = asyncio.create_task(device.wait_for_nod())
        await asyncio.sleep(0)
        first.is_connected = False
        device._on_disconnect(first)
        await asyncio.sleep(0)
        self.assertIs(device._client, second)
        device.nod()
        await asyncio.wait_for(waiter, 1)

    async def test_close_releases_waiter(self):
        device = FakeDevice(Client())
        await device.connect()
        waiter = asyncio.create_task(device.wait_for_nod())
        await asyncio.sleep(0)
        await device.close()
        with self.assertRaises(ConnectionError):
            await waiter

    async def test_duplicate_sequence_not_replayed(self):
        device = FakeDevice(Client())
        await device.connect(); device.nod(10)
        await device.wait_for_nod()
        device.nod(10)
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(device.wait_for_nod(), 0.01)
        await device.close()

    async def test_extended_nod_packet_compatible(self):
        device = FakeDevice(Client())
        await device.connect()
        device._on_nod(None, struct.pack('<II', 11, 1234))
        await asyncio.wait_for(device.wait_for_nod(), 0.1)
        await device.close()

    async def test_capture_total_deadline(self):
        class Slow(Client):
            async def read_gatt_char(self, uuid): await asyncio.sleep(10)
        device = FakeDevice(Slow())
        with self.assertRaises(TimeoutError):
            await device.capture_jpeg(timeout=0.01)
        await device.close()

    async def test_missing_nod_characteristic(self):
        client = Client(has_nod=False)
        with self.assertRaisesRegex(RuntimeError, "nod characteristic"):
            await FakeDevice(client).connect()
        self.assertFalse(client.is_connected)
        self.assertEqual(await FakeDevice(Client(has_nod=False), nods=False)
                         .capture_jpeg(), client.image)


if __name__ == "__main__":
    unittest.main()
