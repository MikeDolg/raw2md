from pydantic import BaseModel


class OCRErrorDetectionResult(BaseModel):
    texts: list[str]
    labels: list[str]
