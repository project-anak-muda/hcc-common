from __future__ import annotations

import socket
from functools import lru_cache
from typing import Literal, Optional
from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class _Base(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

class DatabaseSettings(_Base):
    """PostgreSQL / TimescaleDB connection."""
    host: str = Field("postgres", alias="POSTGRES_HOST")
    port: int = Field(5432, alias="POSTGRES_PORT")
    db: str = Field("hcc", alias="POSTGRES_DB")
    user: str = Field("hcc", alias="POSTGRES_USER")
    password: str = Field("hcc", alias="POSTGRES_PASSWORD")
    url_override: Optional[str] = Field(None, alias="DATABASE_URL")
    retention_days: int = Field(7, alias="DETECTION_RETENTION_DAYS")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def url(self) -> str:
        if self.url_override:
            return self.url_override
        return (
            f"postgresql+psycopg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.db}"
        )

class StorageSettings(_Base):
    """MinIO / S3-compatible object storage."""
    endpoint: Optional[str] = Field("http://minio:9000", alias="S3_ENDPOINT")
    region: str = Field("us-east-1", alias="S3_REGION")
    access_key: str = Field("hcc-minio", alias="S3_ACCESS_KEY")
    secret_key: str = Field("hcc-minio-secret", alias="S3_SECRET_KEY")
    use_ssl: bool = Field(False, alias="S3_USE_SSL")

    bucket_raw: str = Field("raw-frames", alias="S3_BUCKET_RAW")
    bucket_events: str = Field("events", alias="S3_BUCKET_EVENTS")
    bucket_datasets: str = Field("datasets", alias="S3_BUCKET_DATASETS")
    bucket_models: str = Field("models", alias="S3_BUCKET_MODELS")
    bucket_sample_videos: str = Field("sample-videos", alias="S3_BUCKET_SAMPLE_VIDEOS")
    raw_retention_days: int = Field(7, alias="RAW_RETENTION_DAYS")

class BusSettings(_Base):
    """Redis event bus / work queue / camera-shard coordination."""
    url: str = Field("redis://redis:6379/0", alias="REDIS_URL")
    review_queue: str = Field("hcc:review:queue", alias="REVIEW_QUEUE")
    train_queue: str = Field("hcc:train:queue", alias="TRAIN_QUEUE")

class DetectorSettings(_Base):
    go2rtc_api: str = Field("http://go2rtc:1984", alias="GO2RTC_API")
    device: Literal["auto", "cuda", "cpu"] = Field("auto", alias="DETECTOR_DEVICE")
    conf_threshold: float = Field(0.25, alias="DETECTOR_CONF_THRESHOLD")
    iou_dedup: float = Field(0.8, alias="DETECTOR_IOU_DEDUP")
    heartbeat_interval_seconds: int = Field(30, alias="HEARTBEAT_INTERVAL_SECONDS")
    # Event-log policy: detections are debounced into one row per object
    # *occurrence*. A raw frame is saved once when an event opens; an hourly
    # snapshot is saved for background audit. No annotated images are stored
    # (regenerated on demand from raw frame + bbox).
    snapshot_interval_seconds: int = Field(3600, alias="SNAPSHOT_INTERVAL_SECONDS")
    event_gap_seconds: float = Field(10.0, alias="EVENT_GAP_SECONDS")   # missing this long → event closes
    event_assoc_iou: float = Field(0.2, alias="EVENT_ASSOC_IOU")        # same-event spatial match
    # Cap inference at N frames/sec per camera so many cameras sharing one GPU
    # cannot oversubscribe it. Frames between are still decoded (stream stays
    # fresh) but skipped for prediction. Raise for lower-latency, fewer cameras.
    infer_fps: float = Field(5.0, alias="DETECTOR_INFER_FPS")
    # TensorRT acceleration. On CUDA, a .pt model is auto-exported to a .engine
    # (cached back to object storage) and loaded as the engine. On CPU (no GPU /
    # no TensorRT) this is skipped and the .pt is used directly.
    use_tensorrt: bool = Field(True, alias="DETECTOR_USE_TENSORRT")
    trt_half: bool = Field(True, alias="DETECTOR_TRT_HALF")          # FP16 engine
    imgsz: int = Field(640, alias="DETECTOR_IMGSZ")                  # engine input size
    # Unique per replica so Redis camera-leases don't collide. Defaults to the
    # container hostname (Docker makes it unique per `--scale` replica); the env
    # var overrides it when set explicitly.
    worker_id: str = Field(default_factory=socket.gethostname, alias="DETECTOR_WORKER_ID")

class ReviewerSettings(_Base):
    ollama_url: str = Field("http://ollama:11434", alias="OLLAMA_URL")
    vision_model: str = Field("moondream:latest", alias="REVIEWER_VISION_MODEL")
    reasoning_model: str = Field("gemma2:2b", alias="REVIEWER_REASONING_MODEL")
    maxchat_token: Optional[str] = Field(None, alias="MAXCHAT_TOKEN")
    maxchat_target: Optional[str] = Field(None, alias="MAXCHAT_TARGET_NUMBER")
    maxchat_url_send: Optional[str] = Field(None, alias="MAXCHAT_API_URL_SEND")
    maxchat_url_image: Optional[str] = Field(None, alias="MAXCHAT_API_URL_IMAGE")
    notification_cooldown_seconds: int = Field(3600, alias="NOTIFICATION_COOLDOWN_SECONDS")

class TrainerSettings(_Base):
    auto_train_threshold: int = Field(100, alias="AUTO_TRAIN_THRESHOLD")
    epochs: int = Field(100, alias="TRAIN_EPOCHS")
    device: str = Field("auto", alias="TRAIN_DEVICE")
    eval_map50_threshold: float = Field(0.5, alias="EVAL_MAP50_THRESHOLD")
    eval_sample_video_seconds: int = Field(15, alias="EVAL_SAMPLE_VIDEO_SECONDS")

class Settings(_Base):
    """Top-level settings aggregating every section."""
    env: Literal["dev", "staging", "prod"] = Field("dev", alias="HCC_ENV")
    tz: str = Field("Asia/Jakarta", alias="TZ")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    # Namespaced aliases (HCC_CFG_*) so the generic field names db/storage/bus/...
    # can't be hijacked by a stray same-named shell env var (e.g. `STORAGE`),
    # which pydantic-settings would otherwise try to JSON-parse as the model.
    # Each sub-config still self-loads its own real vars (POSTGRES_*, S3_*, ...).
    db: DatabaseSettings = Field(default_factory=DatabaseSettings, alias="HCC_CFG_DB")
    storage: StorageSettings = Field(default_factory=StorageSettings, alias="HCC_CFG_STORAGE")
    bus: BusSettings = Field(default_factory=BusSettings, alias="HCC_CFG_BUS")
    detector: DetectorSettings = Field(default_factory=DetectorSettings, alias="HCC_CFG_DETECTOR")
    reviewer: ReviewerSettings = Field(default_factory=ReviewerSettings, alias="HCC_CFG_REVIEWER")
    trainer: TrainerSettings = Field(default_factory=TrainerSettings, alias="HCC_CFG_TRAINER")

@lru_cache
def get_settings() -> Settings:
    """Cached singleton accessor — import and call from any service."""
    return Settings()