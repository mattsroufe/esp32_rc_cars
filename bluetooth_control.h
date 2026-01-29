#ifndef BLUETOOTH_CONTROL_H
#define BLUETOOTH_CONTROL_H

#include <Bluepad32.h>
#include "soc/rtc_cntl_reg.h"
#include "config.h"
#include "ServoControl.h"
#include "Esc.h"

// =============================================================================
// Global Objects
// =============================================================================
namespace {
    ServoControl steeringServo(Pins::STEERING_SERVO);
    Esc esc(Pins::ESC);
    ControllerPtr connectedController = nullptr;
}

// =============================================================================
// Controller Callbacks
// =============================================================================
void onControllerConnected(ControllerPtr ctl) {
    if (connectedController != nullptr) {
        Serial.println("Controller: Already connected, rejecting new controller");
        ctl->disconnect();
        return;
    }

    Serial.println("Controller: Connected");
    ControllerProperties props = ctl->getProperties();
    Serial.printf("  Model: %s, VID=0x%04x, PID=0x%04x\n",
                  ctl->getModelName().c_str(),
                  props.vendor_id,
                  props.product_id);

    connectedController = ctl;
}

void onControllerDisconnected(ControllerPtr ctl) {
    if (connectedController == ctl) {
        Serial.println("Controller: Disconnected");
        connectedController = nullptr;

        // Safety: reset controls when controller disconnects
        esc.reset();
        steeringServo.reset();
    }
}

// =============================================================================
// Control Processing
// =============================================================================
void processGamepadInput(ControllerPtr ctl) {
    // Map left stick Y axis to throttle (-255 to 255)
    int throttle = map(ctl->axisY(), -511, 511, EscConfig::MIN_THROTTLE, EscConfig::MAX_THROTTLE);
    esc.control(-throttle);  // Invert for correct direction

    // Map right stick X axis to steering (0 to 180)
    int steeringPos = map(ctl->axisRX(), -511, 511,
                          ServoConfig::DEFAULT_MIN_ANGLE, ServoConfig::DEFAULT_MAX_ANGLE);
    steeringServo.control(steeringPos);
}

void updateController() {
    if (connectedController &&
        connectedController->isConnected() &&
        connectedController->hasData()) {

        if (connectedController->isGamepad()) {
            processGamepadInput(connectedController);
        } else {
            Serial.println("Controller: Unsupported type");
        }
    }
}

// =============================================================================
// Main Functions
// =============================================================================
void setup() {
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);
    Serial.begin(115200);

    Serial.printf("Bluepad32 Firmware: %s\n", BP32.firmwareVersion());

    const uint8_t* addr = BP32.localBdAddress();
    Serial.printf("Bluetooth Address: %02X:%02X:%02X:%02X:%02X:%02X\n",
                  addr[0], addr[1], addr[2], addr[3], addr[4], addr[5]);

    BP32.setup(&onControllerConnected, &onControllerDisconnected);
    BP32.forgetBluetoothKeys();

    esc.initialize();
    steeringServo.initialize();

    Serial.println("Setup: Complete");
}

void loop() {
    if (BP32.update()) {
        updateController();
    }
    delay(Timing::LOOP_DELAY_MS);
}

#endif // BLUETOOTH_CONTROL_H
