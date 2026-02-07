import asyncio
from app.models import GenerateRequest, GenerateResponse, TaskStatus, FailureReason
from app.logger import logger
from app.config import config
from app.browser_service import BrowserService

class QueueManager:
    def __init__(self, max_concurrent: int = config.MAX_CONCURRENT_BROWSERS):
        self.queue = asyncio.Queue()
        self.max_concurrent = max_concurrent
        self.active_workers = 0
        self.lock = asyncio.Lock()

    async def enqueue(self, request: GenerateRequest, request_id: str) -> GenerateResponse:
        logger.info(f"Enqueuing request {request_id}", extra={"request_id": request_id})
        
        # Create a future to wait for the result
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        
        await self.queue.put((request, request_id, future))
        
        # Attempt to start a worker if we are under capacity
        async with self.lock:
            if self.active_workers < self.max_concurrent:
                asyncio.create_task(self._worker_loop())
                self.active_workers += 1
                logger.info("Started new worker", extra={"worker_count": self.active_workers})

        # Wait for the result
        return await future

    async def _worker_loop(self):
        logger.info("Worker loop started")
        while True:
            try:
                request, request_id, future = await self.queue.get()
                
                logger.info(f"Processing request {request_id}", extra={"request_id": request_id})
                
                service = BrowserService(request_id)
                try:
                    result = await service.process_request(request)
                    future.set_result(result)
                except Exception as e:
                    logger.error(f"Worker unhandled exception processing {request_id}: {e}")
                    # Ensure future is set even on crash
                    if not future.done():
                        future.set_result(GenerateResponse(
                            request_id=request_id,
                            status=TaskStatus.FAILED,
                            failure_reason=FailureReason.FAIL_UNKNOWN,
                            output_text=str(e),
                            latency_ms=0
                        ))

                self.queue.task_done()
                
            except Exception as e:
                logger.error(f"Worker loop exception: {e}")
            
            # Check if we should exit 
            # We strictly exit if queue is empty to respect resource usage, 
            # but we need to be careful about race conditions with enqueue.
            # actually, if we want to keep workers around for a bit we could, but let's be strict for now.
            
            if self.queue.empty():
                 async with self.lock:
                    if self.queue.empty():
                        self.active_workers -= 1
                        logger.info("Worker loop stopping (queue empty)", extra={"worker_count": self.active_workers})
                        return

queue_manager = QueueManager(config.MAX_CONCURRENT_BROWSERS if 'config' in globals() else 2) # dependency injection later
