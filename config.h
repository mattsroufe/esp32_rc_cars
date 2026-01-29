#ifndef CONFIG_H
#define CONFIG_H

#include <cstdint>

// =============================================================================
// Servo Configuration
// =============================================================================
namespace ServoConfig {
    constexpr int DEFAULT_MIN_ANGLE = 0;
    constexpr int DEFAULT_MAX_ANGLE = 180;
    constexpr int CENTER = 90;

    // Steering-specific limits (physical constraints)
    constexpr int STEERING_MIN_ANGLE = 30;
    constexpr int STEERING_MAX_ANGLE = 130;
    constexpr int STEERING_DEADZONE = 5;
}

// =============================================================================
// ESC (Electronic Speed Controller) Configuration
// =============================================================================
namespace EscConfig {
    constexpr int MIN_PULSE_US = 1000;
    constexpr int NEUTRAL_PULSE_US = 1500;
    constexpr int MAX_PULSE_US = 2000;
    constexpr float SMOOTHING_FACTOR = 0.6f;
    constexpr int DEADZONE = 5;
    constexpr int MIN_THROTTLE = -255;
    constexpr int MAX_THROTTLE = 255;
}

// =============================================================================
// Hardware Pin Assignments
// =============================================================================
namespace Pins {
    constexpr int STEERING_SERVO = 12;
    constexpr int ESC = 13;
    constexpr int DUMMY = -1;  // For PWM channel reservation
}

// =============================================================================
// Timing Configuration
// =============================================================================
namespace Timing {
    constexpr unsigned long COMMAND_TIMEOUT_MS = 20;
    constexpr unsigned long ESC_INIT_DELAY_MS = 1000;
    constexpr unsigned long LOOP_DELAY_MS = 30;
}

// =============================================================================
// Backward Compatibility Aliases (deprecated - use namespaced versions)
// =============================================================================
constexpr int SERVO_DEFAULT_MIN_ANGLE = ServoConfig::DEFAULT_MIN_ANGLE;
constexpr int SERVO_DEFAULT_MAX_ANGLE = ServoConfig::DEFAULT_MAX_ANGLE;
constexpr int SERVO_MIN_ANGLE = ServoConfig::STEERING_MIN_ANGLE;
constexpr int SERVO_MAX_ANGLE = ServoConfig::STEERING_MAX_ANGLE;
constexpr int SERVO_CENTER = ServoConfig::CENTER;
constexpr int SERVO_DEADZONE = ServoConfig::STEERING_DEADZONE;
constexpr int STEERING_SERVO_PIN = Pins::STEERING_SERVO;

#endif // CONFIG_H
