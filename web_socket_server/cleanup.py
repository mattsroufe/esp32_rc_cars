import asyncio
import logging

async def cleanup(app):
    """
    Clean up resources when the server shuts down.
    Cancels background tasks and shuts down the thread pool.
    """
    logging.info("Cleaning up resources...")

    # Cancel all running tasks except the current one
    current_task = asyncio.current_task()
    for task in asyncio.all_tasks():
        if task is not current_task:
            task.cancel()

    # Wait briefly for tasks to cancel
    await asyncio.sleep(0.1)

    # Shutdown thread pool
    thread_pool = app.get('thread_pool')
    if thread_pool:
        logging.info("Shutting down thread pool...")
        thread_pool.shutdown(wait=False, cancel_futures=True)

    logging.info("Cleanup complete.")
