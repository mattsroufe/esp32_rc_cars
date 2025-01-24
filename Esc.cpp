// Esc.cpp
#include "Esc.h" // Include the header file

// Constructor that initializes the ESC with a given pin
Esc::Esc(int pin)
{
    _pin = pin;
    _esc.attach(_pin); // Attach the ESC to the specified pin
}

// Method to initialize the ESC (sets it to 0 speed initially)
void Esc::initialize()
{
    _esc.writeMicroseconds(1500); // Start motor at 0 speed
    delay(1000);                  // Wait for ESC initialization
}

// Method to control the ESC based on the throttle input
void Esc::control(int throttle)
{
    if (abs(throttle) < MOTOR_DEAD_ZONE)
    {
        throttle = 0; // Ignore small values within dead zone
    }

    // Smooth the throttle value
    smoothedMotorSpeed = smoothedMotorSpeed + MOTOR_SMOOTHING_FACTOR * (throttle - smoothedMotorSpeed);

    // Map the smoothed throttle value from -255 to 255 into a PWM signal range (1000 to 2000 microseconds)
    int pwmValue = map(smoothedMotorSpeed, -255, 255, MIN_SPEED_MS, MAX_SPEED_MS);

    // Set the PWM signal to the ESC
    _esc.writeMicroseconds(pwmValue);

    // Optionally, print the PWM value for debugging
    // Serial.print(" - PWM Value: ");
    // Serial.println(pwmValue);
}
