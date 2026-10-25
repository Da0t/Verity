#include <VerityLink.h>
#include <cassert>
#include <cstring>
#include <iostream>
using namespace Verity;
constexpr uint8_t still=SensorOk|Calibrated|Settled;
// Gesture traces at 100 Hz; every completed double is appended as one decimal digit.
static unsigned fired=0;
static void hold(GestureDetector& d,uint32_t& t,float pitch,float yaw,uint32_t ms) {
  for(uint32_t end=t+ms;t<end;t+=10) if(uint8_t g=d.update(pitch,yaw,t)) fired=fired*10+g;
}
static void move(GestureDetector& d,uint32_t& t,float pitch,float yaw) { hold(d,t,pitch,yaw,250); hold(d,t,0,0,150); }
struct Fixture {
  SenderLink sender{11,100}; CameraLink camera{22,200}; uint32_t now=100;
  Packet take(uint8_t flags=still) { Packet p; assert(sender.poll(now,flags,p)); assert(valid(p)); return p; }
  Action deliver(const Packet& p,bool forward=true) { return camera.receive(p,now,now,forward); }
  void handshake() {
    Packet hello=take(); assert(hello.type==Type::Hello);
    auto challenge=deliver(hello); assert(challenge.reply);
    sender.receive(challenge.packet,now,now);
    Packet ready=take(); assert(ready.type==Type::Ready);
    auto ack=deliver(ready); assert(ack.reply);
    sender.receive(ack.packet,now,now); assert(sender.active()); assert(camera.settled(now));
  }
};
int main() {
  const uint8_t peer[]={2,1,2,3,4,5}, other[]={2,1,2,3,4,6};
  assert(matchesPeer(peer,peer)); assert(!matchesPeer(peer,other)); assert(!matchesPeer(peer,nullptr));
  // Known byte layout, strict parsing and malformed payloads.
  Packet p; p.boot=0x12345678; p.token=9;p.seq=1;
  uint8_t bytes[PACKET_SIZE]; assert(encode(p,bytes,sizeof(bytes)));
  assert(bytes[0]=='V' && bytes[2]==2 && bytes[4]==0x78 && bytes[7]==0x12);
  Packet out; assert(decode(bytes,sizeof(bytes),out)); assert(out.boot==p.boot);
  for(size_t size=0;size<PACKET_SIZE;++size) assert(!decode(bytes,size,out));
  assert(!decode(nullptr,PACKET_SIZE,out)); assert(!encode(p,nullptr,PACKET_SIZE));
  for(int offset: {0,1,2,3,26,27,28}) { auto old=bytes[offset]; bytes[offset]=255; assert(!decode(bytes,PACKET_SIZE,out)); bytes[offset]=old; }
  assert(!motionValid(Settled)); assert(!motionValid(128));
  assert(newer(1,0xffffffffu)); assert(!newer(5,5)); assert(!newer(4,5));
  assert(elapsed(4,0xfffffffeu)==6);
  // Only Nod packets carry a gesture, and only a known one.
  { Packet q=p; q.gesture=DoubleNod; assert(!valid(q)); }
  // The gesture kind survives sender -> wire -> camera.
  { Fixture f; f.handshake(); assert(f.sender.nod(f.now,still,DoubleRight)); auto nod=f.take();
    assert(nod.gesture==DoubleRight); uint8_t wire[PACKET_SIZE]; Packet back;
    assert(encode(nod,wire,PACKET_SIZE) && decode(wire,PACKET_SIZE,back) && back.gesture==DoubleRight);
    for(uint8_t bad: {uint8_t(NoGesture),uint8_t(4)}) { back.gesture=bad; assert(!valid(back)); }
    assert(f.deliver(nod).nod);
  }
  // Double gestures: singles, mixed pairs and slow pairs do nothing; a third repeat is swallowed.
  { GestureDetector d; uint32_t t=0; hold(d,t,0,0,1000);
    move(d,t,25,0); hold(d,t,0,0,2000); assert(fired==0);
    move(d,t,25,0); move(d,t,25,0); hold(d,t,0,0,2000); assert(fired==DoubleNod);
    fired=0; move(d,t,0,35); move(d,t,0,35); hold(d,t,0,0,2000); assert(fired==DoubleLeft);
    fired=0; move(d,t,0,-35); move(d,t,0,-35); hold(d,t,0,0,2000); assert(fired==DoubleRight);
    fired=0; move(d,t,0,35); move(d,t,0,-35); hold(d,t,0,0,2000); assert(fired==0);
    move(d,t,25,0); hold(d,t,0,0,1600); move(d,t,25,0); hold(d,t,0,0,2000); assert(fired==0);
    move(d,t,0,35); move(d,t,25,0); move(d,t,0,35); hold(d,t,0,0,2000); assert(fired==DoubleLeft); // stray nod mid-pair
    fired=0;
    move(d,t,25,0); move(d,t,25,0); move(d,t,25,0); hold(d,t,0,0,2000); assert(fired==DoubleNod);
    fired=0; move(d,t,10,10); move(d,t,10,10); hold(d,t,0,0,2000); assert(fired==0); // too small
  }
  // No gestures queued before a fresh handshake.
  { Fixture f; assert(!f.sender.nod(f.now,still)); f.handshake(); auto status=f.take(); assert(status.type==Type::Status); }
  // Application ACK loss causes a retry, never a second activation.
  { Fixture f; f.handshake(); assert(f.sender.nod(f.now,still)); auto nod=f.take();
    auto a=f.deliver(nod); assert(a.nod && a.packet.code==Ack::Forwarded);
    f.now+=150; auto retry=f.take(); assert(retry.event==nod.event && newer(retry.seq,nod.seq));
    a=f.deliver(retry); assert(!a.nod && a.packet.code==Ack::Duplicate);
    f.sender.receive(a.packet,f.now,f.now); assert(!f.sender.pendingNod());
    assert(f.sender.acknowledged()==1);
  }
  // A dropped event is consumed, even if a subscriber appears before its retry.
  { Fixture f; f.handshake(); f.sender.nod(f.now,still); auto nod=f.take();
    auto a=f.deliver(nod,false); assert(!a.nod && a.packet.code==Ack::Dropped);
    ++nod.seq; a=f.deliver(nod,true); assert(!a.nod && a.packet.code==Ack::Duplicate);
  }
  // Bounded retries and local deadline; no endless gesture loop.
  { Fixture f; f.handshake(); f.sender.nod(f.now,still); unsigned nods=0;
    for(unsigned i=0;i<8;++i) { Packet q; if(f.sender.poll(f.now,still,q) && q.type==Type::Nod) ++nods; f.now+=150; }
    assert(nods==MAX_ATTEMPTS); assert(!f.sender.pendingNod()); assert(f.sender.dropped()==1);
  }
  // Queued packets and event age cannot make old gestures current.
  { Fixture f; f.handshake(); f.sender.nod(f.now,still); auto nod=f.take();
    assert(!f.camera.receive(nod,f.now,f.now+QUEUE_TTL+1,true).reply);
    nod.age=NOD_TTL; auto a=f.camera.receive(nod,f.now,f.now+1,true);
    assert(!a.nod && a.packet.code==Ack::Expired);
  }
  // Invalid/reordered traffic never refreshes freshness.
  { Fixture f; f.handshake(); auto status=f.take(); auto a=f.deliver(status);
    f.sender.receive(a.packet,f.now,f.now); assert(f.camera.settled(f.now));
    assert(!f.camera.receive(status,f.now+1000,f.now+1000,true).reply);
    assert(!f.camera.settled(f.now+STATUS_TTL));
  }
  // Motion unknown or uncalibrated is never settled.
  { Fixture f; f.handshake(); auto status=f.take(0); f.deliver(status);
    assert(!f.camera.settled(f.now)); }
  // BLE reconnect invalidates the old lease: old nod is reset, not replayed.
  { Fixture f; f.handshake(); f.sender.nod(f.now,still); auto nod=f.take();
    f.camera.invalidate(); auto a=f.deliver(nod); assert(!a.nod && a.packet.type==Type::Reset);
    f.sender.receive(a.packet,f.now,f.now); assert(!f.sender.pendingNod()); f.handshake();
    assert(!f.deliver(nod).nod);
  }
  // Camera restart rejects the old token; handshake fences pending gestures.
  { Fixture f; f.handshake(); f.sender.nod(f.now,still); auto nod=f.take();
    CameraLink rebooted(33,300); auto a=rebooted.receive(nod,f.now,f.now,true);
    assert(!a.nod && a.packet.type==Type::Reset); f.sender.receive(a.packet,f.now,f.now);
    assert(!f.sender.active() && !f.sender.pendingNod());
  }
  // A restarted sensor establishes a fresh boot; delayed retired traffic is ignored.
  { Fixture f; f.handshake(); auto old=f.take(); SenderLink rebooted(44,400); Packet hello,ready;
    assert(rebooted.poll(f.now,still,hello)); auto a=f.deliver(hello);
    rebooted.receive(a.packet,f.now,f.now); assert(rebooted.poll(f.now,still,ready));
    a=f.deliver(ready); rebooted.receive(a.packet,f.now,f.now); assert(rebooted.active());
    assert(!f.deliver(old).nod); old.type=Type::Hello; old.target=0;
    assert(!f.deliver(old).reply);
  }
  // Late ACK cannot revive an expired lease, nor can a foreign challenge bind it.
  { Fixture f; f.handshake(); auto status=f.take(); auto a=f.deliver(status);
    f.sender.receive(a.packet,f.now+STATUS_TTL,f.now+STATUS_TTL); assert(!f.sender.active());
  }
  { Fixture f; auto hello=f.take(); auto a=f.deliver(hello); ++a.packet.event;
    f.sender.receive(a.packet,f.now,f.now); assert(f.sender.stage()==SenderLink::Stage::Hello);
  }
  // READY ACK loss is recovered by READY retry without a second session reset.
  { Fixture f; auto hello=f.take(); auto a=f.deliver(hello); f.sender.receive(a.packet,f.now,f.now);
    auto ready=f.take(); f.deliver(ready); f.now+=150; ready=f.take(); a=f.deliver(ready);
    f.sender.receive(a.packet,f.now,f.now); assert(f.sender.active()); }
  // Time rollover leaves normal handshakes, nods and status expiration functional.
  { Fixture f; f.now=0xfffffff0u; f.handshake(); f.sender.nod(f.now,still); auto nod=f.take();
    f.now+=150; auto a=f.deliver(nod); assert(a.nod); assert(!f.camera.settled(f.now+STATUS_TTL)); }
  std::cout << "ESP-NOW protocol and lifecycle assertions passed\n";
}
