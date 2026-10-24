#pragma once
#include <stddef.h>
#include <stdint.h>

namespace Verity {
// Explicit LE wire layout; never memcpy a compiler-dependent C++ struct.
static constexpr size_t PACKET_SIZE = 29;
static constexpr uint8_t VERSION = 2;
static constexpr uint32_t STATUS_INTERVAL = 300, STATUS_TTL = 1200;
static constexpr uint32_t QUEUE_TTL = 500, NOD_TTL = 700;
static constexpr uint32_t RETRY_INTERVAL = 150, MAX_ATTEMPTS = 4;
static constexpr uint32_t SYNC_BACKOFF = 1000, CHALLENGE_TTL = 1500;

enum class Type : uint8_t { Hello=1, Challenge=2, Ready=3, ReadyAck=4,
    Status=5, Nod=6, NodAck=7, Reset=8, StatusAck=9 };
enum class Ack : uint8_t { None=0, Forwarded=1, Dropped=2, Duplicate=3, Expired=4 };
enum Motion : uint8_t { SensorOk=1, Calibrated=2, Settled=4 };
// Nod packets carry any head gesture; also the BLE notification's kind byte.
enum Gesture : uint8_t { NoGesture=0, DoubleNod=1, DoubleLeft=2, DoubleRight=3 };

struct Packet {
    Type type=Type::Hello;
    uint32_t boot=0, target=0, token=0, seq=0, event=0;
    uint16_t age=0;
    uint8_t flags=0;
    Ack code=Ack::None;
    uint8_t gesture=NoGesture;
};
inline bool matchesPeer(const uint8_t* configured, const uint8_t* actual) {
    if (!configured || !actual) return false;
    for (unsigned i=0;i<6;++i) if (configured[i]!=actual[i]) return false;
    return true;
}
inline bool newer(uint32_t a, uint32_t b) {
    const uint32_t delta=a-b;
    return delta && delta < 0x80000000u;
}
inline uint32_t next(uint32_t& n) { if (++n==0) ++n; return n; }
inline uint32_t elapsed(uint32_t now, uint32_t before) { return now-before; }
inline void put32(uint8_t* p, uint32_t n) {
    for (unsigned i=0; i<4; ++i) p[i]=uint8_t(n>>(8*i));
}
inline uint32_t get32(const uint8_t* p) {
    return uint32_t(p[0]) | uint32_t(p[1])<<8 | uint32_t(p[2])<<16 | uint32_t(p[3])<<24;
}
inline bool motionValid(uint8_t flags) {
    return !(flags & ~uint8_t(7)) && (!(flags & Settled) ||
        (flags & (SensorOk|Calibrated))==(SensorOk|Calibrated));
}
inline bool sensorReady(uint8_t flags) {
    return (flags & (SensorOk|Calibrated))==(SensorOk|Calibrated);
}
inline bool valid(const Packet& p) {
    const auto type=static_cast<uint8_t>(p.type);
    if (type<1 || type>9 || !p.boot || !p.seq || !p.token || !motionValid(p.flags)) return false;
    if (p.type==Type::Hello) {
        if (p.target || p.age || p.code!=Ack::None) return false;
    } else if (!p.target) return false;
    if (p.type!=Type::Nod && p.age) return false;
    if (p.type==Type::Nod ? (p.gesture<DoubleNod || p.gesture>DoubleRight) : p.gesture) return false;
    if (p.type==Type::NodAck) {
        if (!p.event || p.flags || p.code<Ack::Forwarded || p.code>Ack::Expired) return false;
    } else if (p.code!=Ack::None) return false;
    if ((p.type==Type::Challenge || p.type==Type::ReadyAck || p.type==Type::StatusAck ||
         p.type==Type::Reset || p.type==Type::Nod) && !p.event) return false;
    if ((p.type==Type::Challenge || p.type==Type::ReadyAck || p.type==Type::StatusAck ||
         p.type==Type::Reset) && p.flags) return false;
    return true;
}
inline bool encode(const Packet& p, uint8_t* out, size_t size) {
    if (!out || size!=PACKET_SIZE || !valid(p)) return false;
    out[0]='V'; out[1]='R'; out[2]=VERSION; out[3]=static_cast<uint8_t>(p.type);
    put32(out+4,p.boot); put32(out+8,p.target); put32(out+12,p.token);
    put32(out+16,p.seq); put32(out+20,p.event);
    out[24]=uint8_t(p.age); out[25]=uint8_t(p.age>>8);
    out[26]=p.flags; out[27]=static_cast<uint8_t>(p.code); out[28]=p.gesture;
    return true;
}
inline bool decode(const uint8_t* data, size_t size, Packet& out) {
    if (!data || size!=PACKET_SIZE || data[0]!='V' || data[1]!='R' || data[2]!=VERSION) return false;
    Packet p;
    p.type=static_cast<Type>(data[3]); p.boot=get32(data+4); p.target=get32(data+8);
    p.token=get32(data+12); p.seq=get32(data+16); p.event=get32(data+20);
    p.age=uint16_t(data[24]) | uint16_t(data[25])<<8;
    p.flags=data[26]; p.code=static_cast<Ack>(data[27]); p.gesture=data[28];
    if (!valid(p)) return false;
    out=p; return true;
}
}
