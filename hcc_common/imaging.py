"""Image helpers shared across services.

`draw_boxes`/`encode_jpeg` are used by the detector; `regenerate_annotated` lets
the reviewer (and the regen CLI) rebuild a boxed image from a stored raw frame +
the detection bbox(es) on demand — so annotated images never need to be stored.

cv2/numpy are imported lazily so installing hcc_common doesn't force OpenCV on
services that don't do imaging (only the detector/trainer/reviewer need it).
"""
from __future__ import annotations

from typing import Optional


def encode_jpeg(frame, quality: int = 80) -> Optional[bytes]:
    import cv2

    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    return buf.tobytes() if ok else None


def decode_jpeg(data: bytes):
    import cv2
    import numpy as np

    arr = np.frombuffer(data, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def draw_boxes(frame, boxes: list[dict]):
    """Annotate a copy of the frame with labelled boxes."""
    import cv2

    out = frame.copy()
    for b in boxes:
        x1, y1, x2, y2 = (int(v) for v in b["bbox"])
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        conf = b.get("confidence")
        text = f"{b['label']} {conf:.2f}" if conf is not None else str(b["label"])
        cv2.putText(out, text, (x1, max(0, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    return out


def regenerate_annotated(raw_bytes: bytes, boxes: list[dict], quality: int = 80) -> Optional[bytes]:
    """Rebuild a boxed JPEG from a raw frame's bytes + bbox list. Returns None
    if the raw frame can't be decoded."""
    frame = decode_jpeg(raw_bytes)
    if frame is None:
        return None
    return encode_jpeg(draw_boxes(frame, boxes), quality)
