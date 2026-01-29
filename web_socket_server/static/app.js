/**
 * ESP32 RC Cars - Browser Control Interface
 * Handles gamepad input and WebSocket communication with the server.
 */

// =============================================================================
// Configuration
// =============================================================================
const CONFIG = {
  GAMEPAD_POLLING_INTERVAL: 30,  // ms
  WS_RECONNECT_DELAY: 2000,      // ms
  WS_MAX_RECONNECT_ATTEMPTS: 10,
  THROTTLE_MIN: -255,
  THROTTLE_MAX: 255,
  STEERING_MIN: 0,
  STEERING_MAX: 180,
};

// Controller-specific axis configurations
const CONTROLLER_CONFIGS = {
  "default": {
    rightJoystickRange: { min: -1, max: 1 }
  },
  "057e-2009-Pro Controller": {
    rightJoystickRange: { min: -1.0, max: 0.0 }
  }
};

// =============================================================================
// State
// =============================================================================
let ws = null;
let wsReconnectAttempts = 0;
let clients = [];
let clientStats = {};
let lastSentData = null;
let pollingIntervalId = null;

// =============================================================================
// WebSocket Management
// =============================================================================
function getWebSocketUrl() {
  const host = window.location.host || 'localhost:8080';
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${host}/ws`;
}

function updateConnectionStatus(connected) {
  const statusEl = document.getElementById('connection-status');
  if (statusEl) {
    statusEl.textContent = connected ? 'Connected' : 'Disconnected';
    statusEl.className = `status ${connected ? 'connected' : 'disconnected'}`;
  }
}

function connectWebSocket() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    return;
  }

  const url = getWebSocketUrl();
  console.log(`WebSocket: Connecting to ${url}...`);

  try {
    ws = new WebSocket(url);
  } catch (error) {
    console.error('WebSocket: Failed to create connection:', error);
    scheduleReconnect();
    return;
  }

  ws.onopen = function() {
    console.log('WebSocket: Connected');
    wsReconnectAttempts = 0;
    updateConnectionStatus(true);
  };

  ws.onmessage = function(event) {
    try {
      const json = JSON.parse(event.data);
      clients = Object.keys(json);

      // Update stats for each client
      clients.forEach((clientIp, i) => {
        const stats = json[clientIp];
        clientStats[clientIp] = stats;
        updateGamepadPanel(i, stats.fps, stats.frame_count);
      });
    } catch (error) {
      console.error('WebSocket: Failed to parse message:', error);
    }
  };

  ws.onclose = function(event) {
    console.log(`WebSocket: Closed (code: ${event.code})`);
    updateConnectionStatus(false);
    ws = null;

    // Don't reconnect if closed cleanly by server shutdown
    if (event.code !== 1001) {
      scheduleReconnect();
    }
  };

  ws.onerror = function(error) {
    console.error('WebSocket: Error:', error);
  };
}

function scheduleReconnect() {
  if (wsReconnectAttempts >= CONFIG.WS_MAX_RECONNECT_ATTEMPTS) {
    console.log('WebSocket: Max reconnection attempts reached');
    return;
  }

  wsReconnectAttempts++;
  const delay = CONFIG.WS_RECONNECT_DELAY * Math.min(wsReconnectAttempts, 5);
  console.log(`WebSocket: Reconnecting in ${delay}ms (attempt ${wsReconnectAttempts})...`);

  setTimeout(connectWebSocket, delay);
}

// =============================================================================
// Gamepad Processing
// =============================================================================
function mapRange(value, inMin, inMax, outMin, outMax) {
  return Math.round(outMin + (value - inMin) * (outMax - outMin) / (inMax - inMin));
}

function transformAxisToStandardRange(value, min, max) {
  if (min === -1 && max === 1) {
    return value;
  }
  return ((value - min) * 2) / (max - min) - 1;
}

function getControllerConfig(gamepadId) {
  return CONTROLLER_CONFIGS[gamepadId] || CONTROLLER_CONFIGS["default"];
}

function processGamepad(gamepad) {
  if (!gamepad) return null;

  const config = getControllerConfig(gamepad.id);

  // Get axis values
  let throttleAxis = -gamepad.axes[1];  // Left stick Y (inverted)
  let steeringAxis = gamepad.axes[2];    // Right stick X

  // Apply controller-specific transformation
  if (config.rightJoystickRange) {
    const range = config.rightJoystickRange;
    steeringAxis = transformAxisToStandardRange(steeringAxis, range.min, range.max);
  }

  // Clamp to valid range
  throttleAxis = Math.max(-1, Math.min(1, throttleAxis));
  steeringAxis = Math.max(-1, Math.min(1, steeringAxis));

  // Map to output ranges
  const throttle = mapRange(throttleAxis, -1, 1, CONFIG.THROTTLE_MIN, CONFIG.THROTTLE_MAX);
  const steering = mapRange(steeringAxis, -1, 1, CONFIG.STEERING_MIN, CONFIG.STEERING_MAX);

  return {
    axes: [throttleAxis.toFixed(1), steeringAxis.toFixed(1)],
    buttons: gamepad.buttons.map(button => +button.pressed),
    command: [throttle, steering]
  };
}

function updateGamepadDisplay(gamepadIndex, data) {
  const container = document.getElementById(`gamepad-info-${gamepadIndex}`);
  if (!container) return;

  const axesEl = container.querySelector('.axes');
  const buttonsEl = container.querySelector('.buttons');

  if (axesEl && data.axes) {
    axesEl.textContent = data.axes.join(', ');
  }
  if (buttonsEl && data.buttons) {
    buttonsEl.textContent = data.buttons.join(', ');
  }
}

function updateGamepadPanel(index, fps, frameCount) {
  const panel = document.getElementById(`gamepad-info-${index}`);
  if (!panel) return;

  let statsEl = panel.querySelector('.stats');
  if (!statsEl) {
    statsEl = document.createElement('div');
    statsEl.className = 'stats';
    panel.appendChild(statsEl);
  }

  statsEl.textContent = `FPS: ${fps} | Frames: ${frameCount}`;
}

function pollGamepads() {
  const gamepads = navigator.getGamepads();
  const gamepadData = [];

  for (const gamepad of gamepads) {
    const data = processGamepad(gamepad);
    if (data) {
      gamepadData.push(data.command);

      // Update display in next animation frame
      requestAnimationFrame(() => {
        updateGamepadDisplay(gamepad.index, data);
      });
    }
  }

  // Send to server if connected
  if (ws && ws.readyState === WebSocket.OPEN && clients.length > 0) {
    const payload = {};
    clients.forEach((ip, i) => {
      if (gamepadData[i]) {
        payload[ip] = gamepadData[i];
      }
    });

    const jsonStr = JSON.stringify(payload);
    if (jsonStr !== lastSentData && Object.keys(payload).length > 0) {
      ws.send(jsonStr);
      lastSentData = jsonStr;
    }
  }
}

// =============================================================================
// Initialization
// =============================================================================
function init() {
  // Setup video stream
  const videoEl = document.getElementById('video-stream');
  if (videoEl) {
    const host = window.location.host || 'localhost:8080';
    videoEl.src = `http://${host}/video`;

    videoEl.onerror = function() {
      console.error('Video: Failed to load stream');
    };
  }

  // Connect WebSocket
  connectWebSocket();

  // Start gamepad polling
  pollingIntervalId = setInterval(pollGamepads, CONFIG.GAMEPAD_POLLING_INTERVAL);

  // Gamepad connection events
  window.addEventListener('gamepadconnected', (event) => {
    console.log(`Gamepad connected: ${event.gamepad.id} (index: ${event.gamepad.index})`);
  });

  window.addEventListener('gamepaddisconnected', (event) => {
    console.log(`Gamepad disconnected: ${event.gamepad.id} (index: ${event.gamepad.index})`);
  });

  // Cleanup on page unload
  window.addEventListener('beforeunload', () => {
    if (pollingIntervalId) {
      clearInterval(pollingIntervalId);
    }
    if (ws) {
      ws.close(1000, 'Page unload');
    }
  });

  console.log('ESP32 RC Control initialized');
}

// Start when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
