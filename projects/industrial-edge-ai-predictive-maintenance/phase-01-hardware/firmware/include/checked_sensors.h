#pragma once
#include <stdint.h>
#include <stddef.h>
#include <math.h>

// Read-only sampling for the existing default-address, default-INA219-preset
// sensor-only configuration. Transfer success does not prove calibration.
namespace edgeops {
template <class WireType>
struct WireBus {
  WireType& wire;
  explicit WireBus(WireType& value) : wire(value) {}
  bool read(uint8_t address, uint8_t reg, uint8_t* destination, size_t length) {
    wire.beginTransmission(address);
    if (wire.write(reg) != 1) { wire.endTransmission(true); return false; }
    if (wire.endTransmission(false) != 0) return false;
    const size_t received = wire.requestFrom(address, uint8_t(length), uint8_t(true));
    if (received != length || size_t(wire.available()) != length) {
      while (wire.available()) wire.read();
      return false;
    }
    for (size_t index = 0; index < length; ++index) {
      const int value = wire.read();
      if (value < 0) return false;
      destination[index] = uint8_t(value);
    }
    return true;
  }
};


inline int32_t signedWord(uint16_t value) {
  return value >= 0x8000 ? int32_t(value) - 65536 : int32_t(value);
}

template <class Bus>
bool word(Bus& bus, uint8_t address, uint8_t reg, uint16_t& value) {
  uint8_t data[2] = {};
  if (!bus.read(address, reg, data, sizeof(data))) return false;
  value = (uint16_t(data[0]) << 8) | uint16_t(data[1]);
  return true;
}

template <class Bus>
bool acceleration(Bus& bus, float& x, float& y, float& z) {
  x = y = z = NAN;
  uint8_t id = 0, format = 0, power = 0, data[6] = {};
  // Full resolution, right justified, +/-16 g; measurement mode without sleep.
  if (!bus.read(0x53, 0x00, &id, 1) || id != 0xe5 ||
      !bus.read(0x53, 0x31, &format, 1) || (format & 0x0f) != 0x0b ||
      !bus.read(0x53, 0x2d, &power, 1) || (power & 0x3f) != 0x08 ||
      !bus.read(0x53, 0x32, data, sizeof(data))) return false;
  const float scale = 0.004f * 9.80665f;  // Same nominal full-resolution SI scale.
  x = signedWord(uint16_t(data[0]) | (uint16_t(data[1]) << 8)) * scale;
  y = signedWord(uint16_t(data[2]) | (uint16_t(data[3]) << 8)) * scale;
  z = signedWord(uint16_t(data[4]) | (uint16_t(data[5]) << 8)) * scale;
  return isfinite(x) && isfinite(y) && isfinite(z);
}

template <class Bus>
bool currentVoltage(Bus& bus, float& volts, float& milliamps) {
  volts = milliamps = NAN;
  uint16_t config = 0, calibration = 0, voltage = 0, current = 0, after = 0;
  // Preserve the existing library's 32V/2A nominal preset, which assumes a
  // 0.1-ohm shunt. This is a software conversion preset, NOT a board rating.
  if (!word(bus, 0x40, 0x00, config) || config != 0x399f ||
      !word(bus, 0x40, 0x05, calibration) || calibration != 0x1000 ||
      !word(bus, 0x40, 0x02, voltage) || (voltage & 0x01) || !(voltage & 0x02) ||
      !word(bus, 0x40, 0x04, current) ||
      !word(bus, 0x40, 0x05, after) || after != calibration) return false;
  volts = float(voltage >> 3) * 0.004f;
  milliamps = float(signedWord(current)) * 0.1f;
  return isfinite(volts) && isfinite(milliamps);
}
}  // namespace edgeops
