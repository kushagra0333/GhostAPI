from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class TaskStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class FailureReason(str, Enum):
    SUCCESS_FULL = "SUCCESS_FULL"
    SUCCESS_PARTIAL = "SUCCESS_PARTIAL"
    FAIL_TIMEOUT = "FAIL_TIMEOUT"
    FAIL_CAPTCHA = "FAIL_CAPTCHA"
    FAIL_UI_CHANGE = "FAIL_UI_CHANGE"
    FAIL_UNKNOWN = "FAIL_UNKNOWN"

class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="The prompt to send to ChatGPT")

class GenerateResponse(BaseModel):
    request_id: str
    status: TaskStatus
    output_text: Optional[str] = None
    failure_reason: Optional[FailureReason] = None
    latency_ms: Optional[int] = None
