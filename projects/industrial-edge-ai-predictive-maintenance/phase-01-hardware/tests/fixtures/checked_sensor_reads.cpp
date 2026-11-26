#include "../../firmware/include/checked_sensors.h"
#include <assert.h>
#include <stdio.h>
#include <vector>
#include <map>
#include <utility>

// Fake register bus. No Arduino, GPIO, serial or network access.
struct Registers {
  std::map<std::pair<int, int>, std::vector<uint8_t> > values;
  int calls = 0, fail = -1;
  bool resetCalibrationAfterCurrent = false;
  bool read(uint8_t address, uint8_t reg, uint8_t* out, size_t count) {
    ++calls;
    if (calls == fail) return false;
    const std::vector<uint8_t>& data = values[std::make_pair(address, reg)];
    if (data.size() != count) return false;
    for (size_t i=0; i<count; ++i) out[i] = data[i];
    if (resetCalibrationAfterCurrent && address == 0x40 && reg == 0x04)
      values[std::make_pair(0x40, 0x05)] = {0,0};
    return true;
  }
};

Registers validBus() {
  Registers bus;
  bus.values[{0x53,0x00}] = {0xe5};
  bus.values[{0x53,0x31}] = {0x0b};
  bus.values[{0x53,0x2d}] = {0x08};
  bus.values[{0x53,0x32}] = {0xfa,0, 0x06,0xff, 0,0}; // +250,-250,0
  bus.values[{0x40,0x00}] = {0x39,0x9f};
  bus.values[{0x40,0x05}] = {0x10,0};
  bus.values[{0x40,0x02}] = {0x19,0xca}; // 3.3V, conversion ready
  bus.values[{0x40,0x04}] = {0xff,0x06}; // -250 -> -25mA
  return bus;
}

struct WireFixture {
  int written=1, endStatus=0, returned=2, availableCount=2, readValue=0;
  int pointerWrites=0, stopCalls=0, reads=0;
  void beginTransmission(uint8_t) {}
  size_t write(uint8_t) { ++pointerWrites; return written; }
  uint8_t endTransmission(bool stop) { if(stop)++stopCalls; return endStatus; }
  size_t requestFrom(uint8_t,uint8_t,uint8_t) { return returned; }
  int available() { return availableCount; }
  int read() { ++reads; --availableCount; return readValue; }
};

int main() {
  float x=123,y=123,z=123,v=123,m=123;
  Registers bus=validBus();
  assert(edgeops::acceleration(bus,x,y,z));
  assert(fabs(x-9.80665f)<0.00001f && fabs(y+9.80665f)<0.00001f && z==0);
  assert(edgeops::currentVoltage(bus,v,m));
  assert(fabs(v-3.3f)<0.00001f && m==-25.0f);
  assert(edgeops::signedWord(0x8000)==-32768 && edgeops::signedWord(0x7fff)==32767);
  for(int failure=1; failure<=4; ++failure) {
    bus=validBus();bus.fail=failure;
    assert(!edgeops::acceleration(bus,x,y,z));assert(isnan(x)&&isnan(y)&&isnan(z));
  }
  for(int failure=1; failure<=5; ++failure) {
    bus=validBus();bus.fail=failure;
    assert(!edgeops::currentVoltage(bus,v,m));assert(isnan(v)&&isnan(m));
  }
  for(int reg : {0x00,0x31,0x2d}) {
    bus=validBus();bus.values[{0x53,reg}]={0};
    assert(!edgeops::acceleration(bus,x,y,z));
  }
  bus=validBus();bus.values[{0x53,0x32}]={0,0};
  assert(!edgeops::acceleration(bus,x,y,z));
  bus=validBus();bus.values[{0x40,0x00}]={0,0};
  assert(!edgeops::currentVoltage(bus,v,m));
  bus=validBus();bus.values[{0x40,0x05}]={0,0};
  assert(!edgeops::currentVoltage(bus,v,m));
  for(uint8_t flags : {uint8_t(0),uint8_t(3)}) {
    bus=validBus();bus.values[{0x40,0x02}]={0,flags};
    assert(!edgeops::currentVoltage(bus,v,m));
  }
  bus=validBus();bus.resetCalibrationAfterCurrent=true;
  assert(!edgeops::currentVoltage(bus,v,m));
  bus=validBus();bus.values[{0x40,0x02}]={0,2};bus.values[{0x40,0x04}]={0,0};
  assert(edgeops::currentVoltage(bus,v,m)&&v==0&&m==0);
  bus=validBus();bus.values.clear();
  assert(!edgeops::acceleration(bus,x,y,z));assert(!edgeops::currentVoltage(bus,v,m));
  // Losing one group does not overwrite the other group's usable values.
  bus=validBus();bus.values.erase({0x53,0x32});
  assert(!edgeops::acceleration(bus,x,y,z));assert(edgeops::currentVoltage(bus,v,m));

  uint8_t bytes[2]={99,99};
  WireFixture wire;edgeops::WireBus<WireFixture> adapter(wire);
  assert(adapter.read(0x40,2,bytes,2));assert(wire.reads==2&&wire.pointerWrites==1);
  wire=WireFixture();wire.written=0;
  assert(!adapter.read(0x40,2,bytes,2));assert(wire.stopCalls==1&&wire.reads==0);
  wire=WireFixture();wire.endStatus=2;
  assert(!adapter.read(0x40,2,bytes,2));assert(wire.reads==0);
  wire=WireFixture();wire.returned=1;wire.availableCount=1;
  assert(!adapter.read(0x40,2,bytes,2));assert(wire.availableCount==0);
  wire=WireFixture();wire.availableCount=1;
  assert(!adapter.read(0x40,2,bytes,2));
  wire=WireFixture();wire.readValue=-1;
  assert(!adapter.read(0x40,2,bytes,2));
  puts("checked sensor transfer/configuration/units fixtures passed; no hardware used");
}
