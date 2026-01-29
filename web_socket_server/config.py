"""Server configuration from environment variables."""

import os
from multiprocessing import cpu_count

# =============================================================================
# Server Configuration
# =============================================================================
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

# =============================================================================
# Video Configuration
# =============================================================================
FRAME_RATE_FPS = float(os.getenv("FRAME_RATE", "30"))
FRAME_RATE = 1.0 / FRAME_RATE_FPS  # Convert to interval in seconds

# Maximum expected concurrent ESP32 clients
MAX_EXPECTED_CLIENTS = int(os.getenv("MAX_EXPECTED_CLIENTS", "8"))

# =============================================================================
# Thread Pool Configuration
# =============================================================================
# Thread pool size for CPU-bound video processing
# Minimum 2, maximum based on expected clients or CPU cores
MAX_THREADS = max(2, min(MAX_EXPECTED_CLIENTS, cpu_count() * 2))

# =============================================================================
# WebSocket Configuration
# =============================================================================
WS_HEARTBEAT_INTERVAL = float(os.getenv("WS_HEARTBEAT", "30.0"))
