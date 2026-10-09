# Builds the YOLO dataset in dataset/yolo from REVIEWED labels only: the .json files in
# dataset/autolabel session folders named <world>-<session>[-far]-done
# (e.g. empangpeleh21-20261003_142718-done, public3-20261008_152214-far-done).
# Train/val is split 80/20 BY WORLD: every session of a world goes to the same side, so val
# only has worlds the model never trained on. The trailing number is the spot inside a world
# (empangpeleh21 and empangpeleh29 are both world "empangpeleh"), except for NUMBER_IS_WORLD.
# Only dataset/yolo is written, and it is rebuilt from scratch on every run.
import itertools, json, os, random, re, shutil
from collections import Counter
from pathlib import Path

from PIL import Image

CLASSES = ["splash", "bubble_nothing", "bubble_emptier", "bubble_caught", "bubble_maxed"]
AUTO, BG, OUT = Path("../dataset/autolabel"), Path("../dataset/background"), Path("../dataset/yolo")
DONE = "-done"
VAL_FRAC = 0.2
IMG_EXT = (".jpg", ".jpeg", ".png")
STAMP = re.compile(r"\d{8}_\d{6}")  # recording time inside the folder name
# Normally the trailing number is a spot inside one world (empangpeleh21 == empangpeleh29).
# For these names the number IS the world: public1 and public2 are different worlds.
NUMBER_IS_WORLD = {"public"}


def warn(msg):
    print(f"  WARNING: {msg}")


def strip_done(name):
    return name[:-len(DONE)] if name.endswith(DONE) else name


def parse_session(folder):
    """'empangpeleh21-20261003_142718-far-done' -> ('empangpeleh', True). World is None if the
    folder has no name before the recording time."""
    name = strip_done(folder)
    m = STAMP.search(name)
    prefix = name[:m.start()].rstrip("-_ ") if m else name
    base = prefix.rstrip("0123456789") or prefix
    world = prefix if base in NUMBER_IS_WORLD else base  # spot number -> same world
    far = "-far" in (name[m.end():] if m else name)
    return world or None, far


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


def pick_val_worlds(per_world):
    """Whole worlds go to val. Picks the set of worlds whose val share is closest to 20% for
    the image count, EVERY class's box count, and the -far images (stratified)."""
    total = sum(per_world.values(), Counter())
    keys = ["_images"] + [c for c in CLASSES if total[c]]
    if 0 < total["_far"] < total["_images"]:
        keys.append("_far")  # only stratify on zoom if both zooms exist

    def score(val):
        acc = sum((per_world[w] for w in val), Counter())
        return sum((acc[k] / total[k] - VAL_FRAC) ** 2 for k in keys)

    names = sorted(per_world)
    if len(names) <= 16:  # exhaustive: every split of up to 16 worlds (65k options)
        options = (set(c) for r in range(1, len(names)) for c in itertools.combinations(names, r))
    else:  # ponytail: random search past 16 worlds; exhaustive would be too slow
        rng = random.Random(0)
        options = ({w for w in names if rng.random() < VAL_FRAC} for _ in range(20000))
    return min((o for o in options if o and len(o) < len(names)), key=score)


def main():
    print(f"Reading -done sessions in {AUTO} ...")
    items = []  # (session, world, far, event, image_path, label_lines)
    n_skipped, no_world = 0, set()
    for js in sorted(AUTO.glob("*/*/*.json")):
        folder, ev = js.parent.parent.name, js.parent.name
        if not folder.endswith(DONE):
            n_skipped += 1  # session not reviewed yet: never enters training
            continue
        r = read_labels(js)
        if r:
            world, far = parse_session(folder)
            if world is None:
                no_world.add(folder)
                world = strip_done(folder)  # its own world
            items.append((strip_done(folder), world, far, ev, *r))
    print(f"using {len(items)} images from -done sessions, ignoring {n_skipped} not yet -done")
    for f in sorted(no_world):
        warn(f"{f} has no world name in front — treated as its own world")
    if not items:
        raise SystemExit(f"No reviewed labels: rename a reviewed session folder in {AUTO} to end with {DONE}")

    per_world, sessions = {}, {}
    for sess, world, far, _, _, lines in items:
        c = per_world.setdefault(world, Counter())
        c["_images"] += 1
        c["_far"] += far
        c.update(CLASSES[int(l.split()[0])] for l in lines)
        sessions.setdefault(world, set()).add(sess)
    val_worlds = pick_val_worlds(per_world) if len(per_world) > 1 else set()
    if not val_worlds:
        warn("only one world has labels — can't split by world, using it for both train and val")

    bg = sorted(p for p in BG.glob("*") if p.suffix.lower() in IMG_EXT) if BG.is_dir() else []

    if OUT.exists():
        shutil.rmtree(OUT)  # generated folder; only links/copies live here
    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        (OUT / sub).mkdir(parents=True)

    stats = {sp: {"images": Counter(), "boxes": Counter(), "total": 0, "background": 0, "far": 0}
             for sp in ("train", "val")}

    def put(split, src, name, lines, far=False):
        dst = OUT / "images" / split / name
        try:
            os.link(src, dst)  # hardlink: no extra disk space; training never writes images
        except OSError:
            shutil.copy2(src, dst)
        (OUT / "labels" / split / Path(name).with_suffix(".txt")).write_text(
            "".join(l + "\n" for l in lines))
        st = stats[split]
        st["total"] += 1
        st["far"] += far
        st["background"] += not lines
        st["boxes"].update(CLASSES[int(l.split()[0])] for l in lines)
        st["images"].update({CLASSES[int(l.split()[0])] for l in lines})

    for sess, world, far, ev, img, lines in items:
        name = f"{sess}_{ev}_{img.name}"  # file names repeat across sessions
        if not val_worlds:
            put("train", img, name, lines, far); put("val", img, name, lines, far)
        else:
            put("val" if world in val_worlds else "train", img, name, lines, far)
    for i, img in enumerate(bg):
        put("val" if i % 5 == 0 else "train", img, f"background_{img.name}", [])

    (OUT / "data.yaml").write_text(
        f"path: {OUT.resolve().as_posix()}\ntrain: images/train\nval: images/val\n"
        f"names:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(CLASSES)))

    print(f"\n{'world':<14}{'sessions':>9}{'images':>8}{'far':>6}  split")
    for w in sorted(per_world, key=lambda w: (w not in val_worlds, w)):
        c = per_world[w]
        print(f"{w:<14}{len(sessions[w]):>9}{c['_images']:>8}{c['_far']:>6}  "
              f"{'VAL' if w in val_worlds else 'train'}")
    print(f"background images: {len(bg)}" + ("" if BG.is_dir() else f"  ({BG} not found)"))

    tr, va = stats["train"], stats["val"]
    pct = lambda v, t: f"{100 * v / (v + t):.0f}%" if v + t else "-"
    print(f"\n{'class':<16}{'train img':>10}{'train box':>10}{'val img':>9}{'val box':>9}{'val %':>7}")
    for c in CLASSES:
        print(f"{c:<16}{tr['images'][c]:>10}{tr['boxes'][c]:>10}{va['images'][c]:>9}{va['boxes'][c]:>9}"
              f"{pct(va['boxes'][c], tr['boxes'][c]):>7}")
        if not va["boxes"][c]:
            warn(f"no {c!r} boxes in val — its val score will be meaningless")
        elif val_worlds and not 0.1 <= va["boxes"][c] / (va["boxes"][c] + tr["boxes"][c]) <= 0.35:
            warn(f"{c!r} val share is far from {VAL_FRAC:.0%} — the worlds can't split it evenly")
    for sp in ("train", "val"):
        print(f"{sp}: {stats[sp]['total']} images ({stats[sp]['background']} with no boxes, "
              f"{stats[sp]['far']} far)")
    print(f"val share: {pct(va['total'], tr['total'])} of images, {pct(va['far'], tr['far'])} of far images")
    print(f"\nWrote {OUT / 'data.yaml'}")


if __name__ == "__main__":
    main()
