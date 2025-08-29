import logging
import asyncio

async def cleanup(app):
    logging.info("Shutting down resources...")
    app['shutdown_event'].set()

    # Cancel background tasks
    for task in asyncio.all_tasks():
        if task is not asyncio.current_task():
            task.cancel()

    app['thread_pool'].shutdown(wait=False, cancel_futures=True)
    logging.info("Cleanup finished.")
