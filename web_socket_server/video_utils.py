import numpy as np
from collections import deque
from typing import Dict, Deque, Tuple, Any
import cv2
import math

# Type Aliases
FrameQueue = Deque[Tuple[bytes, float]]
VideoFrames = Dict[str, Dict[str, Any]]  # {"frames": FrameQueue, "fps": float, "frame_count": int}

FRAME_WIDTH = 320
FRAME_HEIGHT = 240

def calculate_frame_rate(frame_queue: FrameQueue) -> float:
    """Compute FPS from a deque of (frame, timestamp) tuples."""
    timestamps = [ts for _, ts in frame_queue]
    if len(timestamps) > 1:
        return round((len(timestamps)-1) / (timestamps[-1]-timestamps[0]), 1)
    return 0.0

def calculate_grid_dimensions(num_clients: int) -> Tuple[int, int]:
    """Compute grid rows and cols to arrange frames."""
    cols = int(math.ceil(math.sqrt(num_clients)))
    rows = int(math.ceil(num_clients / cols))
    return rows, cols

def get_offsets(index: int, cols: int) -> Tuple[int, int]:
    """Compute x, y offset of a frame in the canvas grid."""
    return (index % cols) * FRAME_WIDTH, (index // cols) * FRAME_HEIGHT

def process_frame_canvas(frame_queues: VideoFrames) -> np.ndarray:
    """Generate a single canvas frame from all WebSocket video streams."""
    num_clients = len(frame_queues)
    if num_clients == 0:
        return np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)

    rows, cols = calculate_grid_dimensions(num_clients)
    canvas = np.zeros((rows*FRAME_HEIGHT, cols*FRAME_WIDTH, 3), dtype=np.uint8)

    for idx, (client_ip, client_data) in enumerate(frame_queues.items()):
        queue: FrameQueue = client_data.get("frames", deque())
        if not queue:
            continue

        # Use the latest frame
        compressed_frame, _ = queue[-1]
        frame_array = np.frombuffer(compressed_frame, dtype=np.uint8)
        frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
        if frame is None:
            continue

        x_offset, y_offset = get_offsets(idx, cols)
        # Resize to uniform frame size
        frame_resized = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
        canvas[y_offset:y_offset+FRAME_HEIGHT, x_offset:x_offset+FRAME_WIDTH] = frame_resized

    return canvas
