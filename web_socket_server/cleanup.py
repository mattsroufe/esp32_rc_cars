import asyncio
import logging

async def cleanup(app):
    """
    Clean up resources when the server shuts down.
    Cancels all running tasks and shuts down the thread pool.
    """
    logging.info("Cleaning up resources...")

    current_task = asyncio.current_task()
    tasks = [t for t in asyncio.all_tasks() if t is not current_task]

    if tasks:
        logging.info(f"Cancelling {len(tasks)} running tasks...")
        for task in tasks:
            task.cancel()

        # Wait for all tasks to finish/cancel
        await asyncio.gather(*tasks, return_exceptions=True)

    # Shutdown thread pool
    thread_pool = app.get('thread_pool')
    if thread_pool:
        logging.info("Shutting down thread pool...")
        thread_pool.shutdown(wait=False, cancel_futures=True)

    logging.info("Cleanup complete.")
