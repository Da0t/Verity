#pragma once
#include "Protocol.h"

namespace Verity {
struct Action { bool reply=false, nod=false; Packet packet; };

class CameraLink {
 public:
    explicit CameraLink(uint32_t boot, uint32_t nonceSeed=1):boot_(boot),nonce_(nonceSeed) {}
    void invalidate() { active_=pending_=false; }
    void tick(uint32_t now) {
        if (active_ && elapsed(now,lastRx_)>=STATUS_TTL) active_=false;
        if (pending_ && elapsed(now,challengeAt_)>=CHALLENGE_TTL) pending_=false;
    }
    bool linked(uint32_t now) const { return active_ && elapsed(now,lastRx_)<STATUS_TTL; }
    bool fresh(uint32_t now) const { return linked(now) && elapsed(now,statusAt_)<STATUS_TTL; }
    bool settled(uint32_t now) const { return fresh(now) && sensorReady(flags_) && (flags_ & Settled); }
    const char* reason(uint32_t now) const {
        if (!linked(now)) return "remote IMU link missing/stale";
        if (!fresh(now)) return "remote motion status stale";
        if (!sensorReady(flags_)) return "remote sensor unavailable/calibrating";
        return settled(now) ? "remote IMU settled" : "remote IMU moving";
    }
    Action receive(const Packet& p, uint32_t receivedAt, uint32_t now, bool canForward) {
        tick(now);
        if (!valid(p) || elapsed(now,receivedAt)>QUEUE_TTL) return {};
        if (p.type==Type::Hello) {
            if (retired(p.boot)) return {};
            if (p.boot==peer_ && haveSeq_ && !newer(p.seq,lastSeq_)) return {};
            if (pending_ && p.boot==pendingBoot_ && p.token==helloNonce_) {
                if (newer(p.seq,helloSeq_)) helloSeq_=p.seq;
            } else {
                if (pending_ && p.boot==pendingBoot_ && !newer(p.seq,helloSeq_)) return {};
                if (p.boot==peer_) active_=false; // new handshake fences old events immediately
                pending_=true; pendingBoot_=p.boot; helloNonce_=p.token; helloSeq_=p.seq;
                pendingToken_=next(nonce_); challengeAt_=receivedAt;
            }
            auto action=reply(Type::Challenge,pendingBoot_,pendingToken_,helloNonce_);
            return action;
        }
        if (p.type==Type::Ready && pending_ && p.boot==pendingBoot_ &&
            p.target==boot_ && p.token==pendingToken_ && newer(p.seq,helloSeq_)) {
            if (peer_ && peer_!=p.boot) retire(peer_);
            peer_=p.boot; token_=p.token; lastSeq_=p.seq; haveSeq_=true;
            fence_=p.event; flags_=p.flags; lastRx_=statusAt_=receivedAt;
            active_=true; pending_=false;
            return reply(Type::ReadyAck,peer_,token_,p.seq);
        }
        if (p.type!=Type::Ready && p.type!=Type::Status && p.type!=Type::Nod) return {};
        if (!linked(now) || p.boot!=peer_ || p.target!=boot_ || p.token!=token_) {
            // Echo their obsolete lease. Only its current owner will honor this reset.
            return reply(Type::Reset,p.boot,p.token,p.seq);
        }
        if (p.type==Type::Ready) return reply(Type::ReadyAck,peer_,token_,p.seq);
        if (p.type==Type::Nod && !newer(p.event,fence_)) {
            return reply(Type::NodAck,peer_,token_,p.event,Ack::Duplicate);
        }
        if (haveSeq_ && !newer(p.seq,lastSeq_)) return {};
        lastSeq_=p.seq; lastRx_=statusAt_=receivedAt; flags_=p.flags;
        if (p.type==Type::Status) return reply(Type::StatusAck,peer_,token_,p.seq);
        // Consume even a dropped/expired event: retries must never activate twice.
        fence_=p.event;
        Ack code=Ack::Dropped;
        if (p.age+elapsed(now,receivedAt)>NOD_TTL) code=Ack::Expired;
        else if (canForward && sensorReady(p.flags)) code=Ack::Forwarded;
        auto action=reply(Type::NodAck,peer_,token_,p.event,code);
        action.nod=(code==Ack::Forwarded);
        return action;
    }
 private:
    uint32_t boot_,nonce_,tx_=0,peer_=0,token_=0,lastSeq_=0,fence_=0;
    uint32_t lastRx_=0,statusAt_=0,pendingBoot_=0,pendingToken_=0;
    uint32_t helloNonce_=0,helloSeq_=0,challengeAt_=0;
    uint32_t retired_[4]={0,0,0,0}; unsigned retiredIndex_=0;
    bool active_=false,pending_=false,haveSeq_=false;
    uint8_t flags_=0;
    bool retired(uint32_t boot) const { for (auto old:retired_) if (old && old==boot) return true; return false; }
    void retire(uint32_t boot) { retired_[retiredIndex_++%4]=boot; }
    Action reply(Type type,uint32_t peer,uint32_t token,uint32_t event,Ack code=Ack::None) {
        Action a; a.reply=true; a.packet.type=type; a.packet.boot=boot_;
        a.packet.target=peer; a.packet.token=token; a.packet.seq=next(tx_);
        a.packet.event=event; a.packet.code=code; return a;
    }
};
}
