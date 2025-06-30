#include "SteeringServo.h"
#include "config.h"

SteeringServo::SteeringServo(int pin, int minAngle, int maxAngle, int deadZone)
    : _pin(pin), _minAngle(minAngle), _maxAngle(maxAngle), _deadZone(deadZone)
{
    _servo.attach(_pin);
    _servo.write(_centerPos);
}

int SteeringServo::mapSteering(int input)
{
    int angle = constrain(input, SERVO_DEFAULT_MIN_ANGLE, SERVO_DEFAULT_MAX_ANGLE);

    if (abs(input - _centerPos) < _deadZone)
    {
        return _centerPos;
    }

    if (input < _centerPos)
    {
        angle = map(input, SERVO_DEFAULT_MIN_ANGLE, _centerPos, _minAngle, _centerPos);
    }
    else
    {
        angle = map(input, _centerPos, SERVO_DEFAULT_MAX_ANGLE, _centerPos, _maxAngle);
    }

    return angle;
}

void SteeringServo::control(int position)
{
    int angle = mapSteering(position);
    _servo.write(angle);
}
