#!/usr/bin/env python3
"""
High-performance async MJPEG server with per-client frame caching and moving-average FPS:
- GPU/CPU canvas composition
- nvImageCodec or CPU JPEG encoding
- Async non-blocking WebSocket control commands
- Blank frames until client frames arrive
- Latest-frame-per-client: no backpressure or queue blocking
- FPS smoothed over last 10 frames
"""
import os
import asyncio
import logging
import json
import cv2
import numpy as np
from time import time
from typing import Dict, Any, Tuple
from collections import deque
from multiprocessing import cpu_count
from concurrent.futures import ThreadPoolExecutor
from aiohttp import web, WSMsgType
import contextlib

# -------------------------
# Configuration
# -------------------------
class Config:
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8080"))
    FRAME_RATE_FPS = float(os.getenv("FRAME_RATE", "60"))
    FRAME_INTERVAL = 1.0 / FRAME_RATE_FPS
    MAX_EXPECTED_CLIENTS = int(os.getenv("MAX_EXPECTED_CLIENTS", "4"))  # default 4
    MAX_THREADS = max(2, min(MAX_EXPECTED_CLIENTS * 2, cpu_count() * 2))
    FRAME_WIDTH = int(os.getenv("FRAME_WIDTH", "320"))
    FRAME_HEIGHT = int(os.getenv("FRAME_HEIGHT", "240"))
    JPEG_QUALITY = int(os.getenv("JPEG_QUALITY", "80"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    FPS_WINDOW = 10  # number of frames to average FPS

# -------------------------
# Utilities
# -------------------------
def calculate_grid_dimensions(n: int) -> Tuple[int, int]:
    if n <= 0:
        return 1, 1
    cols = int(np.ceil(np.sqrt(n)))
    rows = int(np.ceil(n / cols))
    return rows, cols

# -------------------------
# Encoder
# -------------------------
class Encoder:
    def __init__(self, nvencoder, quality: int):
        self.nvencoder = nvencoder
        self.quality = quality

    def encode(self, frame: np.ndarray) -> bytes:
        if frame is None or frame.size == 0:
            frame = np.zeros((Config.FRAME_HEIGHT, Config.FRAME_WIDTH, 3), dtype=np.uint8)
        if self.nvencoder:
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                buf = self.nvencoder.encode(rgb, '.jpg')
                if isinstance(buf, (list, tuple)):
                    return buf[0]
                return buf
            except Exception:
                pass
        ok, buf = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), self.quality])
        return buf.tobytes() if ok else b''

# -------------------------
# Canvas Processors
# -------------------------
class CanvasProcessor:
    def compose(self, frame_queues: Dict[str, Any]) -> np.ndarray:
        raise NotImplementedError

class CPUCanvasProcessor(CanvasProcessor):
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.canvas = None
        self.rows = 0
        self.cols = 0
        self.client_count = 0

    def compose(self, frame_queues):
        if not frame_queues:
            return np.zeros((self.cfg.FRAME_HEIGHT, self.cfg.FRAME_WIDTH, 3), dtype=np.uint8)

        num_clients = len(frame_queues)
        if num_clients != self.client_count:
            self.rows, self.cols = calculate_grid_dimensions(num_clients)
            h, w = self.rows * self.cfg.FRAME_HEIGHT, self.cols * self.cfg.FRAME_WIDTH
            self.canvas = np.zeros((h, w, 3), dtype=np.uint8)
            self.client_count = num_clients
        else:
            self.canvas.fill(0)

        for idx, (_, data) in enumerate(frame_queues.items()):
            frame = data.get('frame')
            if frame is None:
                continue
            y, x = (idx // self.cols) * self.cfg.FRAME_HEIGHT, (idx % self.cols) * self.cfg.FRAME_WIDTH
            self.canvas[y:y+self.cfg.FRAME_HEIGHT, x:x+self.cfg.FRAME_WIDTH] = frame
        return self.canvas

class GPUCanvasProcessor(CanvasProcessor):
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.gpu_canvas = None
        self.rows = 0
        self.cols = 0
        self.client_count = 0

    def compose(self, frame_queues):
        if not frame_queues:
            return np.zeros((self.cfg.FRAME_HEIGHT, self.cfg.FRAME_WIDTH, 3), dtype=np.uint8)

        num_clients = len(frame_queues)
        if num_clients != self.client_count:
            self.rows, self.cols = calculate_grid_dimensions(num_clients)
            h, w = self.rows * self.cfg.FRAME_HEIGHT, self.cols * self.cfg.FRAME_WIDTH
            self.gpu_canvas = cv2.cuda_GpuMat()
            self.gpu_canvas.upload(np.zeros((h, w, 3), dtype=np.uint8))
            self.client_count = num_clients
        else:
            self.gpu_canvas.upload(np.zeros(self.gpu_canvas.size()[::-1] + (3,), dtype=np.uint8))

        for idx, (_, data) in enumerate(frame_queues.items()):
            frame = data.get('frame')
            if frame is None:
                continue
            y, x = (idx // self.cols) * self.cfg.FRAME_HEIGHT, (idx % self.cols) * self.cfg.FRAME_WIDTH

            try:
                # only resize if necessary
                if not isinstance(frame, cv2.cuda_GpuMat):
                    if frame.shape[:2] != (self.cfg.FRAME_HEIGHT, self.cfg.FRAME_WIDTH):
                        frame = cv2.resize(frame, (self.cfg.FRAME_WIDTH, self.cfg.FRAME_HEIGHT))
                    gpu_frame = cv2.cuda_GpuMat()
                    gpu_frame.upload(frame)
                else:
                    gpu_frame = frame
                roi = self.gpu_canvas.rowRange(y, y+self.cfg.FRAME_HEIGHT).colRange(x, x+self.cfg.FRAME_WIDTH)
                gpu_frame.copyTo(roi)
            except Exception:
                # fallback to CPU
                cpu_canvas = self.gpu_canvas.download()
                f = frame if isinstance(frame, np.ndarray) else frame.download()
                if f.shape[:2] != (self.cfg.FRAME_HEIGHT, self.cfg.FRAME_WIDTH):
                    f = cv2.resize(f, (self.cfg.FRAME_WIDTH, self.cfg.FRAME_HEIGHT))
                cpu_canvas[y:y+self.cfg.FRAME_HEIGHT, x:x+self.cfg.FRAME_WIDTH] = f
                self.gpu_canvas.upload(cpu_canvas)

        return self.gpu_canvas.download()

# -------------------------
# Application Context
# -------------------------
class AppContext:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.have_cuda = False
        self.nvencoder = None
        self.encoder = None
        self.canvas_processor = None
        self.check_capabilities()
        self._warmup_gpu()

    def check_capabilities(self):
        try:
            if cv2.cuda.getCudaEnabledDeviceCount() > 0:
                self.have_cuda = True
                logging.info("CUDA available.")
        except Exception:
            logging.info("CUDA not available.")

        try:
            from nvidia import nvimgcodec
            self.nvencoder = nvimgcodec.Encoder()
            logging.info("nvImageCodec available.")
        except Exception:
            self.nvencoder = None
            logging.info("nvImageCodec not available.")

        self.encoder = Encoder(self.nvencoder, self.cfg.JPEG_QUALITY)
        self.canvas_processor = GPUCanvasProcessor(self.cfg) if self.have_cuda else CPUCanvasProcessor(self.cfg)

    def _warmup_gpu(self):
        if self.have_cuda:
            blank = np.zeros((self.cfg.FRAME_HEIGHT, self.cfg.FRAME_WIDTH, 3), dtype=np.uint8)
            g = cv2.cuda_GpuMat()
            g.upload(blank)
            g.download()

# -------------------------
# Frame Processor
# -------------------------
class FrameProcessor:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.loop = asyncio.get_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=ctx.cfg.MAX_THREADS)

    async def process_frames_async(self, frame_queues):
        # copy to avoid "Future already retrieved"
        return await self.loop.run_in_executor(self.executor, self._process_frames_sync, dict(frame_queues))

    def _process_frames_sync(self, frame_queues):
        if not frame_queues:
            blank = np.zeros((self.ctx.cfg.FRAME_HEIGHT, self.ctx.cfg.FRAME_WIDTH, 3), dtype=np.uint8)
            return self.ctx.encoder.encode(blank)
        canvas = self.ctx.canvas_processor.compose(frame_queues)
        return self.ctx.encoder.encode(canvas)

# -------------------------
# MJPEG Server
# -------------------------
class MJPEGServer:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.processor = FrameProcessor(ctx)

    async def handle_binary(self, msg, client_ip, request, ws):
        cfg = self.ctx.cfg
        try:
            arr = np.frombuffer(msg.data, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                return
            if frame.shape[:2] != (cfg.FRAME_HEIGHT, cfg.FRAME_WIDTH):
                frame = cv2.resize(frame, (cfg.FRAME_WIDTH, cfg.FRAME_HEIGHT))
        except Exception:
            return

        stored_frame = frame
        if self.ctx.have_cuda:
            try:
                g = cv2.cuda_GpuMat()
                g.upload(frame)
                stored_frame = g
            except Exception:
                pass

        fq = request.app['video_frames'].setdefault(client_ip, {})
        fq['frame'] = stored_frame
        fq.setdefault('timestamps', deque(maxlen=cfg.FPS_WINDOW))
        fq['timestamps'].append(time())
        ts = fq['timestamps']
        if len(ts) >= 2:
            dt = ts[-1] - ts[0]
            fq['fps'] = (len(ts)-1)/dt if dt > 0 else 0.0
        else:
            fq['fps'] = 0.0

        # send control commands immediately when frame is received
        if client_ip in request.app['control_commands']:
            cmd = request.app['control_commands'][client_ip]
            asyncio.create_task(ws.send_str(f"CONTROL:{cmd[0]}:{cmd[1]}"))

    async def handle_text(self, msg, request, ws):
        # preserve your working logic
        if msg.data == 'close':
            await ws.close()
            return
        try:
            request.app['control_commands'].update(json.loads(msg.data))
        except json.JSONDecodeError:
            logging.warning(f"Invalid JSON from client {request.remote}: {msg.data}")
        video_info = {
            ip: {
                "fps": int(d.get("fps", 0)),
                "frame_count": len(d.get("timestamps", []))
            } for ip, d in request.app['video_frames'].items()
        }
        await ws.send_json(video_info)

    async def websocket_handler(self, request):
        ws = web.WebSocketResponse(heartbeat=20.0, timeout=60.0)
        await ws.prepare(request)
        client_ip = request.remote or "unknown"
        logging.info(f"WS connect: {client_ip}")
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    await self.handle_text(msg, request, ws)
                elif msg.type == WSMsgType.BINARY:
                    await self.handle_binary(msg, client_ip, request, ws)
        finally:
            request.app['video_frames'].pop(client_ip, None)
            logging.info(f"WS disconnect: {client_ip}")
        return ws

    async def generate_frames(self, request):
        shutdown_event = request.app['shutdown_event']
        cfg = self.ctx.cfg
        while not shutdown_event.is_set():
            async with request.app['frame_lock']:
                frame_queues = dict(request.app['video_frames'])
            try:
                jpeg_bytes = await self.processor.process_frames_async(frame_queues)
                if jpeg_bytes:
                    yield jpeg_bytes
            except Exception as e:
                logging.warning(f"Frame generation error: {e}")
            await asyncio.sleep(cfg.FRAME_INTERVAL)

    async def video_feed(self, request):
        response = web.StreamResponse(
            status=200,
            headers={"Content-Type": "multipart/x-mixed-replace; boundary=frame",
                     "Cache-Control": "no-cache, no-store", "Pragma": "no-cache"}
        )
        await response.prepare(request)
        try:
            async for jpeg in self.generate_frames(request):
                try:
                    await response.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
                except (ConnectionResetError, BrokenPipeError, asyncio.CancelledError):
                    break
        finally:
            with contextlib.suppress(Exception):
                await response.write_eof()
        return response

# -------------------------
# App Setup
# -------------------------
async def cleanup(app):
    logging.info("Cleanup: shutting down.")
    app['shutdown_event'].set()
    for t in asyncio.all_tasks():
        if t is not asyncio.current_task():
            t.cancel()
    app['thread_pool'].shutdown(wait=False, cancel_futures=True)
    logging.info("Cleanup complete.")

async def create_app():
    cfg = Config()
    ctx = AppContext(cfg)
    server = MJPEGServer(ctx)

    app = web.Application()
    app['shutdown_event'] = asyncio.Event()
    app['video_frames'] = {}
    app['control_commands'] = {}
    app['frame_lock'] = asyncio.Lock()
    app['thread_pool'] = ThreadPoolExecutor(max_workers=cfg.MAX_THREADS)

    app.router.add_get("/", lambda r: web.FileResponse("./static/index.html"))
    app.router.add_get("/video", server.video_feed)
    app.router.add_get("/ws", server.websocket_handler)
    app.router.add_static("/static", path="./static", name="static")
    app.on_cleanup.append(cleanup)
    return app

async def main():
    logging.basicConfig(level=Config.LOG_LEVEL, format="[%(asctime)s] %(levelname)s: %(message)s")
    app = await create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, Config.HOST, Config.PORT)
    await site.start()
    logging.info(f"Server listening at http://{Config.HOST}:{Config.PORT}")
    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await app.shutdown()
        await app.cleanup()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(main())

