from aiohttp import web
from video_utils import process_frame_canvas
from ws_handlers import websocket_handler
import asyncio
import cv2

async def index(request):
    return web.FileResponse('./static/index.html')


async def generate_frames(request):
    shutdown_event = request.app['shutdown_event']
    loop = asyncio.get_event_loop()
    pool = request.app['thread_pool']

    while not shutdown_event.is_set():
        async with request.app['frame_lock']:
            frame_queues = dict(request.app['video_frames'])

        canvas = await loop.run_in_executor(pool, process_frame_canvas, frame_queues)
        _, jpeg_frame = cv2.imencode('.jpg', canvas)
        yield jpeg_frame.tobytes()
        await asyncio.sleep(request.app['frame_rate'])


async def video_feed(request):
    response = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "multipart/x-mixed-replace; boundary=frame",
            "Cache-Control": "no-cache"
        }
    )
    await response.prepare(request)

    try:
        async for frame in generate_frames(request):
            await response.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
    except asyncio.CancelledError:
        return

    return response
