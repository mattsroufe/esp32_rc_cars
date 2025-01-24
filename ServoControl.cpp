#include "ServoControl.h"

// Constructor to initialize the servo with pin, offsets, and dead zone
ServoControl::ServoControl(int pin, int leftOffset, int rightOffset, int deadZone)
{
    _pin = pin;
    _leftOffset = leftOffset;
    _rightOffset = rightOffset;
    _deadZone = deadZone;
}

// Initialize the servo by attaching it to the specified pin and setting the default position
void ServoControl::initialize()
{
    _servo.attach(_pin);      // Attach the servo to the specified pin
    _servo.write(_centerPos); // Set the servo to the center position (90 degrees)
}

// Map the input value to a servo angle with different outer limits for left and right
int ServoControl::mapSteering(int input)
{
    // Ensure the input is within the valid range for the servo
    int angle = constrain(input, _minAngle, _maxAngle);

    // Apply left or right offsets based on the input value
    if (input < _centerPos)
    { // Left steering (input < 90)
        angle = map(input, _minAngle, _centerPos, _leftOffset, _centerPos);
    }
    else
    { // Right steering (input >= 90)
        angle = map(input, _centerPos, _maxAngle, _centerPos, _maxAngle - _rightOffset);
    }

    return angle;
}

// Control the servo based on the position, applying dead zone
void ServoControl::control(int position)
{
    // Apply dead zone to the servo position (ignore small values near neutral)
    if (abs(position - _centerPos) < _deadZone)
    {
        position = _centerPos; // Ignore small values near the center (neutral position)
    }

    // Map the input position to the appropriate angle
    int angle = mapSteering(position);

    // Write the calculated angle to the servo
    _servo.write(angle);
}
