import cv2
import numpy as np
from collections import deque
from typing import Dict, Deque, Tuple, Any

FRAME_WIDTH = 320
FRAME_HEIGHT = 240

FrameQueue = Deque[Tuple[bytes, float]]
VideoFrames = Dict[str, Dict[str, Any]]  # {"frames": FrameQueue, "fps": float, "frame_count": int}

def calculate_grid_dimensions(num_clients: int) -> Tuple[int, int]:
    cols = int(np.ceil(np.sqrt(num_clients)))
    rows = int(np.ceil(num_clients / cols))
    return rows, cols

def get_offsets(index: int, cols: int) -> Tuple[int, int]:
    return (index % cols) * FRAME_WIDTH, (index // cols) * FRAME_HEIGHT

def calculate_frame_rate(frame_queue: FrameQueue) -> float:
    timestamps = [ts for _, ts in frame_queue]
    if len(timestamps) > 1:
        return round((len(timestamps) - 1) / (timestamps[-1] - timestamps[0]), 1)
    return 0.0

def process_frame_canvas(frame_queues: VideoFrames) -> np.ndarray:
    """
    Combine all client frames into a single canvas.
    Handles empty frames or missing data gracefully.
    """
    num_clients = len(frame_queues)
    if num_clients == 0:
        return np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)

    rows, cols = calculate_grid_dimensions(num_clients)
    canvas = np.zeros((rows * FRAME_HEIGHT, cols * FRAME_WIDTH, 3), dtype=np.uint8)

    for i, (client_ip, client_data) in enumerate(frame_queues.items()):
        frame_queue = client_data.get("frames", deque())
        if not frame_queue:
            continue

        compressed_frame, _ = frame_queue[-1]  # latest frame
        if compressed_frame is None:
            continue

        frame_array = np.frombuffer(compressed_frame, dtype=np.uint8)
        frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
        if frame is None or frame.shape[0] == 0 or frame.shape[1] == 0:
            continue

        x_offset, y_offset = get_offsets(i, cols)
        # Resize frame if needed to match expected dimensions
        if frame.shape[1] != FRAME_WIDTH or frame.shape[0] != FRAME_HEIGHT:
            frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))

        canvas[y_offset:y_offset + FRAME_HEIGHT, x_offset:x_offset + FRAME_WIDTH] = frame

    return canvas
