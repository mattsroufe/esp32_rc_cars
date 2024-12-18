#include <Bluepad32.h>
#include <ESP32Servo.h>  // ESP32Servo library for servo control

// Motor and Servo setup
const int motorPin1 = 12;  // Motor control pin 1
const int motorPin2 = 13;  // Motor control pin 2
const int servoPin = 14;   // Servo control pin


// Define dead zone threshold (adjust as needed)
const int MOTOR_DEAD_ZONE = 10;  // Threshold for motor to ignore small values
const int SERVO_DEAD_ZONE = 10;  // Threshold for servo to ignore small values

// Smoothing factor (higher values make the smoothing slower)
const float MOTOR_SMOOTHING_FACTOR = 0.4;  // Smoothing factor for motor
const float SERVO_SMOOTHING_FACTOR = 0.6;  // Smoothing factor for servo

// Variables to store smoothed values
int smoothedMotorSpeed = 0;
int smoothedServoPos = 90;
int motorSpeed = 0;        // Motor speed (controlled by left joystick Y-axis)
int lastMotorSpeed = 0;    // To store last motor speed for smoothing
int lastServoPos = 90;     // To store last servo position for smoothing
int motorSpeedSmoothFactor = 5; // The factor to control smoothing speed
int servoPosSmoothFactor = 5;  // The factor to control servo smoothing speed

int deadZone = 50;  // Configurable dead zone for joystick input

const int RIGHT_STEERING_OFFSET = 50;
const int LEFT_STEERING_OFFSET = 20;

// Create an instance of the ESP32Servo class
Servo myServo;

ControllerPtr myControllers[BP32_MAX_GAMEPADS];

// This callback gets called any time a new gamepad is connected.
// Up to 4 gamepads can be connected at the same time.
void onConnectedController(ControllerPtr ctl) {
    bool foundEmptySlot = false;
    for (int i = 0; i < BP32_MAX_GAMEPADS; i++) {
        if (myControllers[i] == nullptr) {
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
    if (!foundEmptySlot) {
        Serial.println("CALLBACK: Controller connected, but could not found empty slot");
    }
}

void onDisconnectedController(ControllerPtr ctl) {
    bool foundController = false;

    for (int i = 0; i < BP32_MAX_GAMEPADS; i++) {
        if (myControllers[i] == ctl) {
            Serial.printf("CALLBACK: Controller disconnected from index=%d\n", i);
            myControllers[i] = nullptr;
            foundController = true;
            break;
        }
    }

    if (!foundController) {
        Serial.println("CALLBACK: Controller disconnected, but not found in myControllers");
    }
}

void dumpGamepad(ControllerPtr ctl) {
    Serial.printf(
        "idx=%d, dpad: 0x%02x, buttons: 0x%04x, axis L: %4d, %4d, axis R: %4d, %4d, brake: %4d, throttle: %4d, "
        "misc: 0x%02x, gyro x:%6d y:%6d z:%6d, accel x:%6d y:%6d z:%6d\n",
        ctl->index(),        // Controller Index
        ctl->dpad(),         // D-pad
        ctl->buttons(),      // bitmask of pressed buttons
        ctl->axisX(),        // (-511 - 512) left X Axis
        ctl->axisY(),        // (-511 - 512) left Y axis
        ctl->axisRX(),       // (-511 - 512) right X axis
        ctl->axisRY(),       // (-511 - 512) right Y axis
        ctl->brake(),        // (0 - 1023): brake button
        ctl->throttle(),     // (0 - 1023): throttle (AKA gas) button
        ctl->miscButtons(),  // bitmask of pressed "misc" buttons
        ctl->gyroX(),        // Gyro X
        ctl->gyroY(),        // Gyro Y
        ctl->gyroZ(),        // Gyro Z
        ctl->accelX(),       // Accelerometer X
        ctl->accelY(),       // Accelerometer Y
        ctl->accelZ()        // Accelerometer Z
    );
}

// Function to control the motor based on the left joystick Y-axis
void controlMotor(ControllerPtr ctl) {
    // Map the joystick Y-axis to a motor speed range (0 to 255 for forward)
    int throttle = map(ctl->axisY(), -511, 511, -255, 255);

    // Apply dead zone to the throttle value
    if (abs(throttle) < MOTOR_DEAD_ZONE) {
        throttle = 0;  // Ignore small values within dead zone
    }

    // Smooth the motor speed
    smoothedMotorSpeed = smoothedMotorSpeed + MOTOR_SMOOTHING_FACTOR * (throttle - smoothedMotorSpeed);

    Serial.print(" - Throttle: ");
    Serial.println(smoothedMotorSpeed);

    // Motor control using two pins for direction
    if (smoothedMotorSpeed > 0) {
        // Forward direction
        analogWrite(motorPin1, smoothedMotorSpeed);
        analogWrite(motorPin2, 0);
    } else if (smoothedMotorSpeed < 0) {
        // Reverse direction
        analogWrite(motorPin1, 0);
        analogWrite(motorPin2, -smoothedMotorSpeed);
    } else {
        // Stop motor
        analogWrite(motorPin1, 0);
        analogWrite(motorPin2, 0);
    }
}

// Function to control the servo based on the joystick X-axis
void controlServo(ControllerPtr ctl) {
    // Map joystick X-axis to servo range (0-180)
    int servoPos = map(ctl->axisRX(), -511, 511, 0, 180);

    // Apply dead zone to the servo position (ignore small values near neutral)
    if (abs(servoPos - 90) < SERVO_DEAD_ZONE) {
        servoPos = 90;  // Ignore small values near the center (neutral position)
    }

    // Smooth the servo position
    smoothedServoPos = smoothedServoPos + SERVO_SMOOTHING_FACTOR * (servoPos - smoothedServoPos);

    // Ensure the servo position converges to 90 when near it
    if (abs(smoothedServoPos - 90) < 5) {
        smoothedServoPos = 90;  // Force it to return exactly to 90 if close enough
    }

    Serial.print(" - Servo position: ");
    Serial.println(smoothedServoPos);

    // Write the smoothed position to the servo
    myServo.write(constrain(smoothedServoPos, 0 + LEFT_STEERING_OFFSET, 180 - RIGHT_STEERING_OFFSET));  // Constrain within car's steering range
}

void processGamepad(ControllerPtr ctl) {
    // There are different ways to query whether a button is pressed.
    // By query each button individually:
    //  a(), b(), x(), y(), l1(), etc...
    if (ctl->a()) {
        static int colorIdx = 0;
        // Some gamepads like DS4 and DualSense support changing the color LED.
        // It is possible to change it by calling:
        switch (colorIdx % 3) {
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

    if (ctl->b()) {
        // Turn on the 4 LED. Each bit represents one LED.
        static int led = 0;
        led++;
        // Some gamepads like the DS3, DualSense, Nintendo Wii, Nintendo Switch
        // support changing the "Player LEDs": those 4 LEDs that usually indicate
        // the "gamepad seat".
        // It is possible to change them by calling:
        ctl->setPlayerLEDs(led & 0x0f);
    }

    if (ctl->x()) {
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

    controlMotor(ctl);  // Control motor based on left joystick Y
    controlServo(ctl);  // Control servo based on left joystick X
}

void processControllers() {
    for (auto myController : myControllers) {
        if (myController && myController->isConnected() && myController->hasData()) {
            if (myController->isGamepad()) {
                processGamepad(myController);
            } else {
                Serial.println("Unsupported controller");
            }
        }
    }
}

// Arduino setup function. Runs in CPU 1
void setup() {
    Serial.begin(115200);
    Serial.printf("Firmware: %s\n", BP32.firmwareVersion());
    const uint8_t* addr = BP32.localBdAddress();
    Serial.printf("BD Addr: %2X:%2X:%2X:%2X:%2X:%2X\n", addr[0], addr[1], addr[2], addr[3], addr[4], addr[5]);

    // Setup the Bluepad32 callbacks
    BP32.setup(&onConnectedController, &onDisconnectedController);

    // "forgetBluetoothKeys()" should be called when the user performs
    // a "device factory reset", or similar.
    // Calling "forgetBluetoothKeys" in setup() just as an example.
    // Forgetting Bluetooth keys prevents "paired" gamepads to reconnect.
    // But it might also fix some connection / re-connection issues.
    BP32.forgetBluetoothKeys();

    // Enables mouse / touchpad support for gamepads that support them.
    // When enabled, controllers like DualSense and DualShock4 generate two connected devices:
    // - First one: the gamepad
    // - Second one, which is a "virtual device", is a mouse.
    // By default, it is disabled.
    BP32.enableVirtualDevice(false);

    // Initialize motor pins
    pinMode(motorPin1, OUTPUT);
    pinMode(motorPin2, OUTPUT);
    
    // Initialize the servo
    myServo.attach(servoPin);  // Attach servo to pin
}

// Arduino loop function. Runs in CPU 1.
void loop() {
    // This call fetches all the controllers' data.
    // Call this function in your main loop.
    bool dataUpdated = BP32.update();
    if (dataUpdated)
        processControllers();

    // The main loop must have some kind of "yield to lower priority task" event.
    // Otherwise, the watchdog will get triggered.
    // If your main loop doesn't have one, just add a simple `vTaskDelay(1)`.
    // Detailed info here:
    // https://stackoverflow.com/questions/66278271/task-watchdog-got-triggered-the-tasks-did-not-reset-the-watchdog-in-time

    //     vTaskDelay(1);
    delay(50);
}
