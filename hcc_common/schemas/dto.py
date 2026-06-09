from __future__ import annotations

import datetime as dt
from typing import Optional
from pydantic import BaseModel, Field


class DetectionEvent(BaseModel):
    detection_id: int
    detection_time: dt.datetime
    camera_id: str
    camera_name: str
    model_id: Optional[str] = None
    label: str
    confidence: float
    bbox: Optional[list[int]] = None
    raw_image_key: Optional[str] = None
    annotated_image_key: Optional[str] = None
    extra: dict = Field(default_factory=dict)

class ReviewJob(BaseModel):
    event: DetectionEvent

class TrainJob(BaseModel):
    model_name: str
    base_model_key: Optional[str] = None
    epochs: Optional[int] = None
    triggered_by: str = "auto"          # auto | manual
    run_id: Optional[str] = None

class EvalMetrics(BaseModel):
    map50: float = 0.0
    map50_95: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    fitness: float = 0.0
    num_val_images: int = 0
    per_class: dict = Field(default_factory=dict)

    def passes(self, map50_threshold: float) -> bool:
        return self.map50 >= map50_threshold