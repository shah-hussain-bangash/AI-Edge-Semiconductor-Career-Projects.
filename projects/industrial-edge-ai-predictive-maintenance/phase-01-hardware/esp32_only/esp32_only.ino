// ESP32 Dev Module / classic ESP32 communication test only.
// All sensor flags are false; numeric placeholders are NOT measurements.
// No sensor libraries, Wi-Fi, MQTT, motor pins or equipment commands.
#include <Arduino.h>

uint32_t sequenceNumber = 0;
uint32_t lastReport = 0;

void setup() {
  Serial.begin(115200);
  delay(1200);
  Serial.println("# EDGEOPS ESP32-only TEST: all sensors unavailable");
  lastReport = millis();
}

void loop() {
  const uint32_t now = millis();
  if ((uint32_t)(now - lastReport) < 1000) return;
  lastReport = now;
  Serial.printf(
    "{\"schema_version\":1,\"device_id\":\"motor-001\",\"seq\":%lu,\"uptime_ms\":%lu,"
    "\"ax_mps2\":0,\"ay_mps2\":0,\"az_mps2\":0,\"temp_c\":0,\"bus_v\":0,\"current_ma\":0,"
    "\"adxl345_valid\":false,\"ds18b20_valid\":false,\"ina219_valid\":false,\"valid\":false}\n",
    (unsigned long)++sequenceNumber, (unsigned long)now);
}
