#include "ServoControl.h"
#include <Arduino.h>

ServoControl::ServoControl(int pin, int minAngle, int maxAngle, int deadzone)
    : _pin(pin)
    , _minAngle(minAngle)
    , _maxAngle(maxAngle)
    , _deadzone(deadzone)
{}

void ServoControl::initialize() {
    if (_initialized) return;

    _servo.attach(_pin);
    _servo.write(ServoConfig::CENTER);
    _currentAngle = ServoConfig::CENTER;
    _initialized = true;
}

void ServoControl::reset() {
    _currentAngle = ServoConfig::CENTER;
    if (_initialized) {
        _servo.write(ServoConfig::CENTER);
    }
}

void ServoControl::control(int position) {
    if (!_initialized) return;

    int angle = mapToServoRange(position);
    if (angle != _currentAngle) {
        _currentAngle = angle;
        _servo.write(angle);
    }
}

int ServoControl::mapToServoRange(int input) const {
    // Constrain input to valid range
    input = constrain(input, ServoConfig::DEFAULT_MIN_ANGLE, ServoConfig::DEFAULT_MAX_ANGLE);

    // Apply deadzone around center
    if (abs(input - ServoConfig::CENTER) < _deadzone) {
        return ServoConfig::CENTER;
    }

    // Map input to physical servo limits
    if (input < ServoConfig::CENTER) {
        return map(input,
                   ServoConfig::DEFAULT_MIN_ANGLE, ServoConfig::CENTER,
                   _minAngle, ServoConfig::CENTER);
    } else {
        return map(input,
                   ServoConfig::CENTER, ServoConfig::DEFAULT_MAX_ANGLE,
                   ServoConfig::CENTER, _maxAngle);
    }
}
