# Builds the YOLO dataset in dataset/yolo from REVIEWED labels only: the .json files in
# dataset/autolabel session folders renamed to end with "-done" (e.g. 20261005_124043-done).
# Only dataset/yolo is written, and it is rebuilt from scratch on every run.
import json, os, random, shutil
from collections import Counter
from pathlib import Path

from PIL import Image

CLASSES = ["splash", "bubble_nothing", "bubble_emptier", "bubble_caught", "bubble_maxed"]
AUTO, BG, OUT = Path("../dataset/autolabel"), Path("../dataset/background"), Path("../dataset/yolo")
DONE = "-done"
VAL_FRAC = 0.2
IMG_EXT = (".jpg", ".jpeg", ".png")


def warn(msg):
    print(f"  WARNING: {msg}")


def strip_done(name):
    return name[:-len(DONE)] if name.endswith(DONE) else name


def find_image(js):
    for ext in IMG_EXT:
        p = js.with_suffix(ext)
        if p.exists():
            return p
    return None


def read_labels(js):
    """-> (image_path, ["cls cx cy w h", ...]) or None if the file should be skipped."""
    try:
        d = json.loads(js.read_text(encoding="utf-8"))
    except Exception as e:
        return warn(f"{js}: can't read JSON ({e}) — skipped")
    img = find_image(js)
    if img is None:
        return warn(f"{js}: no image next to it — skipped")
    w, h = d.get("imageWidth"), d.get("imageHeight")
    if not w or not h:
        try:
            w, h = Image.open(img).size
        except Exception as e:
            return warn(f"{img}: can't open image ({e}) — skipped")
    lines = []
    for s in d.get("shapes") or []:
        label = s.get("label")
        if label not in CLASSES:
            # skip the whole image: dropping just the box would teach "nothing here"
            return warn(f"{js}: unknown label {label!r} (typo?) — image skipped")
        try:
            xs, ys = [float(p[0]) for p in s["points"]], [float(p[1]) for p in s["points"]]
        except Exception:
            return warn(f"{js}: bad points on a {label!r} box — image skipped")
        x1, x2 = max(0.0, min(xs)), min(float(w), max(xs))
        y1, y2 = max(0.0, min(ys)), min(float(h), max(ys))
        if x2 - x1 < 1 or y2 - y1 < 1:
            warn(f"{js}: zero-size {label!r} box ignored")
            continue
        lines.append(f"{CLASSES.index(label)} {(x1+x2)/2/w:.6f} {(y1+y2)/2/h:.6f} "
                     f"{(x2-x1)/w:.6f} {(y2-y1)/h:.6f}")
    return img, lines


def pick_val_sessions(per_session, tries=5000):
    # Whole sessions go to val, so near-identical frames of one event never sit in both splits.
    # ponytail: random search for the session set whose val share is closest to 20% for
    # images AND every class — fine for dozens of sessions, not thousands.
    total = sum(per_session.values(), Counter())
    keys = [k for k in total if total[k]]
    names, rng, best = sorted(per_session), random.Random(0), None
    for _ in range(tries):
        rng.shuffle(names)
        val, acc = set(), Counter()
        for s in names:
            if acc["_images"] >= VAL_FRAC * total["_images"]:
                break
            val.add(s)
            acc += per_session[s]
        score = sum((acc[k] / total[k] - VAL_FRAC) ** 2 for k in keys)
        if best is None or score < best[0]:
            best = (score, val)
    return best[1]


def main():
    print(f"Reading -done sessions in {AUTO} ...")
    items = []  # (session, event, image_path, label_lines) — session/event without "-done"
    n_skipped = 0
    for js in sorted(AUTO.glob("*/*/*.json")):
        sess, ev = js.parent.parent.name, js.parent.name
        if not sess.endswith(DONE):
            n_skipped += 1  # session not reviewed yet: never enters training
            continue
        r = read_labels(js)
        if r:
            items.append((strip_done(sess), ev, *r))
    print(f"using {len(items)} images from -done sessions, ignoring {n_skipped} not yet -done")
    if not items:
        raise SystemExit(f"No reviewed labels: rename a reviewed session folder in {AUTO} to end with {DONE}")

    per_session = {}
    for sess, _, _, lines in items:
        c = per_session.setdefault(sess, Counter())
        c["_images"] += 1
        c.update(CLASSES[int(l.split()[0])] for l in lines)
    val_sessions = pick_val_sessions(per_session) if len(per_session) > 1 else set()
    if not val_sessions:
        warn("only one session has labels — can't split by session, using it for both train and val")

    bg = sorted(p for p in BG.glob("*") if p.suffix.lower() in IMG_EXT) if BG.is_dir() else []

    if OUT.exists():
        shutil.rmtree(OUT)  # generated folder; only links/copies live here
    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        (OUT / sub).mkdir(parents=True)

    stats = {sp: {"images": Counter(), "boxes": Counter(), "total": 0, "background": 0}
             for sp in ("train", "val")}

    def put(split, src, name, lines):
        dst = OUT / "images" / split / name
        try:
            os.link(src, dst)  # hardlink: no extra disk space; training never writes images
        except OSError:
            shutil.copy2(src, dst)
        (OUT / "labels" / split / Path(name).with_suffix(".txt")).write_text(
            "".join(l + "\n" for l in lines))
        st = stats[split]
        st["total"] += 1
        st["background"] += not lines
        st["boxes"].update(CLASSES[int(l.split()[0])] for l in lines)
        st["images"].update({CLASSES[int(l.split()[0])] for l in lines})

    for sess, ev, img, lines in items:
        name = f"{sess}_{ev}_{img.name}"  # file names repeat across sessions
        if not val_sessions:
            put("train", img, name, lines); put("val", img, name, lines)
        else:
            put("val" if sess in val_sessions else "train", img, name, lines)
    for i, img in enumerate(bg):
        put("val" if i % 5 == 0 else "train", img, f"background_{img.name}", [])

    (OUT / "data.yaml").write_text(
        f"path: {OUT.resolve().as_posix()}\ntrain: images/train\nval: images/val\n"
        f"names:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(CLASSES)))

    print(f"\nval sessions: {', '.join(sorted(val_sessions)) or '(same as train)'}")
    print(f"background images: {len(bg)}" + ("" if BG.is_dir() else f"  ({BG} not found)"))
    print(f"\n{'class':<16}{'train img':>10}{'train box':>10}{'val img':>9}{'val box':>9}")
    for c in CLASSES:
        tr, va = stats["train"], stats["val"]
        print(f"{c:<16}{tr['images'][c]:>10}{tr['boxes'][c]:>10}{va['images'][c]:>9}{va['boxes'][c]:>9}")
        if not va["boxes"][c]:
            warn(f"no {c!r} boxes in val — its val score will be meaningless")
    for sp in ("train", "val"):
        print(f"{sp}: {stats[sp]['total']} images ({stats[sp]['background']} with no boxes)")
    print(f"\nWrote {OUT / 'data.yaml'}")


if __name__ == "__main__":
    main()
