import logging
import cv2
import numpy as np
import asyncio
from aiohttp import web
import io

# Define the size of the canvas
width, height = 640, 480

async def index(request):
    return web.Response(text=open('index.html').read(), content_type='text/html')

# Function to generate the image with the integer in the middle
def create_canvas_with_integer(current_integer):
    # Create a black canvas
    canvas = np.zeros((height, width, 3), dtype=np.uint8)

    # Convert the integer to a string and calculate the text size
    text = str(current_integer)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 3
    thickness = 5
    (text_width, text_height), _ = cv2.getTextSize(text, font, font_scale, thickness)

    # Calculate the position to center the text
    text_x = (width - text_width) // 2
    text_y = (height + text_height) // 2

    # Put the text on the canvas
    cv2.putText(canvas, text, (text_x, text_y), font, font_scale, (255, 255, 255), thickness)

    return canvas

# Define an async generator to stream video
async def stream_video(request):
    current_integer = 0
    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'multipart/x-mixed-replace; boundary=frame'
        }
    )
    await response.prepare(request)

    async def generate():
        nonlocal current_integer

        # Simulate a continuous stream
        while True:
            # Generate the canvas with the current integer
            frame = create_canvas_with_integer(current_integer)

            # Convert the frame to JPEG format
            ret, jpeg_frame = cv2.imencode('.jpg', frame)
            if not ret:
                break

            # Create a byte buffer for the frame
            byte_data = jpeg_frame.tobytes()

            # Write the frame to the stream in chunks
            yield(byte_data)

            print(current_integer)
            # Update the integer for the next frame
            current_integer += 1

            # Simulate a delay for video frame rate (e.g., 30 fps)
            await asyncio.sleep(1)

    async for frame_data in generate():
        await response.write(
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n\r\n'
        )

    await response.write_eof()
    return response



# Create the aiohttp web application
logging.basicConfig(level=logging.DEBUG)
app = web.Application()
app.router.add_get('/', index)
app.router.add_static('/static', path='./static', name='static')
app.router.add_get('/video', stream_video)

# Run the app
if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=8080)

