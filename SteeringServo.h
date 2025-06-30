#ifndef STEERINGSERVO_H
#define STEERINGSERVO_H

#include <ESP32Servo.h>
#include "config.h"

class SteeringServo
{
public:
    SteeringServo(int pin,
                  int minAngle = SERVO_MIN_ANGLE,
                  int maxAngle = SERVO_MAX_ANGLE,
                  int deadZone = SERVO_DEADZONE);

    void control(int position);

private:
    int _pin;
    int _minAngle;
    int _maxAngle;
    int _deadZone;
    static constexpr int _centerPos = SERVO_CENTER;

    Servo _servo;

    int mapSteering(int input);
};

#endif
