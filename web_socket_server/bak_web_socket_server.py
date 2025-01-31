import asyncio
import base64
import json
import cv2
import numpy as np
import os
from aiohttp import web
from collections import deque
from time import time
from multiprocessing import Process, Queue

SERVER_PORT = 8080  # Port for the HTTP and Websocket server

# Frame rate configuration
FRAME_RATE = 30  # Frames per second (adjustable)
FRAME_WIDTH: int = 320
FRAME_HEIGHT: int = 240

# Utility Functions
def calculate_grid_dimensions(num_clients):
    """Calculate the grid layout dimensions based on the number of clients."""
    cols = int(np.ceil(np.sqrt(num_clients)))
    rows = int(np.ceil(num_clients / cols))
    return rows, cols

def get_offsets(index, cols):
    """Calculate x and y offsets for placing frames on the canvas."""
    x_offset = (index % cols) * FRAME_WIDTH
    y_offset = (index // cols) * FRAME_HEIGHT
    return x_offset, y_offset

# Function to generate an image with an incrementing integer using OpenCV
def generate_image(frame_queues, output_queue):
    img = process_frame_canvas(frame_queues)

    # Encode the image to JPEG format
    _, jpeg = cv2.imencode('.jpg', img)
    
    # Convert the image to bytes
    image_data = jpeg.tobytes()

    # Send the image data back to the main process
    output_queue.put(image_data)

def process_frame_canvas(frame_queues):
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

# WebSocket handler for video stream (sending frames to client)
async def video_stream(request, websocket, path):
    frame_number = 0
    while True:
        # Generate the image for the current frame
        async with request.app['frame_lock']:
            frame_queues = request.app['video_frames']

        # Use multiprocessing to process the frame grid
        output_queue = Queue()
        process = Process(target=generate_image, args=(frame_queues, output_queue))
        process.start()
        process.join()

        # Get the image data from the output queue
        image_data = output_queue.get()

        # Send the image data as a binary message
        await websocket.send_bytes(image_data)

        # Increment the frame number
        frame_number += 1

        # Sleep to control the frame rate (frame rate = 1 / sleep_time)
        await asyncio.sleep(1 / FRAME_RATE)

# WebSocket handler for receiving video stream (capture frames from client)
async def video_capture(request, websocket, path):
    print(f"Client connected to {path}")
    print("Receiving video stream from client...")
    while True:
        try:
            # Receive binary data (video frame) from the client
            frame_data = await websocket.receive_bytes()

            # Convert the byte data into a NumPy array
            np_frame = np.frombuffer(frame_data, dtype=np.uint8)

            # Decode the JPEG image
            frame = cv2.imdecode(np_frame, cv2.IMREAD_COLOR)

            if frame is not None:
                client_ip = request.remote
                if client_ip in request.app['video_frames']:
                    frame_queue = request.app['video_frames'][client_ip]
                else:
                    frame_queue = request.app['video_frames'].setdefault(client_ip, {"frames": deque(maxlen=10), "fps": 0.0, "frame_count": 0})

                # Get the current timestamp
                timestamp = time()

                # Append the frame with the timestamp
                frame_queue["frames"].append((np_frame, timestamp))

        except Exception as e:
            print(f"Error receiving frame: {e}")
            break

# Serve the index HTML page
async def index(request):
    html_path = os.path.join(os.path.dirname(__file__), 'index.html')
    
    with open(html_path, 'r') as f:
        return web.Response(text=f.read(), content_type='text/html')

# WebSocket routing handler
async def websocket_handler(request):
    websocket = web.WebSocketResponse()
    await websocket.prepare(request)

    path = request.path
    print(f"Client connected with path: {path}")

    if path == "/video":
        await video_stream(request, websocket, path)
    elif path == "/ws":
        await video_capture(request, websocket, path)
    else:
        print(f"Unknown path {path}, closing connection.")
        await websocket.close()

    return websocket

# Start the HTTP and WebSocket server with aiohttp
async def init_app():
    app = web.Application()

    # Shared state
    app['video_frames'] = {}
    app['frame_lock'] = asyncio.Lock()

    app.router.add_get('/', index)
    app.router.add_static('/static', path='./static', name='static')

    app.router.add_get('/video', websocket_handler)
    app.router.add_get('/ws', websocket_handler)

    return app

# Run the app
if __name__ == '__main__':
    app = init_app()
    web.run_app(app, host='0.0.0.0', port=SERVER_PORT)

