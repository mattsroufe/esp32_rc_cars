const ws = new WebSocket('ws://localhost:8080/ws');
const GAMEPAD_POLLING_INTERVAL = 30; // ms for polling gamepad status
let clients = []

ws.onmessage = function (event) {
  clients = JSON.parse(event.data)
  // Handle incoming WebSocket messages if needed
};

function sendMessage() {
  ws.send(message);
}

ws.onclose = function () {
  // Handle WebSocket closure
};

const gamepads = {};

// Configuration object for joystick ranges
const controllerConfig = {
  "default": {
    rightJoystickRange: { min: -1, max: 1 } // Default range: -1 to 1
  },
  "057e-2009-Pro Controller": { // Replace with actual gamepad.id of your special controller
    rightJoystickRange: { min: -1.0, max: 0.0 } // Special range: -1.0 to 0.0
  }
};

// Send gamepad data to the server
function updateGamepadInfo() {
  const connectedGamepads = navigator.getGamepads();

  // Collect the status of each connected gamepad
  const gamepadData = connectedGamepads.map((gamepad) => {
    if (!gamepad) return;

    let gamepadAxes = [
      -gamepad.axes[1].toFixed(1),  // Left joystick axis Y
      gamepad.axes[2].toFixed(1)   // Right joystick axis X
    ];

    // Check for special configuration based on gamepad.id
    const controllerId = gamepad.id;
    const config = controllerConfig[controllerId] || controllerConfig["default"]; // Default config if no special config

    // Remap the right joystick axis based on the controller's config
    if (config.rightJoystickRange) {
      gamepadAxes[1] = transformAxisToStandardRange(gamepad.axes[2], config.rightJoystickRange.min, config.rightJoystickRange.max, -1, 1).toFixed(1);
    }

    gamepadButtons = gamepad.buttons.map(button => +button.pressed);

    requestAnimationFrame(() => {
      // Get the gamepad info container
      const gamepadInfoContainer = document.getElementById(`gamepad-info-${gamepad.index}`);

      // Selectively update the text content of specific child elements
      const axesContainer = gamepadInfoContainer.querySelector(".axes");
      const buttonsContainer = gamepadInfoContainer.querySelector(".buttons");

      // Only update what's changed
      axesContainer.textContent = gamepadAxes.join(", ");
      buttonsContainer.textContent = gamepadButtons.join(", ");
    });

    // Map the axes values to desired ranges
    const result = [
      Math.round(-255 + (gamepadAxes[0] - -1) * (255 - -255) / (1 - -1)),
      Math.round(0 + (gamepadAxes[1] - -1) * (180 - 0) / (1 - -1))
    ];

    return result;
  });

  // Send the gamepad data to the server if WebSocket is open
  if (ws && ws.readyState === WebSocket.OPEN) {
    json = {}
    clients.forEach((ip, i) => json[ip] = gamepadData[i])
    ws.send(JSON.stringify(json));
  }
}

// Transform axis from a custom range to the standard -1 to 1 range
function transformAxisToStandardRange(value, min, max, newMin, newMax) {
  if (min === -1 && max === 1) {
    return value;  // No transformation needed for normal range
  }

  // Adjust the value before applying the transformation for special controllers
  return ((value - min) * (newMax - newMin)) / (max - min) + newMin;
}

// Poll for gamepad status every 30ms
function pollGamepads() {
  setInterval(updateGamepadInfo, GAMEPAD_POLLING_INTERVAL);
}

// Start polling when gamepads are connected
window.addEventListener("gamepadconnected", (event) => {
  const gamepad = event.gamepad;
  gamepads[gamepad.index] = gamepad;
  console.log("Gamepad connected:", gamepad.id);
});

// Handle gamepad disconnection
window.addEventListener("gamepaddisconnected", (event) => {
  const gamepad = event.gamepad;
  delete gamepads[gamepad.index];
  console.log("Gamepad disconnected:", gamepad.id);
});

// Start the polling loop
pollGamepads();

