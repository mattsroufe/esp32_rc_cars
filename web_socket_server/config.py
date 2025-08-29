import os
from multiprocessing import cpu_count

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

# Video
FRAME_RATE_FPS = float(os.getenv("FRAME_RATE", "30"))
FRAME_RATE = 1.0 / FRAME_RATE_FPS
MAX_EXPECTED_CLIENTS = int(os.getenv("MAX_EXPECTED_CLIENTS", "8"))

# Thread pool
MAX_THREADS = max(2, min(MAX_EXPECTED_CLIENTS, cpu_count() * 2))
