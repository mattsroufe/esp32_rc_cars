#ifndef SERVOCONTROL_H
#define SERVOCONTROL_H

#include <Servo.h>

class ServoControl
{
public:
    // Constructor to initialize the servo with pin, offsets, and dead zone
    ServoControl(int pin, int leftOffset = 25, int rightOffset = 50, int deadZone = 5);

    // Initialize the servo (attach and set to center position)
    void initialize();

    // Control the servo position based on the input, applying dead zone and steering offsets
    void control(int position);

private:
    int _pin;             // Pin where the servo is connected
    Servo _servo;         // Servo object
    int _centerPos = 90;  // Default center position of the servo (can be adjusted)
    int _leftOffset = 0;  // Left steering offset
    int _rightOffset = 0; // Right steering offset
    int _deadZone = 0;    // Dead zone for servo control
    int _minAngle = 0;    // Min angle (0 degrees)
    int _maxAngle = 180;  // Max angle (180 degrees)

    // Helper method to map input values to a specific steering angle
    int mapSteering(int input);
};

#endif
