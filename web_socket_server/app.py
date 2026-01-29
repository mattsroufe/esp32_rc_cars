#!/usr/bin/env python3
"""
ESP32 RC Cars WebSocket Server

A multi-client video streaming and control relay server for ESP32-based RC cars.
Handles graceful shutdown on SIGINT/SIGTERM.
"""

import asyncio
import logging
import signal
import sys
from typing import Set

from aiohttp import web
from concurrent.futures import ThreadPoolExecutor

from server import index, video_feed
from ws_handlers import websocket_handler
from cleanup import cleanup
from config import HOST, PORT, MAX_THREADS, FRAME_RATE

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class GracefulShutdown:
    """Manages graceful shutdown of the server."""

    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self.active_websockets: Set[web.WebSocketResponse] = set()
        self._shutdown_initiated = False

    def register_websocket(self, ws: web.WebSocketResponse):
        self.active_websockets.add(ws)

    def unregister_websocket(self, ws: web.WebSocketResponse):
        self.active_websockets.discard(ws)

    async def shutdown(self):
        """Initiate graceful shutdown."""
        if self._shutdown_initiated:
            return
        self._shutdown_initiated = True

        logger.info("Initiating graceful shutdown...")
        self.shutdown_event.set()

        # Close all active WebSocket connections
        if self.active_websockets:
            logger.info(f"Closing {len(self.active_websockets)} WebSocket connection(s)...")
            close_tasks = [
                ws.close(code=1001, message=b'Server shutting down')
                for ws in self.active_websockets
                if not ws.closed
            ]
            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)

        logger.info("Shutdown complete")


async def create_application() -> web.Application:
    """Create and configure the aiohttp application."""
    app = web.Application()

    # Initialize shutdown manager
    shutdown_manager = GracefulShutdown()
    app['shutdown_manager'] = shutdown_manager
    app['shutdown_event'] = shutdown_manager.shutdown_event

    # Shared state
    app['video_frames'] = {}
    app['control_commands'] = {}
    app['frame_lock'] = asyncio.Lock()
    app['thread_pool'] = ThreadPoolExecutor(max_workers=MAX_THREADS)
    app['frame_rate'] = FRAME_RATE

    # Routes
    app.router.add_get("/", index)
    app.router.add_get("/video", video_feed)
    app.router.add_get("/ws", websocket_handler)

    # Static files
    app.router.add_static("/static", path="./static", name="static")

    # Cleanup handler
    app.on_cleanup.append(cleanup)

    return app


def setup_signal_handlers(loop: asyncio.AbstractEventLoop, shutdown_manager: GracefulShutdown):
    """Setup signal handlers for graceful shutdown."""

    def signal_handler(sig):
        sig_name = signal.Signals(sig).name
        logger.info(f"Received {sig_name}, initiating shutdown...")
        asyncio.create_task(shutdown_manager.shutdown())

    # Handle SIGINT (Ctrl+C) and SIGTERM
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: signal_handler(s))
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            signal.signal(sig, lambda s, f: signal_handler(s))


async def run_server():
    """Run the server with proper lifecycle management."""
    app = await create_application()
    shutdown_manager = app['shutdown_manager']

    runner = web.AppRunner(app, handle_signals=False)
    await runner.setup()

    site = web.TCPSite(runner, HOST, PORT)
    await site.start()

    logger.info(f"Server started at http://{HOST}:{PORT}")
    logger.info("Press Ctrl+C to stop")

    # Setup signal handlers
    loop = asyncio.get_running_loop()
    setup_signal_handlers(loop, shutdown_manager)

    try:
        # Wait for shutdown signal
        await shutdown_manager.shutdown_event.wait()
    finally:
        logger.info("Cleaning up...")

        # Run application cleanup
        await app.shutdown()
        await app.cleanup()

        # Cleanup runner
        await runner.cleanup()

        # Shutdown thread pool
        app['thread_pool'].shutdown(wait=True, cancel_futures=True)

        logger.info("Server stopped")


def main():
    """Entry point."""
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        pass  # Already handled by signal handler
    except Exception as e:
        logger.exception(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
