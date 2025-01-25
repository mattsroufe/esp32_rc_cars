#include <Arduino.h>
#include <Bluepad32.h>
#include "soc/rtc_cntl_reg.h" //disable brownout problems
#include "Esc.h"              // Include the Esc class header file
#include "ServoControl.h"     // Include the ServoControl class header

// Motor and servo pins
#define DUMMY_PIN -1 // Pin for servo control
#define SERVO_PIN 12 // Pin for servo control
#define ESC_PIN 13   // Pin for motor control

// Define dead zone threshold (adjust as needed)
const int MOTOR_DEAD_ZONE = 5; // Threshold for motor to ignore small values
const int SERVO_DEAD_ZONE = 5; // Threshold for servo to ignore small values

// range for ackerman steering to align properly
const int MIN_SERVO_ANGLE = 65;
const int MAX_SERVO_ANGLE = 140;

ServoControl steeringServo(SERVO_PIN, MIN_SERVO_ANGLE, MAX_SERVO_ANGLE, SERVO_DEAD_ZONE);
Esc esc(ESC_PIN);

// Time tracking variables
unsigned long lastCommandTime = 0;
const int COMMAND_TIMEOUT = 20; // command timeout ms

void setup()
{
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

  Serial.begin(115200);
  Serial.setDebugOutput(true);

  // Now, disable the SD card to free up pins
  SD.end();
  Serial.println("SD Card disabled. Pins freed!");

  steeringServo.initialize();
  esc.initialize();
}

void loop()
{
  if (millis() - COMMAND_TIMEOUT >= lastCommandTime)
  {
    esc.control(0); // Start motor at 0 speed
    steeringServo.control(90);
    // Serial.println("Throttle reset to 0 due to timeout.");
  }

  if (client.available())
  {
    camera_fb_t *fb = esp_camera_fb_get();

    if (!fb)
      return;

    client.sendBinary((const char *)fb->buf, fb->len);

    esp_camera_fb_return(fb);

    client.poll();
  }
}
