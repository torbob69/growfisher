# Runs a trained model on every dataset/raw image and saves copies with the boxes drawn on.
#   python infer_all.py [path\to\best.pt]
# Output: runs/infer/<run name>/<session>/<event>/*.jpg  (dataset/raw is only read)
import sys
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import torch
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
MODEL = HERE.parent / "runs/detect/runs/detect/growfisher-2/weights/best.pt"
RAW = HERE.parent / "dataset/raw"
IMGSZ, CONF, BATCH = 1280, 0.25, 8
OUT_WIDTH = 1280  # saved previews are downscaled to this width to keep the folder small


def main():
    model_path = Path(sys.argv[1]) if len(sys.argv) > 1 else MODEL
    if not model_path.exists():
        raise SystemExit(f"Model not found: {model_path}")
    out = HERE / "runs/infer" / model_path.parent.parent.name
    paths = sorted(str(p) for p in RAW.glob("*/*/*.jpg"))
    model = YOLO(str(model_path))
    device = 0 if torch.cuda.is_available() else "cpu"
    print(f"{len(paths)} images, model {model_path}, output {out}")

    per_event = defaultdict(Counter)  # event -> {"images", "empty", <class>: images with it}
    boxes = Counter()
    for k in range(0, len(paths), BATCH):  # chunked: a list in one predict() = one giant batch
        for r in model.predict(paths[k:k + BATCH], imgsz=IMGSZ, conf=CONF, device=device, verbose=False):
            src = Path(r.path)
            event = src.parent.name
            names = [r.names[int(c)] for c in r.boxes.cls.tolist()]
            boxes.update(names)
            per_event[event]["images"] += 1
            per_event[event]["empty"] += not names
            per_event[event].update(set(names))

            img = r.plot(line_width=2, font_size=14)
            h, w = img.shape[:2]
            if w > OUT_WIDTH:
                img = cv2.resize(img, (OUT_WIDTH, round(h * OUT_WIDTH / w)), interpolation=cv2.INTER_AREA)
            dst = out / src.relative_to(RAW)
            dst.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(dst), img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        done = min(k + BATCH, len(paths))
        if done % 200 < BATCH or done == len(paths):
            print(f"  {done}/{len(paths)}")

    classes = list(model.names.values())
    print(f"\nboxes found: " + ", ".join(f"{c} {boxes[c]}" for c in classes))
    print(f"\nimages containing each class, per event folder:")
    print(f"{'event':<10}{'images':>7}{'none':>6}" + "".join(f"{c[:14]:>16}" for c in classes))
    for ev, c in sorted(per_event.items()):
        print(f"{ev:<10}{c['images']:>7}{c['empty']:>6}" + "".join(f"{c[n]:>16}" for n in classes))
    print(f"\nOpen: {out}")


if __name__ == "__main__":
    main()
