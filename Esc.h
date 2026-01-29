#ifndef ESC_H
#define ESC_H

#include <ESP32Servo.h>
#include "config.h"
#include "Controllable.h"

class Esc : public Controllable {
public:
    explicit Esc(int pin = Pins::ESC);

    // Controllable interface
    void initialize() override;
    void control(int throttle) override;
    void reset() override;
    bool isInitialized() const override { return _initialized; }

    // Getters for current state
    int getCurrentSpeed() const { return _smoothedSpeed; }
    int getPin() const { return _pin; }

private:
    int throttleToPulse(int throttle) const;
    int applySmoothing(int targetSpeed);

    const int _pin;
    Servo _servo;
    int _smoothedSpeed = 0;
    bool _initialized = false;
};

#endif // ESC_H
