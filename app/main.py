from fastapi import FastAPI, HTTPException
from app.models import GenerateRequest, GenerateResponse
from app.queue_manager import queue_manager
from app.logger import logger
import uuid

app = FastAPI(title="Local ChatGPT API", version="1.0.0")

@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest):
    request_id = str(uuid.uuid4())
    logger.info("Received request", extra={"request_id": request_id, "prompt_hash": hash(request.prompt)})
    
    return await queue_manager.enqueue(request, request_id)
    
@app.get("/health")
async def health():
    return {"status": "ok", "active_workers": queue_manager.active_workers, "queue_size": queue_manager.queue.qsize()}
