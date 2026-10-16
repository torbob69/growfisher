# Shared YOLO detector: one model on the GPU for both the bot and the overlay.
# torch/ultralytics are imported lazily, so region mode runs without them installed.
import threading, time
from pathlib import Path

import numpy as np

MODEL = Path(__file__).resolve().parent / "runs/detect/runs/detect/growfisher-4/weights/best.onnx"
IMGSZ = 1280

paused = threading.Event()  # set = nobody detects (e.g. while recycling the inventory)
_lock = threading.Lock()    # ultralytics predictors aren't thread-safe; also guards loading
_model = _device = None
last = None  # (time, (frame_h, frame_w), dets) of the latest published detect() (the bot's);
             # the overlay draws from here instead of running inference twice


def load(log=print):
    global _model, _device
    with _lock:
        if _model is None:
            if not MODEL.exists():
                raise FileNotFoundError(f"YOLO model not found: {MODEL}")
            from ultralytics import YOLO
            _model = YOLO(str(MODEL))
            # .onnx runs on CPU onnxruntime. Asking ultralytics for GPU makes it pip-install
            # onnxruntime-gpu over the CPU package RapidOCR has loaded — that broke the venv once.
            _device = "cpu"
            log(f"YOLO {MODEL.parent.parent.name} loaded on {'GPU' if _device == 0 else 'CPU'}")
    return _model


def names():
    return set(load().names.values())


def detect(frame, conf=0.25, publish=True):
    """BGRA/BGR frame -> [(label, conf, (x1, y1, x2, y2)), ...] in frame pixels.
    publish=True stores the result in `last` for the overlay to show."""
    global last
    model = load()
    with _lock:
        r = model.predict(np.ascontiguousarray(frame[..., :3]), imgsz=IMGSZ, conf=conf,
                          device=_device, verbose=False)[0]
    dets = [(r.names[int(c)], s, tuple(b)) for b, s, c in
            zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist())]
    if publish:
        last = (time.time(), frame.shape[:2], dets)
    return dets
