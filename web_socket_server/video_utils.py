"""Video frame processing utilities."""

from collections import deque
from typing import Dict, Deque, Tuple, Any

import cv2
import numpy as np

# Frame dimensions for the composite grid
FRAME_WIDTH = 320
FRAME_HEIGHT = 240

# Type aliases
FrameQueue = Deque[Tuple[bytes, float]]
VideoFrames = Dict[str, Dict[str, Any]]


def calculate_grid_dimensions(num_clients: int) -> Tuple[int, int]:
    """
    Calculate optimal grid dimensions for N clients.

    Returns (rows, cols) that minimize wasted space while
    keeping the grid as square as possible.
    """
    if num_clients <= 0:
        return (1, 1)

    cols = int(np.ceil(np.sqrt(num_clients)))
    rows = int(np.ceil(num_clients / cols))
    return (rows, cols)


def get_frame_offset(index: int, cols: int) -> Tuple[int, int]:
    """Calculate (x, y) pixel offset for a frame in the grid."""
    x = (index % cols) * FRAME_WIDTH
    y = (index // cols) * FRAME_HEIGHT
    return (x, y)


def calculate_frame_rate(frame_queue: FrameQueue) -> float:
    """
    Calculate FPS from frame timestamps.

    Uses the timestamps in the queue to compute actual frame rate.
    """
    if len(frame_queue) < 2:
        return 0.0

    timestamps = [ts for _, ts in frame_queue]
    duration = timestamps[-1] - timestamps[0]

    if duration <= 0:
        return 0.0

    return round((len(timestamps) - 1) / duration, 1)


def decode_frame(compressed_frame: bytes) -> np.ndarray:
    """
    Decode a JPEG frame to a numpy array.

    Returns None if decoding fails.
    """
    # Copy to avoid memory view issues when deque cleans up
    frame_array = np.frombuffer(compressed_frame, dtype=np.uint8).copy()
    return cv2.imdecode(frame_array, cv2.IMREAD_COLOR)


def resize_frame(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    """Resize frame if dimensions don't match expected size."""
    if frame.shape[1] != width or frame.shape[0] != height:
        return cv2.resize(frame, (width, height))
    return frame


def process_frame_canvas(frame_queues: VideoFrames) -> np.ndarray:
    """
    Combine all client frames into a single composite canvas.

    Creates a grid layout where each ESP32's video feed occupies
    one cell. Empty cells are filled with black.

    Args:
        frame_queues: Dict mapping client IPs to their frame data

    Returns:
        Composite numpy array (BGR image)
    """
    num_clients = len(frame_queues)

    # Return black frame if no clients
    if num_clients == 0:
        return np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)

    # Calculate grid dimensions
    rows, cols = calculate_grid_dimensions(num_clients)
    canvas = np.zeros((rows * FRAME_HEIGHT, cols * FRAME_WIDTH, 3), dtype=np.uint8)

    # Place each client's frame in the grid
    for i, (client_ip, client_data) in enumerate(frame_queues.items()):
        frame_queue = client_data.get("frames", deque())
        if not frame_queue:
            continue

        # Get latest frame
        compressed_frame, _ = frame_queue[-1]
        if compressed_frame is None:
            continue

        # Decode frame
        frame = decode_frame(compressed_frame)
        if frame is None or frame.size == 0:
            continue

        # Resize to expected dimensions
        frame = resize_frame(frame, FRAME_WIDTH, FRAME_HEIGHT)

        # Place in grid
        x_offset, y_offset = get_frame_offset(i, cols)
        canvas[y_offset:y_offset + FRAME_HEIGHT, x_offset:x_offset + FRAME_WIDTH] = frame

    return canvas
