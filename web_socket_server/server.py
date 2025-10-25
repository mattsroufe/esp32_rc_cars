from aiohttp import web
from video_utils import process_frame_canvas
from ws_handlers import websocket_handler
import asyncio
import cv2
import logging

async def index(request):
    return web.FileResponse('./static/index.html')


async def generate_frames(request):
    shutdown_event = request.app['shutdown_event']
    loop = asyncio.get_event_loop()
    pool = request.app['thread_pool']

    while not shutdown_event.is_set():
        async with request.app['frame_lock']:
            # Copy the video frame dictionary safely
            frame_queues = dict(request.app['video_frames'])

        # Run frame composition in executor thread (non-blocking)
        canvas = await loop.run_in_executor(pool, process_frame_canvas, frame_queues)

        success, jpeg_frame = cv2.imencode('.jpg', canvas)
        if not success:
            logging.warning("Failed to encode frame to JPEG.")
            await asyncio.sleep(request.app['frame_rate'])
            continue

        yield jpeg_frame.tobytes()
        await asyncio.sleep(request.app['frame_rate'])


async def video_feed(request):
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=frame",
            "Cache-Control": "no-cache",
        },
    )

    await response.prepare(request)

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

