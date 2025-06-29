#include "SteeringServo.h"

SteeringServo::SteeringServo(int pin, int minAngle, int maxAngle, int deadZone)
    : _pin(pin), _minAngle(minAngle), _maxAngle(maxAngle), _deadZone(deadZone) {
    _servo.attach(_pin);
    _servo.write(_centerPos);
}

int SteeringServo::mapSteering(int input) {
    int angle = constrain(input, 0, 180);

    if (abs(input - _centerPos) < _deadZone) {
        return _centerPos;
    }

    if (input < _centerPos) {
        angle = map(input, 0, _centerPos, _minAngle, _centerPos);
    } else {
        angle = map(input, _centerPos, 180, _centerPos, _maxAngle);
    }

    return angle;
}

void SteeringServo::control(int position) {
    int angle = mapSteering(position);
    _servo.write(angle);
}
