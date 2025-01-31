import asyncio
import cv2
import numpy as np
import os
from aiohttp import web

# Frame rate configuration
FRAME_RATE = 30  # Frames per second (adjustable)
HTTP_PORT = 8080  # Port for the HTTP server (serving HTML)

# Function to generate an image with an incrementing integer using OpenCV
def generate_image(frame_number):
    # Create a black image (480p resolution)
    img = np.zeros((480, 640, 3), dtype=np.uint8)

    # Add frame number text onto the image
    text = f"Frame: {frame_number}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(img, text, (50, 240), font, 1, (255, 255, 255), 2, cv2.LINE_AA)

    # Encode the image to JPEG format
    _, jpeg = cv2.imencode('.jpg', img)
    
    # Convert the image to bytes
    return jpeg.tobytes()

# WebSocket handler for video stream (sending frames to client)
async def video_stream(websocket, path):
    frame_number = 0
    while True:
        # Generate the image for the current frame
        image_data = generate_image(frame_number)

        # Send the image data as a binary message
        await websocket.send_bytes(image_data)

        # Increment the frame number
        frame_number += 1

        # Sleep to control the frame rate (frame rate = 1 / sleep_time)
        await asyncio.sleep(1 / FRAME_RATE)

# WebSocket handler for receiving video stream (capture frames from client)
async def video_capture(websocket, path):
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
                # Optionally, display the received frame (for debugging purposes)
                cv2.imshow('Received Frame', frame)

                # Wait for a keypress to exit (only if running a GUI to show frames)
                cv2.waitKey(1)  # This makes OpenCV non-blocking

        except Exception as e:
            print(f"Error receiving frame: {e}")
            break

# Serve the index HTML page
async def index(request):
    # Path to the HTML file
    html_path = os.path.join(os.path.dirname(__file__), 'index.html')
    
    # Read and return the HTML file as response
    with open(html_path, 'r') as f:
        return web.Response(text=f.read(), content_type='text/html')

# WebSocket routing handler
async def websocket_handler(request):
    websocket = web.WebSocketResponse()
    await websocket.prepare(request)

    path = request.path
    print(f"Client connected with path: {path}")

    # Route based on the path
    if path == "/video":
        await video_stream(websocket, path)
    elif path == "/ws":
        await video_capture(websocket, path)
    else:
        print(f"Unknown path {path}, closing connection.")
        await websocket.close()

    return websocket

# Start the HTTP and WebSocket server with aiohttp
async def init_app():
    app = web.Application()

    # Serve the index page on the root URL
    app.router.add_get('/', index)
    app.router.add_static('/static', path='./static', name='static')

    # WebSocket routes
    app.router.add_get('/video', websocket_handler)
    app.router.add_get('/ws', websocket_handler)

    return app

# Run the app
if __name__ == '__main__':
    app = init_app()
    web.run_app(app, host='0.0.0.0', port=HTTP_PORT)

