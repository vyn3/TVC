#include <Arduino.h>
#include <Wire.h>

void setup(){
  Serial.begin(115200);
  Wire.begin(21,22,100000); // SDA=21, SCL=22
  delay(200);
  Serial.println("I2C scan...");
  for (uint8_t addr = 1; addr < 127; addr++){
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0){
      Serial.printf("Found I2C device at 0x%02X\n", addr);
    }
  }
  Serial.println("Scan done.");
}
void loop(){ delay(1000); }
