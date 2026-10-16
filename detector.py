# Shared YOLO detector: one model on the GPU for both the bot and the overlay.
# torch/ultralytics are imported lazily, so region mode runs without them installed.
import os, threading, time
from pathlib import Path

# torch's OpenMP threads busy-wait between runs too (measured 36% -> 11% total CPU at 3 fps).
# Read once when torch loads, so it must be set before ultralytics imports it.
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")

import numpy as np

MODEL = Path(__file__).resolve().parent / "runs/detect/runs/detect/growfisher-4/weights/best.onnx"
IMGSZ = 1280

paused = threading.Event()  # set = nobody detects (e.g. while recycling the inventory)
_lock = threading.Lock()    # ultralytics predictors aren't thread-safe; also guards loading
_model = _device = None
last = None  # (time, (frame_h, frame_w), dets) of the latest published detect() (the bot's);
             # the overlay draws from here instead of running inference twice


def _no_spin():
    # onnxruntime's worker threads busy-wait between runs by default: measured 57% total CPU at
    # 3 fps vs 11% with spinning off, and lowering the fps made it worse, not better.
    # ponytail: ultralytics gives no way to pass SessionOptions, so wrap the constructor
    import onnxruntime as ort
    if getattr(ort.InferenceSession, "_no_spin", False): return
    Session = ort.InferenceSession
    def session(path, opts=None, *a, **kw):
        opts = opts or ort.SessionOptions()
        opts.add_session_config_entry("session.intra_op.allow_spinning", "0")
        return Session(path, opts, *a, **kw)
    session._no_spin = True
    ort.InferenceSession = session


def load(log=print):
    global _model, _device
    with _lock:
        if _model is None:
            if not MODEL.exists():
                raise FileNotFoundError(f"YOLO model not found: {MODEL}")
            _no_spin()
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
