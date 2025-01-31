import logging
import asyncio
import io
import json
from typing import Dict, Deque, Tuple, Any, Optional, Generator
from aiohttp import web, WSCloseCode, WSMessage
import aiohttp
import cv2
import numpy as np
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from time import time
from PIL import Image, ImageDraw, ImageFont

# Constants
FRAME_WIDTH: int = 320
FRAME_HEIGHT: int = 240
FRAME_RATE: float = 1 / 30

# Type Aliases
FrameQueue = Deque[Tuple[bytes, float]]
ControlCommands = Dict[str, Tuple[float, float]]
VideoFrames = Dict[str, FrameQueue]

# Utility Functions
def calculate_grid_dimensions(num_clients: int) -> Tuple[int, int]:
    """Calculate the grid layout dimensions based on the number of clients."""
    cols = int(np.ceil(np.sqrt(num_clients)))
    rows = int(np.ceil(num_clients / cols))
    return rows, cols

def get_offsets(index: int, cols: int) -> Tuple[int, int]:
    """Calculate x and y offsets for placing frames on the canvas."""
    x_offset = (index % cols) * FRAME_WIDTH
    y_offset = (index // cols) * FRAME_HEIGHT
    return x_offset, y_offset

def calculate_frame_rate(frame_queue: FrameQueue) -> float:
    """Calculate the frame rate from a queue of timestamps."""
    timestamps = [ts for _, ts in frame_queue]
    if len(timestamps) > 1:
        return round((len(timestamps) - 1) / (timestamps[-1] - timestamps[0]), 1)
    return 0.0

def process_frame_canvas(frame_queues: VideoFrames) -> np.ndarray:
    """Create a canvas with video frames arranged in a grid."""
    num_clients = len(frame_queues)
    if num_clients == 0:
        return np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)

    rows, cols = calculate_grid_dimensions(num_clients)
    canvas = np.zeros((rows * FRAME_HEIGHT, cols * FRAME_WIDTH, 3), dtype=np.uint8)

    for i, (client_ip, client_data) in enumerate(frame_queues.items()):
        frame_queue = client_data["frames"]
        if not frame_queue:
            continue

        compressed_frame, _ = frame_queue[-1]  # Use the latest frame
        frame_array = np.frombuffer(compressed_frame, dtype=np.uint8)
        frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
        x_offset, y_offset = get_offsets(i, cols)
        canvas[y_offset:y_offset + FRAME_HEIGHT, x_offset:x_offset + FRAME_WIDTH] = frame

    return canvas

# WebSocket Handlers
async def handle_text_message(msg: WSMessage, request: web.Request, ws: web.WebSocketResponse) -> None:
    """Handle text messages from WebSocket."""
    if msg.data == 'close':
        await ws.close()
    else:
        request.app['control_commands'].update(json.loads(msg.data))
        video_info = {
            client_ip: {
                "fps": client_data["fps"],
                "frame_count": client_data["frame_count"]
            }
            for client_ip, client_data in request.app['video_frames'].items()
        }
        # Send video frame information back to the client
        await ws.send_json(video_info)

async def handle_binary_message(msg: WSMessage, client_ip: str, request: web.Request, ws: web.WebSocketResponse) -> None:
    """Handle binary messages from WebSocket."""
    if client_ip in request.app['video_frames']:
        frame_queue = request.app['video_frames'][client_ip]
    else:
        frame_queue = request.app['video_frames'].setdefault(client_ip, {"frames": deque(maxlen=10), "fps": 0.0, "frame_count": 0})

    # Get the current timestamp
    timestamp = time()

    # Append the frame with the timestamp
    frame_queue["frames"].append((msg.data, timestamp))

    # Calculate the FPS based on the frame queue
    fps = calculate_frame_rate(frame_queue["frames"])
    frame_count = len(frame_queue["frames"])

    # Update FPS and frame count in the dictionary
    frame_queue["fps"] = fps
    frame_queue["frame_count"] = frame_count

    # Save the updated frame queue back to the dictionary
    request.app['video_frames'][client_ip] = frame_queue

    # Check for control commands for this client
    if client_ip in request.app['control_commands']:
        command = request.app['control_commands'][client_ip]
        await ws.send_str(f"CONTROL:{command[0]}:{command[1]}")

# HTTP Handlers
async def index(request: web.Request) -> web.Response:
    """Serve the index HTML page."""
    return web.Response(text=open('index.html').read(), content_type='text/html')

async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle WebSocket connections."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    client_ip = request.remote or "unknown"

    async for msg in ws:
        if msg.type == aiohttp.WSMsgType.TEXT:
            await handle_text_message(msg, request, ws)
        elif msg.type == aiohttp.WSMsgType.BINARY:
            await handle_binary_message(msg, client_ip, request, ws)
        elif msg.type == aiohttp.WSMsgType.ERROR:
            logging.error(f"WebSocket error: {ws.exception()}")

    return ws

async def generate_frames(request: web.Request, pool: ProcessPoolExecutor) -> Generator[bytes, None, None]:
    """Generate video frames for streaming."""
    shutdown_event: asyncio.Event = request.app['shutdown_event']
    while not shutdown_event.is_set():
        async with request.app['frame_lock']:
            frame_queues = request.app['video_frames']

        canvas = await asyncio.get_event_loop().run_in_executor(pool, process_frame_canvas, frame_queues)
        _, jpeg_frame = cv2.imencode('.jpg', canvas)
        yield jpeg_frame.tobytes()
        await asyncio.sleep(FRAME_RATE)

async def stream_video_old(request: web.Request) -> web.StreamResponse:
    """Stream video frames as an HTTP response."""
    response = web.StreamResponse(
        status=200,
        headers={
            'Content-Type': 'multipart/x-mixed-replace; boundary=frame',
            'Cache-Control': 'no-cache',
        }
    )
    await response.prepare(request)

    pool: ProcessPoolExecutor = request.app['process_pool']
    async for frame in generate_frames(request, pool):
        await response.write(
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
        )
    return response

# Function to generate an image with an incrementing integer
def generate_image(frame_number):
    # Create an image with a black background
    img = Image.new('RGB', (640, 480), color='black')
    draw = ImageDraw.Draw(img)

    # Draw the frame number as text on the image
    text = f"Frame: {frame_number}"
    font = ImageFont.load_default()
    draw.text((50, 200), text, font=font, fill="white")

    # Save image to a BytesIO object
    img_byte_array = io.BytesIO()
    img.save(img_byte_array, format='JPEG')
    img_byte_array.seek(0)

    return img_byte_array.getvalue()

# WebSocket handler for video stream
async def stream_video(websocket):
    frame_number = 0
    while True:
        # Generate the image for the current frame
        image_data = generate_image(frame_number)

        # Send the image data as a binary message
        await websocket.send(image_data)

        # Increment the frame number
        frame_number += 1

        # Sleep to control the frame rate (frame rate = 1 / sleep_time)
        await asyncio.sleep(1 / FRAME_RATE)


# Cleanup Function
async def cleanup(app: web.Application) -> None:
    """Clean up resources on shutdown."""
    logging.info("Shutting down resources...")
    app['shutdown_event'].set()
    app['process_pool'].shutdown()

# Main Function
def main() -> None:
    logging.basicConfig(level=logging.DEBUG)
    app = web.Application()

    # Shared state
    app['video_frames']: VideoFrames = {}
    app['control_commands']: ControlCommands = {}
    app['frame_lock'] = asyncio.Lock()
    app['shutdown_event'] = asyncio.Event()
    app['process_pool'] = ProcessPoolExecutor(max_workers=4)

    # Routes
    app.router.add_get('/', index)
    app.router.add_get('/video', stream_video)
    app.router.add_get('/ws', websocket_handler)
    app.router.add_static('/static', path='./static', name='static')

    # Cleanup on shutdown
    app.on_shutdown.append(cleanup)

    web.run_app(app, host='0.0.0.0', port=8080)

if __name__ == "__main__":
    main()
