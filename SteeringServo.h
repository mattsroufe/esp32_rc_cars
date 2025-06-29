#ifndef STEERINGSERVO_H
#define STEERINGSERVO_H

#include <ESP32Servo.h>

class SteeringServo {
public:
    SteeringServo(int pin, int minAngle, int maxAngle, int deadZone);

    void control(int position);

private:
    int _pin;
    int _minAngle;
    int _maxAngle;
    int _deadZone;
    const int _centerPos = 90;

    Servo _servo;

    int mapSteering(int input);
};

#endif
