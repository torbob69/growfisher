# Pre-labels every dataset/raw image with the trained model, for review in X-AnyLabeling.
#   python autolabel.py   -> new images get a hardlink + .json in dataset/autolabel/<session>/<event>/
# Review a recording session in X-AnyLabeling, then rename its SESSION folder to
# <world>-<session>[-far]-done (e.g. empangpeleh21-20261003_142718-done). Sessions are matched by
# their recording time, so renaming is safe. prepare_dataset.py trains ONLY on -done sessions.
import json, os, re, shutil
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------- CONFIG ----
HERE = Path(__file__).resolve().parent
MODEL = HERE.parent / "runs/detect/runs/detect/growfisher-3/weights/best.pt"
RAW = HERE.parent / "dataset/raw"
AUTO = HERE.parent / "dataset/autolabel"
IMGSZ = 1280
CONF = 0.25        # low on purpose: a wrong box is quicker to delete than a missing one to draw
BATCH = 8
RISKY_CONF = 0.5   # boxes below this get the image flagged for review
OVERLAP_IOU = 0.3  # different-class boxes overlapping this much get flagged
MUST_HAVE_BOX = {"splash", "nothing", "emptier", "caught"}
DONE = "-done"     # session folder suffix that marks "reviewed"
# ------------------------------------------------------------------------------

IMG_EXT = (".jpg", ".jpeg", ".png")


def is_done(js):
    """True if this autolabel .json sits in a session folder renamed to ...-done."""
    return js.parent.parent.name.endswith(DONE)


STAMP = re.compile(r"\d{8}_\d{6}")  # recording time = the session's identity


def session_folders():
    """recording time -> its folder name in autolabel, whatever you renamed it to."""
    out = {}
    for d in sorted(AUTO.iterdir()) if AUTO.is_dir() else ():
        m = STAMP.search(d.name)
        if not (d.is_dir() and m):
            continue
        prev = out.get(m.group())
        if prev:
            print(f"  WARNING: two folders for session {m.group()}: {prev} and {d.name}")
            if prev.endswith(DONE):
                continue  # a reviewed folder always wins
        out[m.group()] = d.name
    return out


def find_todo():
    """-> [(raw image, autolabel destination)] for images that still need a label. A -done
    session is finished: never add to it or recreate it, even if you deleted images from it."""
    folders = session_folders()
    todo = []
    for img in sorted(p for p in RAW.glob("*/*/*") if p.suffix.lower() in IMG_EXT):
        sess, ev, name = img.relative_to(RAW).parts
        m = STAMP.search(sess)
        folder = folders.get(m.group() if m else sess, sess)
        if folder.endswith(DONE):
            continue
        dst = AUTO / folder / ev / name
        if not dst.with_suffix(".json").exists():
            todo.append((img, dst))
    return todo


def link_or_copy(src, dst):
    # hardlink = same file on disk under a second name: no extra space, and dataset/raw is
    # never written (X-AnyLabeling only writes the .json). Copy if linking is impossible.
    if dst.exists():
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / union if union > 0 else 0.0


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
    event = js.parent.name
    if not boxes and event in MUST_HAVE_BOX:
        reasons.append(f"no boxes in a {event}/ image")
    return reasons, min_conf


def write_review_order():
    rows = []
    for js in AUTO.glob("*/*/*.json"):
        if is_done(js):
            continue
        img = next((js.with_suffix(e) for e in IMG_EXT if js.with_suffix(e).exists()), None)
        if img is None:
            continue
        try:
            reasons, min_conf = risk(js)
        except Exception as e:
            reasons, min_conf = [f"unreadable JSON ({e})"], 0.0
        rows.append((-len(reasons), min_conf, img.relative_to(AUTO).as_posix(),
                     "; ".join(reasons) or f"ok (min conf {min_conf:.2f})"))
    rows.sort()
    (AUTO / "review_order.txt").write_text(
        "# images in sessions not yet renamed -done, most doubtful first\n"
        + "".join(f"{rel}\t{why}\n" for _, _, rel, why in rows), encoding="utf-8")
    return sum(1 for r in rows if r[0] < 0), len(rows)


def autolabel():
    if not MODEL.exists():
        raise SystemExit(f"Model not found: {MODEL}\nTrain first, or fix MODEL at the top of autolabel.py")
    todo = find_todo()
    print(f"{len(todo)} new images to label")

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
            link_or_copy(src, dst)
            dst.with_suffix(".json").write_text(json.dumps(
                {"version": "4.1.0", "flags": {}, "shapes": shapes, "imagePath": dst.name,
                 "imageData": None, "imageHeight": h, "imageWidth": w}, indent=2), encoding="utf-8")
            if n % 100 == 0:
                print(f"  {n}/{len(todo)}")

    AUTO.mkdir(parents=True, exist_ok=True)
    flagged, pending = write_review_order()
    print(f"\nimages labeled:         {len(todo)}")
    for label, n in boxes.most_common():
        print(f"  {label:<16}{n} boxes")
    print(f"images with no boxes:   {empty}")
    print(f"waiting for review:     {pending} images (sessions not renamed -done yet)")
    print(f"  of which doubtful:    {flagged}  (listed first in {AUTO / 'review_order.txt'})")


if __name__ == "__main__":
    autolabel()
