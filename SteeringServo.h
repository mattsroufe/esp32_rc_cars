#ifndef STEERINGSERVO_H
#define STEERINGSERVO_H

// SteeringServo is now an alias for ServoControl with steering-specific defaults.
// This file is kept for backward compatibility.
// New code should use ServoControl directly.

#include "ServoControl.h"

using SteeringServo = ServoControl;

#endif // STEERINGSERVO_H
