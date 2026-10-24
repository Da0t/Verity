#pragma once
#include "Protocol.h"

namespace Verity {
class SenderLink {
 public:
    enum class Stage { Backoff, Hello, Ready, Active };
    explicit SenderLink(uint32_t boot,uint32_t nonceSeed=1):boot_(boot),helloNonce_(nonceSeed) {}
    Stage stage() const { return stage_; }
    bool active() const { return stage_==Stage::Active; }
    bool pendingNod() const { return pending_; }
    uint32_t dropped() const { return dropped_; }
    uint32_t acknowledged() const { return acknowledged_; }
    // Always advance the event counter, including gestures while disconnected.
    bool nod(uint32_t now, uint8_t flags) {
        const uint32_t id=next(event_);
        if (!active() || !sensorReady(flags) || pending_) { ++dropped_; return false; }
        pending_=true; pendingId_=id; nodAt_=now; nodAttempts_=0; return true;
    }
    void receive(const Packet& p,uint32_t receivedAt,uint32_t now) {
        if (active() && elapsed(now,lastCamera_)>=STATUS_TTL) resync(now,false);
        if (!valid(p) || elapsed(now,receivedAt)>QUEUE_TTL || p.target!=boot_) return;
        if (p.type==Type::Reset && active() && p.token==token_) { resync(now,false); return; }
        if (p.type==Type::Challenge && stage_==Stage::Hello && p.event==helloNonce_) {
            camera_=p.boot; token_=p.token; cameraSeq_=p.seq;
            stage_=Stage::Ready; attempts_=0; fence_=event_; return;
        }
        if (p.boot!=camera_ || p.token!=token_ || !newer(p.seq,cameraSeq_)) return;
        if (p.type==Type::ReadyAck && stage_==Stage::Ready && p.event==readySeq_) {
            cameraSeq_=p.seq; stage_=Stage::Active; lastCamera_=receivedAt;
            lastStatus_=now-STATUS_INTERVAL; return;
        }
        if (!active()) return;
        if (p.type==Type::StatusAck && p.event==statusSeq_) {
            cameraSeq_=p.seq; lastCamera_=receivedAt;
        } else if (p.type==Type::NodAck && pending_ && p.event==pendingId_) {
            cameraSeq_=p.seq; lastCamera_=receivedAt; pending_=false;
            if (p.code==Ack::Forwarded || p.code==Ack::Duplicate) ++acknowledged_;
            else ++dropped_;
        }
    }
    bool poll(uint32_t now,uint8_t flags,Packet& out) {
        if (active() && elapsed(now,lastCamera_)>=STATUS_TTL) resync(now,false);
        if (pending_ && elapsed(now,nodAt_)>NOD_TTL) { pending_=false; ++dropped_; }
        if (stage_==Stage::Backoff) {
            if (started_ && elapsed(now,backoffAt_)<SYNC_BACKOFF) return false;
            stage_=Stage::Hello; next(helloNonce_); attempts_=0; started_=true;
        }
        if (stage_==Stage::Hello || stage_==Stage::Ready) {
            if (attempts_ && elapsed(now,lastAttempt_)<RETRY_INTERVAL) return false;
            if (attempts_>=MAX_ATTEMPTS) { resync(now,true); return false; }
            ++attempts_; lastAttempt_=now;
            out=packet(stage_==Stage::Hello ? Type::Hello : Type::Ready,flags);
            if (stage_==Stage::Hello) { out.target=0; out.token=helloNonce_; out.event=event_; }
            else { out.event=fence_; readySeq_=out.seq; }
            return true;
        }
        if (pending_ && (!nodAttempts_ || elapsed(now,lastNodAttempt_)>=RETRY_INTERVAL)) {
            if (nodAttempts_>=MAX_ATTEMPTS) { pending_=false; ++dropped_; }
            else {
                ++nodAttempts_; lastNodAttempt_=now;
                out=packet(Type::Nod,flags); out.event=pendingId_;
                out.age=static_cast<uint16_t>(elapsed(now,nodAt_)); return true;
            }
        }
        if (elapsed(now,lastStatus_)>=STATUS_INTERVAL ||
            (flags!=lastFlags_ && elapsed(now,lastStatus_)>=100)) {
            lastStatus_=now; lastFlags_=flags;
            out=packet(Type::Status,flags); out.event=event_; statusSeq_=out.seq; return true;
        }
        return false;
    }
 private:
    Stage stage_=Stage::Backoff;
    uint32_t boot_,helloNonce_,tx_=0,event_=0,camera_=0,token_=0,cameraSeq_=0;
    uint32_t fence_=0,readySeq_=0,statusSeq_=0,lastCamera_=0,lastStatus_=0;
    uint32_t lastAttempt_=0,backoffAt_=0,pendingId_=0,nodAt_=0,lastNodAttempt_=0;
    uint32_t dropped_=0,acknowledged_=0;
    unsigned attempts_=0,nodAttempts_=0;
    bool pending_=false,started_=false;
    uint8_t lastFlags_=0;
    Packet packet(Type type,uint8_t flags) {
        Packet p; p.type=type; p.boot=boot_; p.target=camera_; p.token=token_;
        p.seq=next(tx_); p.flags=flags; return p;
    }
    void resync(uint32_t now,bool backoff) {
        if (pending_) { pending_=false; ++dropped_; }
        stage_=Stage::Backoff; backoffAt_=backoff ? now : now-SYNC_BACKOFF;
        camera_=token_=0;
    }
};
}
