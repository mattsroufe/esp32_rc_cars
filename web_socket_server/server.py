import asyncio
import logging
import cv2
from aiohttp import web
from video_utils import process_frame_canvas
from ws_handlers import websocket_handler

async def index(request):
    return web.FileResponse('./static/index.html')


async def generate_frames(request):
    """
    Compose and encode video frames from all connected clients.
    Uses OpenCV for JPEG encoding (no TurboJPEG dependency).
    """
    shutdown_event = request.app['shutdown_event']
    pool = request.app['thread_pool']
    loop = asyncio.get_event_loop()
    frame_rate = request.app['frame_rate']

    while not shutdown_event.is_set():
        async with request.app['frame_lock']:
            frame_queues = request.app['video_frames']

        # Run frame composition (expensive) in the thread pool
        try:
            canvas = await loop.run_in_executor(pool, process_frame_canvas, frame_queues)
        except Exception as e:
            logging.warning(f"Frame composition failed: {e}")
            await asyncio.sleep(frame_rate)
            continue

        # Encode to JPEG using OpenCV
        success, jpeg_buf = cv2.imencode('.jpg', canvas, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not success:
            logging.warning("Failed to encode frame to JPEG.")
            await asyncio.sleep(frame_rate)
            continue

        yield jpeg_buf.tobytes()

        # Limit frame generation rate
        await asyncio.sleep(frame_rate)


async def video_feed(request):
    """
    MJPEG video stream endpoint (/video).
    """
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=frame",
            "Cache-Control": "no-cache"
        }
    )

    await response.prepare(request)
    logging.info("Client connected to /video stream")

    try:
        async for frame in generate_frames(request):
            try:
                await response.write(
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" +
                    frame +
                    b"\r\n"
                )
            except (ConnectionResetError, asyncio.CancelledError, BrokenPipeError):
                logging.info("Client disconnected from video stream.")
                break
    finally:
        try:
            await response.write_eof()
        except Exception:
            pass
        logging.info("Video stream closed.")

    return response

