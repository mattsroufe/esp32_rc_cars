#ifndef CONFIG_H
#define CONFIG_H

// Global constants for servo configuration
constexpr int SERVO_DEFAULT_MIN_ANGLE = 0;
constexpr int SERVO_DEFAULT_MAX_ANGLE = 180;
constexpr int SERVO_MIN_ANGLE = 30;
constexpr int SERVO_MAX_ANGLE = 130;
constexpr int SERVO_CENTER = 90;
constexpr int SERVO_DEADZONE = 5;

// Hardware pin definitions
constexpr int STEERING_SERVO_PIN = 12;

// You can add more reusable values here:
// - ESC min/max
// - pin assignments
// - command timeouts
// - camera config
// - etc.

#endif
