from utils import (get_mouse_pos, get_image, click, press, match, diff, read_number,
                   pixels_changed, latest_frame)
from recorder import Recorder
import detector
import time, random
from threading import Event


class Autofisher:
    def __init__(self, cfg: dict | None = None, stop_event: Event | None = None,
                 on_log=None, paused: callable = lambda: False):
        # cfg = pre-captured dict from GUI. None = old interactive flow.
        self.stop_event = stop_event or Event()
        self.on_log = on_log or (lambda msg: print(msg))
        self.is_paused = paused
        self.deto = True  # off = skip uranium check entirely (no deto_pos/uranium_img needed)
        self.cast_delay = None  # None = random 0.1-0.35s; else fixed seconds between bait/water clicks
        self.splash_diff = 15          # mean pixel change vs splash.png that counts as a bite
        self.nothing_threshold = 0.5   # match score for nothing.png
        self.emptier_threshold = 0.35  # match score for emptier.png
        self.fav_img = None            # optional: region that must never change
        self.fav_diff_px = 1           # pixels of change in fav_img that stops the bot
        self.record = False            # save detection frames to dataset/raw for training
        self.yolo = False              # True = events come from the YOLO model, not picked regions
        # min confidence per YOLO class for a detection to count (GUI: "YOLO confidence")
        self.conf_splash = 0.2
        self.conf_bubble_nothing = 0.2
        self.conf_bubble_emptier = 0.2
        self.conf_bubble_caught = 0.2
        self.conf_bubble_maxed = 0.2
        self.conf_uranium = 0.5        # used once a model has a uranium class
        if cfg is None:
            cfg = self._interactive_calibrate()
        self.cfg = cfg
        for k, v in cfg.items():
            setattr(self, k, v)
        self.rec = Recorder(enabled=bool(self.record), on_log=self.log)

    def _interactive_calibrate(self):
        cfg = {}
        for name in ("bait", "water", "deto", "first_fish", "recycle"):
            print(f"Point at {name} position and press X when done.")
            cfg[f"{name}_pos"] = get_mouse_pos()
        for key, save in (("uranium_img", "uranium"), ("splash_img", "splash"),
                          ("emptier_img", "emptier"), ("empty_fish_img", "empty_fish"),
                          ("nothing_img", "nothing"),
                          ("number_bbox", "number_bbox")):
            cfg[key] = get_image(save)
        return cfg

    def log(self, msg):
        self.on_log(msg)

    def wait_while_paused(self):
        while self.is_paused() and not self.stop_event.is_set():
            time.sleep(0.1)

    def delay(self):
        return random.uniform(0.1, 0.35)

    def stopped(self):
        return self.stop_event.is_set()

    def cast(self):
        d = self.cast_delay if self.cast_delay is not None else self.delay()
        time.sleep(d)
        click(*self.bait_pos)
        time.sleep(d)
        click(*self.water_pos)
        self.rec.mark("cast")

    def recycle_inventory(self):
        detector.paused.set()  # no object detection at all while recycling (bot + overlay)
        try:
            self._recycle()
        finally:
            detector.paused.clear()

    def _recycle(self):
        while not match(self.empty_fish_img, "empty_fish.png"):
            if self.stopped():
                return
            click(*self.first_fish_pos)
            time.sleep(self.delay())
            click(*self.recycle_pos)
            time.sleep(2)

            number = read_number(self.number_bbox)
            for letter in (str(number) if number is not None else ""):
                time.sleep(0.03)
                press(letter)
            press("enter")
            time.sleep(2)
            
            click(*self.first_fish_pos)

    CAST_COOLDOWN = 2  # blanks detection during cast/catch animations
    DETECT_FPS = 15    # caps YOLO inference; CPU usage scales with this

    def loop(self):
        self.rec.start(cfg=self.cfg)
        try:
            self._loop_yolo() if self.yolo else self._loop()
        finally:
            self.rec.stop()

    def _fav_changed(self):
        # fav item guard — checked even during cooldown; losing it means bail now
        if self.fav_img:
            px = pixels_changed(self.fav_img, "fav.png")
            if px >= self.fav_diff_px:
                self.log(f"fav item changed ({px}px) → stopping")
                self.stop_event.set()
                return True
        return False

    def _loop_yolo(self):
        # Same actions as _loop, but each one fires when its object newly APPEARS in YOLO
        # detections. An object must vanish before it can fire again, so a bubble that lingers
        # on screen triggers once. Positions (bait/water/deto/recycle…) are still clicked.
        detector.load(self.log)
        warm = latest_frame()
        if warm is not None:
            detector.detect(warm)
    
        yolo_uranium = "uranium" in detector.names()
        confs = {n: float(getattr(self, f"conf_{n}", 0.5)) for n in detector.names()}
        floor = min(confs.values())  # model returns everything above the lowest; filtered per class below
        self.log("autofisher running (YOLO, conf " + ", ".join(f"{n} {c}" for n, c in confs.items())
                 + (", uranium by region" if self.deto and not yolo_uranium else "") + ")")
        self.fish = 0
        self.cast()
        last_cast = time.time()
        armed = {}  # label -> may fire (False until it has disappeared after firing)
        last, last_detect = None, 0.0

        while not self.stopped():
            self.wait_while_paused()
            if self.stopped() or self._fav_changed(): break

            f = latest_frame()
            # no new frame yet, or too soon since the last inference
            if f is None or f is last or time.time() - last_detect < 1 / self.DETECT_FPS:
                time.sleep(0.01)
                continue
            last, last_detect = f, time.time()
            dets = [d for d in detector.detect(f, conf=floor, publish=False) if d[1] >= confs.get(d[0], 0.5)]
            detector.last = (time.time(), f.shape[:2], dets)  # overlay shows exactly what counts
            seen = {}
            for label, c, _ in dets:
                seen[label] = max(seen.get(label, 0.0), c)
            for label in armed:
                if label not in seen:
                    armed[label] = True
            new = {l for l in seen if armed.get(l, True)}
            boxes = [(l, round(c, 3), [round(v) for v in b]) for l, c, b in dets]

            # cooldown — no actions while the cast/catch is still animating
            if time.time() - last_cast < self.CAST_COOLDOWN:
                time.sleep(0.05)
                continue

            if "bubble_nothing" in new:
                armed["bubble_nothing"] = False
                self.log(f"nothing on the line ({seen['bubble_nothing']:.2f}) → recast")
                self.rec.event("nothing", after=(0.4,), dets=boxes)
                time.sleep(1.5)
            elif self.deto and ("uranium" in new if yolo_uranium else
                                match(self.uranium_img, "uranium.png")):
                if yolo_uranium:
                    armed["uranium"] = False
                else:
                    time.sleep(0.15)
                    if not match(self.uranium_img, "uranium.png"): continue
                self.rec.event("uranium", after=(0.3,), dets=boxes)
                self.log("water frozen → deto")
                time.sleep(self.delay())
                click(*self.deto_pos)
                time.sleep(self.delay())
                click(*self.water_pos)
                time.sleep(self.delay())
            elif "bubble_emptier" in new:
                armed["bubble_emptier"] = False
                self.rec.event("emptier", after=(0.4,), dets=boxes)
                self.log(f"inventory full ({seen['bubble_emptier']:.2f}) → recycle")
                self.recycle_inventory()
                last = None  # frames from before the recycle are stale
            elif "splash" in new:
                armed["splash"] = False
                c = seen["splash"]
                self.rec.event("splash", after=(0.1, 0.2, 0.3), conf=c, dets=boxes)
                time.sleep(self.delay())
                click(*self.water_pos)
                self.rec.mark("click", reason="splash", conf=c)
                self.rec.event("caught", now=False, after=(0.6, 1.2, 1.8))
                time.sleep(self.delay())
                self.fish += 1
                self.log(f"caught, splash {c:.2f} (total: {self.fish})")
                time.sleep(0.5)
            else:
                # caught/maxed bubbles have no action (same as region mode) — just mark them seen
                for label in new & {"bubble_caught", "bubble_maxed"}:
                    armed[label] = False
                self.rec.idle(dets=boxes)
                continue

            self.cast()
            last_cast = time.time()

        self.log("autofisher stopped")

    def _loop(self):
        self.log("autofisher running")
        self.fish = 0
        self.cast()
        last_cast = time.time()
        peak = 0.0  # highest splash diff seen since the cast — your tuning number

        while not self.stopped():
            self.wait_while_paused()
            if self.stopped(): break

            # fav item guard — checked even during cooldown; losing it means bail now
            if self.fav_img:
                px = pixels_changed(self.fav_img, "fav.png")
                if px >= self.fav_diff_px:
                    self.log(f"fav item changed ({px}px) → stopping")
                    self.stop_event.set()
                    break

            # cooldown — skip every check while the cast/catch is still animating
            if time.time() - last_cast < self.CAST_COOLDOWN:
                time.sleep(0.1)
                continue

            d = diff(self.splash_img, "splash.png")
            peak = max(peak, d)

            if match(self.nothing_img, "nothing.png", threshold=self.nothing_threshold):
                self.log(f"nothing on the line → recast (splash peak {peak:.0f} "
                         f"vs splash_diff {self.splash_diff})")
                self.rec.event("nothing", regions={"nothing_hint": self.nothing_img},
                               after=(0.4,), splash_peak=peak)
                time.sleep(1.5)
            elif self.deto and match(self.uranium_img, "uranium.png"):
                time.sleep(0.15)
                if not match(self.uranium_img, "uranium.png"): continue

                self.rec.event("uranium", regions={"uranium": self.uranium_img}, after=(0.3,))
                self.log("water frozen → deto")
                time.sleep(self.delay())
                click(*self.deto_pos)
                time.sleep(self.delay())
                click(*self.water_pos)
                time.sleep(self.delay())
            elif match(self.emptier_img, "emptier.png", threshold=self.emptier_threshold):
                self.rec.event("emptier", regions={"emptier_hint": self.emptier_img}, after=(0.4,))
                self.log("inventory full → recycle")
                self.recycle_inventory()
            elif d > self.splash_diff:
                self.rec.event("splash", regions={"splash": self.splash_img},
                               after=(0.1, 0.2, 0.3), diff=d)
                time.sleep(self.delay())
                click(*self.water_pos)
                self.rec.mark("click", reason="splash", diff=d)
                self.rec.event("caught", now=False, after=(0.6, 1.2, 1.8))
                time.sleep(self.delay())
                self.fish += 1
                self.log(f"caught, diff {d:.0f} (total: {self.fish})")
                time.sleep(0.5)
            else:
                self.rec.idle(regions={"splash": self.splash_img}, diff=d)
                time.sleep(0.05)
                continue

            self.cast()
            last_cast = time.time()
            peak = 0.0

        self.log("autofisher stopped")


if __name__ == "__main__":
    Autofisher().loop()


# Future improvements:
'''
Global window image matching instead of picking area manually --> saves alot of time especially when we trynna reconfigure again :
I wanna change water region to uranium region. So basicly we take a snapshot of a state where the water freezes and became a uranium block. We capture the moment when the water turns into uranium block.
So we match the uranium region. If it match we do :
self.log("water frozen → deto")
                time.sleep(self.delay())
                click(*self.deto_pos)
                time.sleep(self.delay())
                click(*self.water_pos)
                time.sleep(self.delay())


Why : because the bot will be broken if i accidentally change the zoom.
'''
