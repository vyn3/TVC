#include <Arduino.h>
#include <Wire.h>

// ================== CONFIG ==================
constexpr uint32_t BAUD = 115200;          // console USB + UART2
constexpr uint8_t  kMpuAddress = 0x68;     // AD0 -> GND = 0x68
// Garde Wire.begin() par défaut: ESP32 => SDA=21, SCL=22

// Activer en 1 si tu veux aussi envoyer vers la Pi sur UART2 (GPIO17 TX2 -> RX Pi, GPIO16 RX2 <- TX Pi)
#define USE_UART2 1

#if USE_UART2
  #include <HardwareSerial.h>
  HardwareSerial SerialPi(2);               // UART2
  constexpr int RX2_PIN = 16;               // RX2 (depuis TX Pi)
  constexpr int TX2_PIN = 17;               // TX2 (vers RX Pi)
#endif
// ============================================

// ---- Low-level I2C helpers (tes fonctions inchangées) ----
namespace {
bool writeRegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(kMpuAddress);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool readRegisters(uint8_t startReg, uint8_t count, uint8_t *buffer) {
  Wire.beginTransmission(kMpuAddress);
  Wire.write(startReg);
  if (Wire.endTransmission(false) != 0) {   // repeated start
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
  const int16_t gyroX  = toInt16(raw[8],  raw[9]);
  const int16_t gyroY  = toInt16(raw[10], raw[11]);
  const int16_t gyroZ  = toInt16(raw[12], raw[13]);

  constexpr float accelScale = 16384.0f; // FS_SEL=0 -> +/-2g
  constexpr float gyroScale  = 131.0f;   // FS_SEL=0 -> +/-250 dps

  ax_g   = accelX / accelScale;
  ay_g   = accelY / accelScale;
  az_g   = accelZ / accelScale;
  gx_dps = gyroX  / gyroScale;
  gy_dps = gyroY  / gyroScale;
  gz_dps = gyroZ  / gyroScale;
  temp_c = (tempRaw / 340.0f) + 36.53f;

  return true;
}

bool initImu() {
  if (!writeRegister(0x6B, 0x00)) { // PWR_MGMT_1: wake + internal clock
    return false;
  }
  delay(100);
  if (!writeRegister(0x1C, 0x00)) { // ACCEL_CONFIG: ±2g
    return false;
  }
  if (!writeRegister(0x1B, 0x00)) { // GYRO_CONFIG: ±250 dps
    return false;
  }
  return true;
}
} // namespace

// ---- JSON emitter ----
static inline void emit_json_line(Stream &out,
                                  uint32_t t_ms,
                                  float ax_g, float ay_g, float az_g,
                                  float gx_dps, float gy_dps, float gz_dps,
                                  float temp_c) {
  // NDJSON compact: 1 échantillon = 1 ligne terminée par '\n'
  out.print("{\"t_ms\":");  out.print(t_ms);
  out.print(",\"accel\":{\"x\":"); out.print(ax_g, 4);
  out.print(",\"y\":");             out.print(ay_g, 4);
  out.print(",\"z\":");             out.print(az_g, 4);
  out.print("},\"gyro\":{\"x\":");  out.print(gx_dps, 3);
  out.print(",\"y\":");             out.print(gy_dps, 3);
  out.print(",\"z\":");             out.print(gz_dps, 3);
  out.print("},\"temp\":");         out.print(temp_c, 2);
  out.println("}");
}

void setup() {
  Serial.begin(BAUD);
  unsigned long t0 = millis();
  while (!Serial && (millis() - t0) < 1500) { delay(10); }

#if USE_UART2
  SerialPi.begin(BAUD, SERIAL_8N1, RX2_PIN, TX2_PIN);
#endif

  // I2C: garde ce qui marche chez toi
  Wire.begin();             // par défaut ESP32 = SDA 21, SCL 22
  Wire.setClock(400000);    // tu as validé 400 kHz; repasse à 100 kHz si instable
  delay(20);

  if (initImu()) {
    Serial.println("{\"status\":\"mpu_ready\",\"addr\":\"0x68\"}");
#if USE_UART2
    SerialPi.println("{\"status\":\"mpu_ready\",\"addr\":\"0x68\"}");
#endif
  } else {
    Serial.println("{\"error\":\"mpu_init_failed\"}");
#if USE_UART2
    SerialPi.println("{\"error\":\"mpu_init_failed\"}");
#endif
    // on continue quand même pour debug éventuel
  }
}

void loop() {
  float ax, ay, az, gx, gy, gz, tc;
  if (readImuSample(ax, ay, az, gx, gy, gz, tc)) {
    const uint32_t t = millis();
    // USB pour VSCode
    emit_json_line(Serial, t, ax, ay, az, gx, gy, gz, tc);
#if USE_UART2
    // Option: envoyer la même ligne vers la Pi
    emit_json_line(SerialPi, t, ax, ay, az, gx, gy, gz, tc);
#endif
  } else {
    // message très parcimonieux pour ne pas flooder
    static uint32_t lastWarn = 0;
    if (millis() - lastWarn > 1000) {
      Serial.println("{\"warn\":\"imu_read_failed\"}");
#if USE_UART2
      SerialPi.println("{\"warn\":\"imu_read_failed\"}");
#endif
      lastWarn = millis();
    }
  }
  delay(10); // ~100 Hz
}
