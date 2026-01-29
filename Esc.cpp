#include "Esc.h"
#include <Arduino.h>

Esc::Esc(int pin) : _pin(pin) {}

void Esc::initialize() {
    if (_initialized) return;

    _servo.attach(_pin);
    _servo.writeMicroseconds(EscConfig::NEUTRAL_PULSE_US);
    delay(Timing::ESC_INIT_DELAY_MS);
    _initialized = true;
}

void Esc::reset() {
    _smoothedSpeed = 0;
    if (_initialized) {
        _servo.writeMicroseconds(EscConfig::NEUTRAL_PULSE_US);
    }
}

void Esc::control(int throttle) {
    if (!_initialized) return;

    // Apply deadzone
    if (abs(throttle) < EscConfig::DEADZONE) {
        throttle = 0;
    }

    // Constrain input
    throttle = constrain(throttle, EscConfig::MIN_THROTTLE, EscConfig::MAX_THROTTLE);

    // Apply smoothing and convert to pulse width
    int smoothed = applySmoothing(throttle);
    int pulseWidth = throttleToPulse(smoothed);

    _servo.writeMicroseconds(pulseWidth);
}

int Esc::applySmoothing(int targetSpeed) {
    _smoothedSpeed = _smoothedSpeed +
        EscConfig::SMOOTHING_FACTOR * (targetSpeed - _smoothedSpeed);
    return _smoothedSpeed;
}

int Esc::throttleToPulse(int throttle) const {
    return map(throttle,
               EscConfig::MIN_THROTTLE, EscConfig::MAX_THROTTLE,
               EscConfig::MIN_PULSE_US, EscConfig::MAX_PULSE_US);
}
