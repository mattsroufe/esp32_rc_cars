// Esc.h
#pragma once // Prevents double inclusion of this file

#include <ESP32Servo.h> // Include the Servo library to control the ESC

class Esc
{
public:
    // Constructor that takes the pin number for the ESC
    Esc(int pin = 13);

    // Method to initialize the ESC
    void initialize();

    // Method to control the ESC with a throttle value
    void control(int throttle);

private:
    int _pin;                                 // Pin for the ESC
    Servo _esc;                               // Servo object to control the ESC
    int smoothedMotorSpeed = 0;               // Variable for smoothing throttle input
    const float MOTOR_SMOOTHING_FACTOR = 0.6; // Smoothing factor for motor speed
    const int MOTOR_DEAD_ZONE = 5;            // Dead zone threshold
    const int MIN_SPEED_MS = 1000; // 1000;
    const int NEUTRAL_SPEED_MS = 1500; // 1500;
    const int MAX_SPEED_MS = 2000; // 2000;
};
