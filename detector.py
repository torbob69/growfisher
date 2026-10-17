# Shared YOLO detector: one model on the GPU for both the bot and the overlay.
# torch/ultralytics are imported lazily, so region mode runs without them installed.
import os, threading, time
from pathlib import Path
import onnxruntime as ort
import ast
import cv2

# torch's OpenMP threads busy-wait between runs too (measured 36% -> 11% total CPU at 3 fps).
# Read once when torch loads, so it must be set before ultralytics imports it.
os.environ.setdefault("OMP_WAIT_POLICY", "PASSIVE")

import numpy as np

MODEL = Path(__file__).resolve().parent / "runs/detect/runs/detect/growfisher-4/weights/best.onnx"
IMGSZ = 1280

paused = threading.Event()  # set = nobody detects (e.g. while recycling the inventory)
_lock = threading.Lock()
_model = _names = None
last = None 

def preprocessing(frame: np.ndarray):
    h, w = frame.shape[:2]
    r = min(IMGSZ/h, IMGSZ/w)
    
    nw, nh = round(w*r), round(h*r)
    img = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
    
    dw, dh = (IMGSZ-nw)/2, (IMGSZ-nh)/2
    top, bottom = round(dh - 0.1), round(dh + 0.1)
    left, right = round(dw - 0.1), round(dw + 0.1)
    img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))
    
    x = img[..., ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255
    x = np.ascontiguousarray(x)
    
    return x, r, (left, top)

def load(log=print):
    global _model, _names
    with _lock:
        if _model is None:
            if not MODEL.exists():
                raise FileNotFoundError(f"YOLO model not found: {MODEL}")
            options = ort.SessionOptions()
            options.add_session_config_entry('session.intra_op.allow_spinning', "0")
            _model = ort.InferenceSession(str(MODEL), sess_options=options, providers=["CPUExecutionProvider"])
            _names = ast.literal_eval(_model.get_modelmeta().custom_metadata_map["names"])
            log(f"YOLO {MODEL.parent.parent.name} loaded on CPU")
    return _model

def names():
    load()
    return set(_names.values())

def postprocessing(out, r, pad, conf, shape, iou=0.7):
    p = out[0].T                          # (33600, 9): cx, cy, w, h, then one score per class
    cls, s = p[:, 4:].argmax(1), p[:, 4:].max(1)
    keep = s > conf
    xywh, cls, s = p[keep, :4].copy(), cls[keep], s[keep]
    xywh[:, :2] -= xywh[:, 2:] / 2        # centre -> top-left corner, as NMSBoxes wants

    # per-class NMS: shift each class far apart so boxes of different classes never overlap
    # (same 7680 offset ultralytics uses)
    shifted = xywh.copy()
    shifted[:, :2] += cls[:, None] * 7680
    idx = np.array(cv2.dnn.NMSBoxes(shifted.tolist(), s.tolist(), conf, iou), dtype=int).flatten()

    # undo the letterbox: remove padding, scale back, clip to the frame
    left, top = pad
    h, w = shape
    x1 = np.clip((xywh[idx, 0] - left) / r, 0, w)
    y1 = np.clip((xywh[idx, 1] - top) / r, 0, h)
    x2 = np.clip((xywh[idx, 0] + xywh[idx, 2] - left) / r, 0, w)
    y2 = np.clip((xywh[idx, 1] + xywh[idx, 3] - top) / r, 0, h)
    return [(_names[int(c)], float(sc), (float(a), float(b), float(c2), float(d)))
            for c, sc, a, b, c2, d in zip(cls[idx], s[idx], x1, y1, x2, y2)]


def detect(frame:np.ndarray, conf=0.25, publish=True):
    """BGRA/BGR frame -> [(label, conf, (x1, y1, x2, y2)), ...] in frame pixels.
    publish=True stores the result in `last` for the overlay to show."""
    global last
    model = load()
    x, r, pad = preprocessing(frame[..., :3])
    with _lock:
        out = model.run(None, {model.get_inputs()[0].name: x})[0]
    dets = postprocessing(out, r, pad, conf, frame.shape[:2])
    if publish:
        last = (time.time(), frame.shape[:2], dets)
    return dets
