# Verity ESP-NOW protocol v1

Both boards run routerless Wi-Fi STA on one configured channel (1–11), using one
explicit unicast peer each. Incoming packets require that configured sender MAC,
exact length, magic/version, supported type and valid fields. The peer is currently
unencrypted: MAC filtering and session tokens prevent accidental cross-talk and
stale delivery, **not malicious spoofing**. It is a bench prototype protocol.

All multibyte values are little endian. Never transmit a C++ struct directly.

| Byte | Size | Value |
| --- | --- | --- |
| 0 | 2 | ASCII VR |
| 2 | 1 | Version 1 |
| 3 | 1 | Type |
| 4 | 4 | Sender boot ID, random nonzero |
| 8 | 4 | Receiver boot ID (0 only in HELLO) |
| 12 | 4 | Camera lease token (sender nonce in HELLO) |
| 16 | 4 | Packet sequence, monotonic per sender boot; skips zero |
| 20 | 4 | Event ID, handshake fence or acknowledged packet sequence |
| 24 | 2 | Local event age in ms (NOD only) |
| 26 | 1 | Motion bits: sensor valid=1, calibrated=2, settled=4 |
| 27 | 1 | NOD_ACK disposition; 0 for other types |

Types: HELLO=1, CHALLENGE=2, READY=3, READY_ACK=4, STATUS=5, NOD=6,
NOD_ACK=7, RESET=8, STATUS_ACK=9. A settled flag requires sensor+calibrated flags.

## Establish a fresh lease

Sender sends HELLO with a fresh nonce and its current gesture counter. Camera
issues a unique per-boot lease in CHALLENGE and echoes that nonce in event. Sender
accepts only its outstanding nonce, discards pending gestures, snapshots its event
counter, and sends READY with that fence. Camera installs the fence and replies
READY_ACK echoing READY's packet sequence. Sender becomes active only after that
ACK. HELLO/READY each get four attempts 150 ms apart, then a 1000 ms backoff and a
new nonce. Camera challenges expire after 1500 ms.

Packets carry both boot IDs and the lease. A reboot, heartbeat expiry or BLE nod
subscription change fences the old lease. RESET echoes the obsolete sender lease;
the sender drops its pending nod and establishes a new one. A four-entry retired
boot ring additionally rejects recent old sensor boots. Delayed messages cannot
complete a new challenge without its nonce/token. This is replay control, not
cryptographic authentication.

## Heartbeat, nod delivery and freshness

STATUS publishes motion every 300 ms, or changed flags at no more than 10 Hz;
there is no raw IMU stream. STATUS_ACK echoes its packet sequence, providing
application liveness to the sensor. Camera considers the link/status stale after
1200 ms without a valid new packet; sender also expires camera application
liveness after 1200 ms. Duplicate/out-of-order packets do not refresh freshness.
Sequence comparisons support uint32 rollover within the usual half-range limit.

Every local nod advances its event counter. While disconnected or already waiting
for a nod ACK, gestures are dropped rather than queued. A pending nod has at most
four transmissions, 150 ms apart, a stable event ID and a new packet sequence per
attempt. It expires after 700 ms. Camera consumes each event once and returns:
Forwarded=1, Dropped=2, Duplicate=3, Expired=4. Duplicates never notify BLE twice;
Duplicate means previously consumed, not proof of successful end-to-end delivery.
A Forwarded ACK means BLE accepted the notification call, not that a person heard
feedback. ACK loss after consumption therefore cannot trigger a second action.

The receive callback stamps local arrival time and enqueues at most eight packets
without waiting. Main-loop processing rejects queue residence over 500 ms. NOD
freshness is sender-local age plus camera-local queue residence <=700 ms; no clocks
are synchronized or compared across boards. ESP-NOW itself adds unmeasured radio
latency, so these deadlines are bounds on application age/queueing, not a measured
end-to-end guarantee. Invalid or expired packets never yield settled=true.

Callbacks do not capture frames, notify BLE, log, allocate per packet or wait.
Only one radio send is in flight; MAC completion clears that slot. A busy/error
send may be dropped and the application's bounded retry recovers when possible.
A missing send callback does not cause an unbounded wait or overlapping sends;
the board must be restarted if its radio cannot recover. BLE JPEG messages and
four-byte nod sequence payloads remain unchanged; the Windows adapter needs no
production change. A reconnect never drains a historical gesture queue.

Host assertions cover encoding/validation, retries/ACK loss, duplicate/reordered
traffic, expiration, boot changes, BLE lease invalidation and millis rollover.
RF coexistence, physical gesture accuracy and latency require hardware testing.
