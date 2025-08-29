#include <Bluepad32.h>
#include "soc/rtc_cntl_reg.h" // Prevent brownout
#include "config.h"
#include "SteeringServo.h"
#include "Esc.h"

// Create steering and ESC objects
SteeringServo steeringServo(STEERING_SERVO_PIN);
Esc esc;

ControllerPtr myController = nullptr;

void onConnectedController(ControllerPtr ctl)
{
  if (myController != nullptr)
  {
    Serial.println("CALLBACK: A controller is already connected. Rejecting new controller.");
    ctl->disconnect(); // Reject extra controller
    return;
  }

  Serial.println("CALLBACK: Controller connected.");
  ControllerProperties properties = ctl->getProperties();
  Serial.printf("Controller model: %s, VID=0x%04x, PID=0x%04x\n",
                ctl->getModelName().c_str(),
                properties.vendor_id,
                properties.product_id);

  myController = ctl;
}

void onDisconnectedController(ControllerPtr ctl)
{
  if (myController == ctl)
  {
    Serial.println("CALLBACK: Controller disconnected.");
    myController = nullptr;
  }
}

void controlMotor(ControllerPtr ctl)
{
  int throttle = map(ctl->axisY(), -511, 511, -255, 255);
  esc.control(-throttle);
}

void controlServo(ControllerPtr ctl)
{
  int servoPos = map(ctl->axisRX(), -511, 511, 0, 180);
  steeringServo.control(servoPos);
}

void processGamepad(ControllerPtr ctl)
{
  controlMotor(ctl);
  controlServo(ctl);
}

void processController()
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

void setup()
{
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);
  Serial.begin(115200);

  Serial.printf("Firmware: %s\n", BP32.firmwareVersion());
  const uint8_t *addr = BP32.localBdAddress();
  Serial.printf("BD Addr: %2X:%2X:%2X:%2X:%2X:%2X\n",
                addr[0], addr[1], addr[2], addr[3], addr[4], addr[5]);

  BP32.setup(&onConnectedController, &onDisconnectedController);
  BP32.forgetBluetoothKeys();

  esc.initialize(); // Still required if ESC needs pin setup
}

void loop()
{
  bool dataUpdated = BP32.update();
  if (dataUpdated)
  {
    processController();
  }

  delay(30);
}
