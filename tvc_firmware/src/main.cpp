#include <Arduino.h>
#include <Wire.h>

namespace {
constexpr uint8_t kMpuAddress = 0x68;  // MPU6050 default I2C address

bool writeRegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(kMpuAddress);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool readRegisters(uint8_t startReg, uint8_t count, uint8_t *buffer) {
  Wire.beginTransmission(kMpuAddress);
  Wire.write(startReg);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  uint8_t received = Wire.requestFrom(kMpuAddress, count);
  if (received != count) {
    return false;
  }

  for (uint8_t i = 0; i < count; ++i) {
    buffer[i] = Wire.read();
  }
  return true;
}

int16_t toInt16(uint8_t high, uint8_t low) {
  return static_cast<int16_t>((high << 8) | low);
}

bool readImuSample(float &ax_g, float &ay_g, float &az_g,
                   float &gx_dps, float &gy_dps, float &gz_dps, float &temp_c) {
  uint8_t raw[14];
  if (!readRegisters(0x3B, sizeof(raw), raw)) {
    return false;
  }

  const int16_t accelX = toInt16(raw[0], raw[1]);
  const int16_t accelY = toInt16(raw[2], raw[3]);
  const int16_t accelZ = toInt16(raw[4], raw[5]);
  const int16_t tempRaw = toInt16(raw[6], raw[7]);
  const int16_t gyroX = toInt16(raw[8], raw[9]);
  const int16_t gyroY = toInt16(raw[10], raw[11]);
  const int16_t gyroZ = toInt16(raw[12], raw[13]);

  constexpr float accelScale = 16384.0f; // FS_SEL=0 -> +/-2g
  constexpr float gyroScale = 131.0f;    // FS_SEL=0 -> +/-250 dps

  ax_g = accelX / accelScale;
  ay_g = accelY / accelScale;
  az_g = accelZ / accelScale;
  gx_dps = gyroX / gyroScale;
  gy_dps = gyroY / gyroScale;
  gz_dps = gyroZ / gyroScale;
  temp_c = (tempRaw / 340.0f) + 36.53f;

  return true;
}

bool initImu() {
  if (!writeRegister(0x6B, 0x00)) { // Wake up device, use internal clock
    return false;
  }
  delay(100);

  if (!writeRegister(0x1C, 0x00)) { // +/- 2g full scale
    return false;
  }
  if (!writeRegister(0x1B, 0x00)) { // +/- 250 deg/s full scale
    return false;
  }

  return true;
}
}

void setup() {
  Serial.begin(115200);
  while (!Serial) {
    delay(10);
  }
  Serial.println("TVC IMU demo - initializing...");

  Wire.begin();
  Wire.setClock(400000);

  if (initImu()) {
    Serial.println("[OK] MPU6050 ready");
  } else {
    Serial.println("[ERROR] Failed to initialize MPU6050. Check wiring.");
  }
}

void emit_json_line(uint32_t t_ms,
                    float ax_g, float ay_g, float az_g,
                    float gx_dps, float gy_dps, float gz_dps,
                    float temp_c) {
  Serial.print("{\"t_ms\":");  Serial.print(t_ms);
  Serial.print(",\"accel\":{\"x\":"); Serial.print(ax_g, 4);
  Serial.print(",\"y\":");             Serial.print(ay_g, 4);
  Serial.print(",\"z\":");             Serial.print(az_g, 4);
  Serial.print("},\"gyro\":{\"x\":");  Serial.print(gx_dps, 3);
  Serial.print(",\"y\":");             Serial.print(gy_dps, 3);
  Serial.print(",\"z\":");             Serial.print(gz_dps, 3);
  Serial.print("},\"temp\":");         Serial.print(temp_c, 2);
  Serial.println("}");
}

void loop() {
  float ax, ay, az, gx, gy, gz, temp;
  if (readImuSample(ax, ay, az, gx, gy, gz, temp)) {
    const uint32_t t = millis();
    emit_json_line(t, ax, ay, az, gx, gy, gz, temp);
  }
  delay(10); // ~100 Hz
}
