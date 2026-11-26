#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_ADXL345_U.h>
#include <Adafruit_INA219.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>
#include <math.h>
#include "checked_sensors.h"

constexpr uint8_t SDA_PIN = 21;
constexpr uint8_t SCL_PIN = 22;
constexpr uint8_t TEMP_PIN = 4;
constexpr uint32_t REPORT_INTERVAL_MS = 1000;
constexpr const char* DEVICE_ID = "motor-001";

Adafruit_ADXL345_Unified accelerometer(12345);
Adafruit_INA219 currentMonitor;
OneWire oneWire(TEMP_PIN);
DallasTemperature temperatureProbe(&oneWire);

bool accelPresent = false;
bool currentPresent = false;
uint32_t seq = 0;
uint32_t lastReport = 0;

edgeops::WireBus<TwoWire> checkedWire(Wire);

void setup() {
  Serial.begin(115200);
  delay(1200);
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);
  Wire.setTimeOut(50);
  accelPresent = accelerometer.begin();
  if (accelPresent) accelerometer.setRange(ADXL345_RANGE_16_G);
  currentPresent = currentMonitor.begin();
  temperatureProbe.begin();
  temperatureProbe.setResolution(10);
  temperatureProbe.setWaitForConversion(true);
  // Diagnostic lines are prefixed # so the capture script can skip them.
  Serial.printf("# boot accel=%d ina219=%d ds18b20_count=%d\n",
                accelPresent, currentPresent, temperatureProbe.getDeviceCount());
  lastReport = millis();
}

void loop() {
  const uint32_t now = millis();
  if ((uint32_t)(now - lastReport) < REPORT_INTERVAL_MS) return;
  lastReport += REPORT_INTERVAL_MS;

  float ax = NAN, ay = NAN, az = NAN;
  bool accelValid = false;
  if (accelPresent) {
    accelValid = edgeops::acceleration(checkedWire, ax, ay, az);
  }

  temperatureProbe.requestTemperatures();
  const float temp = temperatureProbe.getTempCByIndex(0);
  const bool tempValid = temp > -55.0f && temp < 125.0f &&
                         temp != DEVICE_DISCONNECTED_C && isfinite(temp);

  float voltage = NAN, current = NAN;
  bool currentValid = false;
  if (currentPresent) {
    currentValid = edgeops::currentVoltage(checkedWire, voltage, current);
  }

  JsonDocument doc;
  doc["schema_version"] = 1;
  doc["device_id"] = DEVICE_ID;
  doc["seq"] = ++seq;
  doc["uptime_ms"] = now;
  doc["ax_mps2"] = accelValid ? ax : 0.0f;
  doc["ay_mps2"] = accelValid ? ay : 0.0f;
  doc["az_mps2"] = accelValid ? az : 0.0f;
  doc["temp_c"] = tempValid ? temp : 0.0f;
  doc["bus_v"] = currentValid ? voltage : 0.0f;
  doc["current_ma"] = currentValid ? current : 0.0f;
  doc["adxl345_valid"] = accelValid;
  doc["ds18b20_valid"] = tempValid;
  doc["ina219_valid"] = currentValid;
  doc["valid"] = accelValid && tempValid && currentValid;
  serializeJson(doc, Serial);
  Serial.println();
}
