#include "ServoControl.h"

// Constructor to initialize the servo with pin, min/max angles, and dead zone
ServoControl::ServoControl(int pin, int minAngle, int maxAngle, int deadZone)
{
    _pin = pin;
    _minAngle = minAngle;   // Minimum angle (left limit)
    _maxAngle = maxAngle;   // Maximum angle (right limit)
    _deadZone = deadZone;
}

// Initialize the servo by attaching it to the specified pin and setting the default position
void ServoControl::initialize()
{
    _servo.attach(_pin);      // Attach the servo to the specified pin
    _servo.write(_centerPos); // Set the servo to the center position (90 degrees)
}

// Map the input value (0 to 180) to the servo's range (left and right travel based on min/max angles)
int ServoControl::mapSteering(int input)
{
    int angle = constrain(input, 0, 180);  // Ensure the input is within 0 to 180

    // Apply dead zone to the input (ignore small values near neutral)
    if (abs(input - _centerPos) < _deadZone)
    {
        angle = _centerPos;  // Neutral position
    }

    if (input < _centerPos)
    { // Left steering (input < 90)
        // Map the input range (0-90) to the left angle range (_minAngle to _centerPos)
        angle = map(input, 0, _centerPos, _minAngle, _centerPos);
    }
    else
    { // Right steering (input >= 90)
        // Map the input range (90-180) to the right angle range (_centerPos to _maxAngle)
        angle = map(input, _centerPos, 180, _centerPos, _maxAngle);
    }

    return angle;
}

// Control the servo based on the position, applying dead zone
void ServoControl::control(int position)
{
    // Map the input position (0-180) to the appropriate servo angle
    int angle = mapSteering(position);

    // Write the calculated angle to the servo
    _servo.write(angle);
}
