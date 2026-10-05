# Pre-labels unlabeled dataset/raw images with the trained model, for review in X-AnyLabeling.
#   python autolabel.py                         -> label new images into dataset/autolabel/
#   python autolabel.py mark-reviewed <folder>  -> add every image in <folder> to reviewed.txt
# Only images listed in dataset/autolabel/reviewed.txt are used by prepare_dataset.py.
import json, shutil, sys
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------- CONFIG ----
HERE = Path(__file__).resolve().parent
MODEL = HERE.parent / "runs/detect/runs/detect/growfisher/weights/best.pt"
RAW = HERE.parent / "dataset/raw"
AUTO = HERE.parent / "dataset/autolabel"
IMGSZ = 1280
CONF = 0.25        # low on purpose: a wrong box is quicker to delete than a missing one to draw
BATCH = 8
RISKY_CONF = 0.5   # boxes below this get the image flagged for review
OVERLAP_IOU = 0.3  # different-class boxes overlapping this much get flagged
MUST_HAVE_BOX = {"splash", "nothing", "emptier", "caught"}
# ------------------------------------------------------------------------------

REVIEWED = AUTO / "reviewed.txt"
IMG_EXT = (".jpg", ".jpeg", ".png")


def has_json(img):
    return img.with_suffix(".json").exists()


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / union if union > 0 else 0.0


def read_reviewed():
    if not REVIEWED.exists():
        return set()
    return {l.strip().replace("\\", "/") for l in REVIEWED.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")}


def risk(js):
    """-> (reasons, min_conf) for one autolabel JSON (reads the current file, so edits count)."""
    d = json.loads(js.read_text(encoding="utf-8"))
    boxes, reasons, min_conf = [], [], 1.0
    for s in d.get("shapes") or []:
        xs, ys = [p[0] for p in s["points"]], [p[1] for p in s["points"]]
        desc = s.get("description") or ""
        # no "conf=" means you drew or edited it yourself -> trusted
        conf = float(desc[5:]) if desc.startswith("conf=") else 1.0
        min_conf = min(min_conf, conf)
        boxes.append((s["label"], conf, (min(xs), min(ys), max(xs), max(ys))))
    low = [f"{l} {c:.2f}" for l, c, _ in boxes if c < RISKY_CONF]
    if low:
        reasons.append("low conf: " + ", ".join(low))
    for i, (la, _, ba) in enumerate(boxes):
        for lb, _, bb in boxes[i+1:]:
            if la != lb and iou(ba, bb) > OVERLAP_IOU:
                reasons.append(f"overlap: {la} vs {lb}")
    if not boxes and js.parent.name in MUST_HAVE_BOX:
        reasons.append(f"no boxes in a {js.parent.name}/ image")
    return reasons, min_conf


def write_review_order():
    reviewed = read_reviewed()
    rows = []
    for js in AUTO.glob("*/*/*.json"):
        rel = next((js.with_suffix(e) for e in IMG_EXT if js.with_suffix(e).exists()), None)
        if rel is None:
            continue
        rel = rel.relative_to(AUTO).as_posix()
        if rel in reviewed:
            continue
        try:
            reasons, min_conf = risk(js)
        except Exception as e:
            reasons, min_conf = [f"unreadable JSON ({e})"], 0.0
        rows.append((-len(reasons), min_conf, rel, "; ".join(reasons) or f"ok (min conf {min_conf:.2f})"))
    rows.sort()
    (AUTO / "review_order.txt").write_text(
        "# not-yet-reviewed images, most doubtful first\n"
        + "".join(f"{rel}\t{why}\n" for _, _, rel, why in rows), encoding="utf-8")
    return sum(1 for r in rows if r[0] < 0), len(rows)


def autolabel():
    if not MODEL.exists():
        raise SystemExit(f"Model not found: {MODEL}\nTrain first, or fix MODEL at the top of autolabel.py")
    todo = []
    for img in sorted(p for p in RAW.glob("*/*/*") if p.suffix.lower() in IMG_EXT):
        if has_json(img):
            continue  # labeled by hand
        dst = AUTO / img.relative_to(RAW)
        if has_json(dst):
            continue  # already auto-labeled (maybe reviewed) — never overwrite
        todo.append((img, dst))
    print(f"{len(todo)} unlabeled images to process")

    boxes, empty = Counter(), 0
    if todo:
        import torch
        from ultralytics import YOLO
        model = YOLO(str(MODEL))
        device = 0 if torch.cuda.is_available() else "cpu"
        print(f"device: {torch.cuda.get_device_name(0) if device == 0 else 'CPU (slow)'}")
        dst_of = {img.resolve(): dst for img, dst in todo}
        paths = [str(i) for i, _ in todo]
        # chunk by hand: given a list, Ultralytics put every image into one GPU batch (21 GB OOM)
        results = (r for k in range(0, len(paths), BATCH)
                   for r in model.predict(paths[k:k + BATCH], imgsz=IMGSZ, conf=CONF,
                                          device=device, verbose=False))
        for n, r in enumerate(results, 1):
            src = Path(r.path).resolve()
            dst = dst_of[src]
            h, w = r.orig_shape
            shapes = []
            for (x1, y1, x2, y2), c, k in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(),
                                              r.boxes.cls.tolist()):
                label = r.names[int(k)]
                boxes[label] += 1
                shapes.append({"label": label,
                               "points": [[round(x1, 2), round(y1, 2)], [round(x2, 2), round(y2, 2)]],
                               "group_id": None, "shape_type": "rectangle", "flags": {},
                               "description": f"conf={c:.2f}"})
            empty += not shapes
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)  # copy only; dataset/raw is never written
            dst.with_suffix(".json").write_text(json.dumps(
                {"version": "4.1.0", "flags": {}, "shapes": shapes, "imagePath": dst.name,
                 "imageData": None, "imageHeight": h, "imageWidth": w}, indent=2), encoding="utf-8")
            if n % 100 == 0:
                print(f"  {n}/{len(todo)}")

    AUTO.mkdir(parents=True, exist_ok=True)
    flagged, pending = write_review_order()
    print(f"\nimages processed:       {len(todo)}")
    for label, n in boxes.most_common():
        print(f"  {label:<16}{n} boxes")
    print(f"images with no boxes:   {empty}")
    print(f"flagged for review:     {flagged} of {pending} unreviewed  -> {AUTO / 'review_order.txt'}")


def mark_reviewed(folder):
    folder = Path(folder).resolve()
    try:
        folder.relative_to(AUTO)
    except ValueError:
        raise SystemExit(f"{folder} is not inside {AUTO}")
    have = read_reviewed()
    new = [p.relative_to(AUTO).as_posix() for p in sorted(folder.rglob("*"))
           if p.suffix.lower() in IMG_EXT and has_json(p)]
    new = [r for r in new if r not in have]
    AUTO.mkdir(parents=True, exist_ok=True)
    with open(REVIEWED, "a", encoding="utf-8") as f:
        f.writelines(r + "\n" for r in new)
    print(f"added {len(new)} images to {REVIEWED} ({len(have) + len(new)} reviewed total)")
    write_review_order()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "mark-reviewed":
        mark_reviewed(sys.argv[2])
    elif len(sys.argv) == 1:
        autolabel()
    else:
        raise SystemExit("usage: python autolabel.py  |  python autolabel.py mark-reviewed <folder>")
