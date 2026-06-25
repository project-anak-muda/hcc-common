from __future__ import annotations

import enum
import uuid
from datetime import datetime

from typing import Optional
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import (
    BigInteger, Boolean, Float, ForeignKey, Identity,
    Index, Integer, String, Text, UniqueConstraint,
)

from hcc_common.db import Base, ts_column, now_jakarta


class ModelStatus(str, enum.Enum):
    draft = "draft"
    training = "training"
    evaluating = "evaluating"
    candidate = "candidate"   # trained + passed eval; awaiting human promotion to `ready`
    ready = "ready"
    failed = "failed"
    archived = "archived"

class ReviewStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    rejected = "rejected"
    skipped = "skipped"
    error = "error"

class TrainingStatus(str, enum.Enum):
    queued = "queued"
    collecting = "collecting"
    training = "training"
    evaluating = "evaluating"
    pending_review = "pending_review"   # candidate produced; awaiting human promote/reject
    success = "success"
    failed = "failed"
    cancelled = "cancelled"

class Camera(Base):
    __tablename__ = "cameras"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    group_name: Mapped[Optional[str]] = mapped_column(String(128), index=True)
    # go2rtc stream key / source identifier
    stream_key: Mapped[str] = mapped_column(String(256))
    # Area-of-interest polygons + per-camera detection rules (schedules, classes…)
    aoi: Mapped[dict] = mapped_column(JSONB, default=dict)
    rules: Mapped[dict] = mapped_column(JSONB, default=dict)
    whatsapp_targets: Mapped[list] = mapped_column(JSONB, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = ts_column(default=now_jakarta)
    updated_at: Mapped[datetime] = ts_column(default=now_jakarta, onupdate=now_jakarta)

class Model(Base):
    __tablename__ = "models"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    # object-storage key of the deployable artifact (.engine/.onnx/.pt)
    artifact_key: Mapped[Optional[str]] = mapped_column(String(512))
    status: Mapped[ModelStatus] = mapped_column(
        String(16), default=ModelStatus.draft, index=True
    )
    # evaluation metrics that gated promotion to 'ready'
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    classes: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = ts_column(default=now_jakarta)
    promoted_at: Mapped[Optional[datetime]] = ts_column(nullable=True)
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_models_name_version"),
    )

class CameraModel(Base):
    """Which model (exact version) a camera runs. One assignment per camera;
    a camera with no row here is not processed by the detector."""
    __tablename__ = "camera_models"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cameras.id", ondelete="CASCADE"), unique=True, index=True
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("models.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = ts_column(default=now_jakarta)
    updated_at: Mapped[datetime] = ts_column(default=now_jakarta, onupdate=now_jakarta)

class Detection(Base):
    __tablename__ = "detections"

    # Composite PK (id, time): TimescaleDB requires the partition column in the PK.
    # id is server-generated (IDENTITY) so inserts don't supply it.
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    time: Mapped[datetime] = ts_column(primary_key=True, default=now_jakarta)
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    model_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)
    camera_name: Mapped[str] = mapped_column(String(128), index=True)
    label: Mapped[str] = mapped_column(String(128), index=True)
    confidence: Mapped[float] = mapped_column(Float)   # peak confidence over the occurrence
    bbox: Mapped[Optional[list]] = mapped_column(JSONB)   # normalized YOLO [cx,cy,w,h] in 0..1
    # source frame size (pixels) the bbox was normalized against — lets any
    # consumer reconstruct pixel coords without decoding the image.
    frame_width: Mapped[Optional[int]] = mapped_column(Integer)
    frame_height: Mapped[Optional[int]] = mapped_column(Integer)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)  # reserved (unused)
    # event-log fields: one row per object occurrence (debounced). `time` is
    # first-seen; `last_seen` is set when the event closes (duration = last_seen-time).
    last_seen: Mapped[Optional[datetime]] = ts_column(nullable=True)
    frame_count: Mapped[int] = mapped_column(Integer, default=1)     # frames the object was seen
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)         # pose groups, aoi matches…
    # object-storage references (images live in MinIO, not the DB)
    raw_image_key: Mapped[Optional[str]] = mapped_column(String(512))
    annotated_image_key: Mapped[Optional[str]] = mapped_column(String(512))
    review_status: Mapped[ReviewStatus] = mapped_column(
        String(16), default=ReviewStatus.pending, index=True
    )
    review_verdict: Mapped[Optional[str]] = mapped_column(Text)
    reviewed_at: Mapped[Optional[datetime]] = ts_column(nullable=True)
    # The hypertable conversion (create_hypertable) is done in the Alembic migration.
    __table_args__ = (
        Index("ix_detections_camera_time", "camera_id", "time"),
    )

class CameraHeartbeat(Base):
    __tablename__ = "camera_heartbeats"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    time: Mapped[datetime] = ts_column(primary_key=True, default=now_jakarta)
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    camera_name: Mapped[str] = mapped_column(String(128), index=True)
    worker_id: Mapped[str] = mapped_column(String(64))
    fps: Mapped[float] = mapped_column(Float, default=0.0)
    frame_count: Mapped[int] = mapped_column(BigInteger, default=0)
    detection_count: Mapped[int] = mapped_column(Integer, default=0)
    online: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("ix_heartbeats_camera_time", "camera_id", "time"),
    )

class Correction(Base):
    __tablename__ = "corrections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_name: Mapped[str] = mapped_column(String(128), index=True)
    camera_name: Mapped[Optional[str]] = mapped_column(String(128))
    # dataset object-storage keys (image + YOLO label txt)
    image_key: Mapped[str] = mapped_column(String(512))
    label_key: Mapped[str] = mapped_column(String(512))
    annotations: Mapped[list] = mapped_column(JSONB, default=list)
    source: Mapped[str] = mapped_column(String(32), default="human")  # human | auto
    consumed_by_run: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = ts_column(default=now_jakarta, index=True)

class TrainingRun(Base):
    __tablename__ = "training_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    model_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("models.id"), index=True, nullable=True
    )
    model_name: Mapped[str] = mapped_column(String(128), index=True)
    base_model_key: Mapped[Optional[str]] = mapped_column(String(512))
    status: Mapped[TrainingStatus] = mapped_column(
        String(16), default=TrainingStatus.queued, index=True
    )
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[Optional[str]] = mapped_column(Text)

    dataset_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)  # image count, classes, split
    # populated by the evaluation step
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)           # mAP50, mAP50-95, P, R…
    sample_video_key: Mapped[Optional[str]] = mapped_column(String(512))
    log: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = ts_column(default=now_jakarta, index=True)
    started_at: Mapped[Optional[datetime]] = ts_column(nullable=True)
    finished_at: Mapped[Optional[datetime]] = ts_column(nullable=True)

    model = relationship("Model")

class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_name: Mapped[str] = mapped_column(String(128), index=True)
    detection_time: Mapped[Optional[datetime]] = ts_column(nullable=True)
    channel: Mapped[str] = mapped_column(String(32), default="whatsapp")
    target: Mapped[Optional[str]] = mapped_column(String(128))
    image_key: Mapped[Optional[str]] = mapped_column(String(512))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(32), default="sent")  # sent | failed
    created_at: Mapped[datetime] = ts_column(default=now_jakarta, index=True)