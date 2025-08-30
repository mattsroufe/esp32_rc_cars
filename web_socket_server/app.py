import asyncio
import os
from server import create_app
from aiohttp import web

async def main():
    # Create the aiohttp application
    app = create_app()

    # Set host and port from environment variables
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))

    # Setup runner and site
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    print(f"Server running at http://{host}:{port}")
    
    # Run until Ctrl+C
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("Ctrl+C received, shutting down...")
    finally:
        # Clean up
        await runner.cleanup()
        # Shutdown thread pool
        thread_pool = app.get("thread_pool")
        if thread_pool:
            thread_pool.shutdown(wait=False)
        print("Shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except asyncio.CancelledError:
        # Prevent CancelledError from leaking on shutdown
        pass
