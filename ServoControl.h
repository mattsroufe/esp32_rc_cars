#ifndef SERVOCONTROL_H
#define SERVOCONTROL_H

#include <ESP32Servo.h>
#include "config.h"
#include "Controllable.h"

class ServoControl : public Controllable {
public:
    ServoControl(int pin = Pins::STEERING_SERVO,
                 int minAngle = ServoConfig::STEERING_MIN_ANGLE,
                 int maxAngle = ServoConfig::STEERING_MAX_ANGLE,
                 int deadzone = ServoConfig::STEERING_DEADZONE);

    // Controllable interface
    void initialize() override;
    void control(int position) override;
    void reset() override;
    bool isInitialized() const override { return _initialized; }

    // Getters
    int getCurrentAngle() const { return _currentAngle; }
    int getPin() const { return _pin; }

private:
    int mapToServoRange(int input) const;

    const int _pin;
    const int _minAngle;
    const int _maxAngle;
    const int _deadzone;

    Servo _servo;
    int _currentAngle = ServoConfig::CENTER;
    bool _initialized = false;
};

#endif // SERVOCONTROL_H
