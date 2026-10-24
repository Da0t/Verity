import asyncio
import struct
import unittest
from unittest.mock import AsyncMock, patch
from verity.device import Device, NOD


class Client:
    def __init__(self, device, disconnected_callback):
        self.is_connected = False
        self.disconnected = disconnected_callback
        self.callback = None
    async def connect(self): self.is_connected = True
    async def start_notify(self, uuid, callback):
        assert uuid == NOD
        self.callback = callback
    async def stop_notify(self, uuid): pass
    async def disconnect(self): self.is_connected = False


class DeviceTests(unittest.IsolatedAsyncioTestCase):
    async def make(self):
        scanner = type('Scanner', (), {'find_device_by_filter': AsyncMock(return_value=object())})
        device = Device(scanner=scanner, client_factory=Client, settle=0)
        await device.connect()
        self.addAsyncCleanup(device.close)
        return device

    async def test_nod_deduplication(self):
        device = await self.make()
        packet = struct.pack('<II', 1, 200)
        device.client.callback(None, packet)
        device.client.callback(None, packet)
        await device.wait_for_nod()
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(device.wait_for_nod(), 0.01)

    async def test_disconnect_wakes_waiter(self):
        device = await self.make()
        task = asyncio.create_task(device.wait_for_nod())
        await asyncio.sleep(0)
        device.client.is_connected = False
        device.client.disconnected(device.client)
        with self.assertRaises(ConnectionError):
            await task

    async def test_capture_returns_verified_transport_result(self):
        device = await self.make()
        with patch('verity.device.capture_jpeg', AsyncMock(return_value=b'image')) as capture:
            self.assertEqual(await device.capture_jpeg(), b'image')
            capture.assert_awaited_once()

    async def test_capture_deadline(self):
        device = await self.make()
        async def slow(*args, **kwargs): await asyncio.sleep(1)
        with patch('verity.device.capture_jpeg', slow), self.assertRaises(TimeoutError):
            await device.capture_jpeg(timeout=0.01)

    async def test_old_nods_not_replayed(self):
        device = await self.make()
        device.events.put_nowait(0.0)
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(device.wait_for_nod(), 0.01)

    async def test_close_wakes_waiter(self):
        device = await self.make()
        task = asyncio.create_task(device.wait_for_nod())
        await asyncio.sleep(0)
        await device.close()
        with self.assertRaises(ConnectionError): await task
