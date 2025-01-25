#ifndef SERVOCONTROL_H
#define SERVOCONTROL_H

#include <Servo.h>

class ServoControl
{
public:
    // Constructor to initialize the servo with pin, min/max angle, and dead zone
    ServoControl(int pin, int minAngle = 0, int maxAngle = 180, int deadZone = 0);

    // Initialize the servo
    void initialize();

    // Control the servo based on the input position
    void control(int position);

private:
    int _pin;            // Pin to which the servo is connected
    int _minAngle = 0;   // Minimum angle for the servo (left limit)
    int _maxAngle = 180; // Maximum angle for the servo (right limit)
    int _deadZone = 0;   // Dead zone for the servo control

    Servo _servo;              // Servo object to control the physical servo
    const int _centerPos = 90; // Center position (90 degrees)

    // Map the input value (0-180) to the servo angle range with proper limits
    int mapSteering(int input);
};

#endif
