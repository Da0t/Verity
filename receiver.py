"""BLE still-photo transport. Python 3.10+; pip install -r requirements.txt."""
import argparse
import asyncio
from pathlib import Path
import secrets
import struct
import time
import zlib

SERVICE = "369f0001-7d5c-4f30-a16b-8c578d930001"
COMMAND = "369f0002-7d5c-4f30-a16b-8c578d930001"
STATUS = "369f0003-7d5c-4f30-a16b-8c578d930001"
DATA = "369f0004-7d5c-4f30-a16b-8c578d930001"
NOD = "369f0005-7d5c-4f30-a16b-8c578d930001"


async def capture_jpeg(client, timeout=60):
    """Return verified JPEG bytes; caller owns the connected BleakClient.

    Serialize calls per client. A timeout/disconnect fails this capture; reconnect
    and request a new photo rather than using a partial or stale image.
    """
    async def transfer():
        token = secrets.randbits(32)
        await client.write_gatt_char(COMMAND, struct.pack("<BI", 1, token), response=True)
        while True:
            raw = await client.read_gatt_char(STATUS)
            if len(raw) != 13:
                raise ValueError("Invalid camera status")
            state, frame_id, size, crc = struct.unpack("<BIII", raw)
            if frame_id == token:
                if state == 3:
                    raise RuntimeError("Camera capture failed; check JPEG mode and power")
                if state == 2:
                    break
            await asyncio.sleep(0.1)
        if not 4 <= size <= 1024 * 1024:
            raise ValueError(f"Invalid JPEG size: {size}")
        image = bytearray()
        while len(image) < size:
            offset = len(image)
            await client.write_gatt_char(
                COMMAND, struct.pack("<BII", 2, token, offset), response=True)
            packet = await client.read_gatt_char(DATA)
            if len(packet) <= 4 or struct.unpack_from("<I", packet)[0] != offset:
                raise ValueError("Missing or out-of-order image chunk")
            image.extend(packet[4:])
            if len(image) > size:
                raise ValueError("Image exceeds announced size")
        if zlib.crc32(image) != crc:
            raise ValueError("Image CRC mismatch")
        if not image.startswith(b"\xff\xd8") or not image.endswith(b"\xff\xd9"):
            raise ValueError("Invalid JPEG markers")
        return bytes(image)
    return await asyncio.wait_for(transfer(), timeout)


def save_jpeg(path, jpeg):
    """Atomically replace path so a failed capture never leaves a partial file."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(jpeg)
    temporary.replace(destination)


async def main(args):
    from bleak import BleakClient, BleakScanner
    device = await BleakScanner.find_device_by_filter(
        lambda d, ad: (d.address == args.address if args.address else
                       SERVICE in [u.lower() for u in ad.service_uuids]),
        timeout=15, service_uuids=[SERVICE])
    if device is None:
        raise RuntimeError("Camera not found; check power, firmware, and Bluetooth permission")
    print(f"Connecting to {device.name} ({device.address})")
    async with BleakClient(device) as client:
        while True:
            start = time.monotonic()
            jpeg = await capture_jpeg(client, args.timeout)
            save_jpeg(args.output, jpeg)
            print(f"Saved {len(jpeg):,} bytes to {args.output} in {time.monotonic()-start:.1f}s")
            if not args.interactive:
                return
            answer = await asyncio.to_thread(input, "Enter = fresh photo; q = quit: ")
            if answer.strip().lower() == "q":
                return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", help="Optional device address / macOS peripheral UUID")
    parser.add_argument("--output", default="latest.jpg")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--interactive", action="store_true")
    try:
        asyncio.run(main(parser.parse_args()))
    except (Exception, KeyboardInterrupt) as exc:
        parser.exit(1, f"Capture stopped: {exc}\n")
