import asyncio
import websockets
import io
import os
from PIL import Image, ImageDraw, ImageFont
from aiohttp import web

# Frame rate configuration
FRAME_RATE = 30  # Frames per second (adjustable)
PORT = 8080

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
async def video_stream(websocket):
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

# Serve the index HTML page
async def index(request):
    # Path to the HTML file
    html_path = os.path.join(os.path.dirname(__file__), 'bak_index.html')
    
    # Read and return the HTML file as response
    with open(html_path, 'r') as f:
        return web.Response(text=f.read(), content_type='text/html')

# Start the WebSocket server and HTTP server
async def main():
    # Create a web application to serve the index page
    app = web.Application()

    # Serve the index page on the root URL
    app.router.add_get('/', index)

    # Start the HTTP server to serve the HTML file
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', PORT)
    print(f"HTTP server running on http://localhost:{PORT}")
    
    # Start the WebSocket server
    websocket_server = websockets.serve(video_stream, 'localhost', PORT + 1)
    print(f"WebSocket server running on ws://localhost:{PORT}/video")
    
    # Run both HTTP and WebSocket servers concurrently
    await asyncio.gather(site.start(), websocket_server)

    # Keep the server running indefinitely
    while True:
        await asyncio.sleep(3600)  # Sleep indefinitely, keeping server alive

# Run the server
if __name__ == "__main__":
    asyncio.run(main())

