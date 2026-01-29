#ifndef CONTROLLABLE_H
#define CONTROLLABLE_H

// Interface for controllable hardware components
class Controllable {
public:
    virtual ~Controllable() = default;

    // Initialize the hardware (attach pins, set initial state)
    virtual void initialize() = 0;

    // Control the component with a value
    virtual void control(int value) = 0;

    // Reset to safe/neutral state
    virtual void reset() = 0;

    // Check if initialized
    virtual bool isInitialized() const = 0;
};

#endif // CONTROLLABLE_H
