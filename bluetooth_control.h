#include <Bluepad32.h>
#include "soc/rtc_cntl_reg.h" // brownout config
#include "ServoControl.h"
#include "Esc.h"

ServoControl steeringServo;
Esc esc;
ControllerPtr myControllers[BP32_MAX_GAMEPADS];

// This callback gets called any time a new gamepad is connected.
// Up to 4 gamepads can be connected at the same time.
void onConnectedController(ControllerPtr ctl)
{
  bool foundEmptySlot = false;
  for (int i = 0; i < BP32_MAX_GAMEPADS; i++)
  {
    if (myControllers[i] == nullptr)
    {
      Serial.printf("CALLBACK: Controller is connected, index=%d\n", i);
      // Additionally, you can get certain gamepad properties like:
      // Model, VID, PID, BTAddr, flags, etc.
      ControllerProperties properties = ctl->getProperties();
      Serial.printf("Controller model: %s, VID=0x%04x, PID=0x%04x\n", ctl->getModelName().c_str(), properties.vendor_id,
                    properties.product_id);
      myControllers[i] = ctl;
      foundEmptySlot = true;
      break;
    }
  }
  if (!foundEmptySlot)
  {
    Serial.println("CALLBACK: Controller connected, but could not found empty slot");
  }
}

void onDisconnectedController(ControllerPtr ctl)
{
  bool foundController = false;

  for (int i = 0; i < BP32_MAX_GAMEPADS; i++)
  {
    if (myControllers[i] == ctl)
    {
      Serial.printf("CALLBACK: Controller disconnected from index=%d\n", i);
      myControllers[i] = nullptr;
      foundController = true;
      break;
    }
  }

  if (!foundController)
  {
    Serial.println("CALLBACK: Controller disconnected, but not found in myControllers");
  }
}

void dumpGamepad(ControllerPtr ctl)
{
  Serial.printf(
      "idx=%d, dpad: 0x%02x, buttons: 0x%04x, axis L: %4d, %4d, axis R: %4d, %4d, brake: %4d, throttle: %4d, "
      "misc: 0x%02x, gyro x:%6d y:%6d z:%6d, accel x:%6d y:%6d z:%6d\n",
      ctl->index(),       // Controller Index
      ctl->dpad(),        // D-pad
      ctl->buttons(),     // bitmask of pressed buttons
      ctl->axisX(),       // (-511 - 512) left X Axis
      ctl->axisY(),       // (-511 - 512) left Y axis
      ctl->axisRX(),      // (-511 - 512) right X axis
      ctl->axisRY(),      // (-511 - 512) right Y axis
      ctl->brake(),       // (0 - 1023): brake button
      ctl->throttle(),    // (0 - 1023): throttle (AKA gas) button
      ctl->miscButtons(), // bitmask of pressed "misc" buttons
      ctl->gyroX(),       // Gyro X
      ctl->gyroY(),       // Gyro Y
      ctl->gyroZ(),       // Gyro Z
      ctl->accelX(),      // Accelerometer X
      ctl->accelY(),      // Accelerometer Y
      ctl->accelZ()       // Accelerometer Z
  );
}

// Function to control the motor based on the left joystick Y-axis
void controlMotor(ControllerPtr ctl)
{
  // Map the joystick Y-axis to a motor speed range (0 to 255 for forward)
  int throttle = map(ctl->axisY(), -511, 511, -255, 255);
  esc.control(-throttle);
}

// Function to control the servo based on the joystick X-axis
void controlServo(ControllerPtr ctl)
{
  // Map joystick X-axis to servo range (0-180)
  int servoPos = map(ctl->axisRX(), -511, 511, 0, 180);
  steeringServo.control(servoPos);
}

void processGamepad(ControllerPtr ctl)
{
  // There are different ways to query whether a button is pressed.
  // By query each button individually:
  //  a(), b(), x(), y(), l1(), etc...
  if (ctl->a())
  {
    static int colorIdx = 0;
    // Some gamepads like DS4 and DualSense support changing the color LED.
    // It is possible to change it by calling:
    switch (colorIdx % 3)
    {
    case 0:
      // Red
      ctl->setColorLED(255, 0, 0);
      break;
    case 1:
      // Green
      ctl->setColorLED(0, 255, 0);
      break;
    case 2:
      // Blue
      ctl->setColorLED(0, 0, 255);
      break;
    }
    colorIdx++;
  }

  if (ctl->b())
  {
    // Turn on the 4 LED. Each bit represents one LED.
    static int led = 0;
    led++;
    // Some gamepads like the DS3, DualSense, Nintendo Wii, Nintendo Switch
    // support changing the "Player LEDs": those 4 LEDs that usually indicate
    // the "gamepad seat".
    // It is possible to change them by calling:
    ctl->setPlayerLEDs(led & 0x0f);
  }

  if (ctl->x())
  {
    // Some gamepads like DS3, DS4, DualSense, Switch, Xbox One S, Stadia support rumble.
    // It is possible to set it by calling:
    // Some controllers have two motors: "strong motor", "weak motor".
    // It is possible to control them independently.
    ctl->playDualRumble(0 /* delayedStartMs */, 250 /* durationMs */, 0x80 /* weakMagnitude */,
                        0x40 /* strongMagnitude */);
  }

  // Another way to query controller data is by getting the buttons() function.
  // See how the different "dump*" functions dump the Controller info.
  // dumpGamepad(ctl);

  controlMotor(ctl); // Control motor based on left joystick Y
  controlServo(ctl); // Control servo based on left joystick X
}

void processControllers()
{
  for (auto myController : myControllers)
  {
    if (myController && myController->isConnected() && myController->hasData())
    {
      if (myController->isGamepad())
      {
        processGamepad(myController);
      }
      else
      {
        Serial.println("Unsupported controller");
      }
    }
  }
}

// Arduino setup function. Runs in CPU 1
void setup()
{
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

  Serial.begin(115200);
  Serial.printf("Firmware: %s\n", BP32.firmwareVersion());
  const uint8_t *addr = BP32.localBdAddress();
  Serial.printf("BD Addr: %2X:%2X:%2X:%2X:%2X:%2X\n", addr[0], addr[1], addr[2], addr[3], addr[4], addr[5]);

  BP32.setup(&onConnectedController, &onDisconnectedController);
  BP32.forgetBluetoothKeys();

  steeringServo.initialize();
  esc.initialize();
}

void loop()
{
  bool dataUpdated = BP32.update();
  if (dataUpdated)
    processControllers();

  delay(30);
}
