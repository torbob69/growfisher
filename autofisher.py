from utils import get_mouse_pos, get_image, click, press, match, read_number
import time, random
from threading import Event


class Autofisher:
    def __init__(self, cfg: dict | None = None, stop_event: Event | None = None,
                 on_log=None, paused: callable = lambda: False):
        # cfg = pre-captured dict from GUI. None = old interactive flow.
        self.stop_event = stop_event or Event()
        self.on_log = on_log or (lambda msg: print(msg))
        self.is_paused = paused
        if cfg is None:
            cfg = self._interactive_calibrate()
        for k, v in cfg.items():
            setattr(self, k, v)

    def _interactive_calibrate(self):
        cfg = {}
        for name in ("bait", "water", "deto", "first_fish", "recycle"):
            print(f"Point at {name} position and press X when done.")
            cfg[f"{name}_pos"] = get_mouse_pos()
        for key, save in (("uranium_img", "uranium"), ("splash_img", "splash"),
                          ("emptier_img", "emptier"), ("empty_fish_img", "empty_fish"),
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
        time.sleep(self.delay())
        click(*self.bait_pos)
        time.sleep(self.delay())
        click(*self.water_pos)

    def recycle_inventory(self):
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

    def loop(self):
        self.log("autofisher running")
        self.fish = 0
        self.cast()
        last_cast = time.time()

        while not self.stopped():
            self.wait_while_paused()
            if self.stopped(): break

            # cooldown — skip every check while the cast/catch is still animating
            if time.time() - last_cast < self.CAST_COOLDOWN:
                time.sleep(0.1)
                continue

            if match(self.nothing_img, "nothing.png", threshold=0.5):
                self.log("nothing on the line → recast")
                time.sleep(1.5)
            elif match(self.uranium_img, "uranium.png"):
                time.sleep(0.15)
                if not match(self.uranium_img, "uranium.png"): continue

                self.log("water frozen → deto")
                time.sleep(self.delay())
                click(*self.deto_pos)
                time.sleep(self.delay())
                click(*self.water_pos)
                time.sleep(self.delay())
            elif match(self.emptier_img, "emptier.png", threshold=0.65):
                self.log("inventory full → recycle")
                self.recycle_inventory()
            elif not match(self.splash_img, "splash.png", threshold=0.5):
                time.sleep(self.delay())
                click(*self.water_pos)
                time.sleep(self.delay())
                self.fish += 1
                self.log(f"caught (total: {self.fish})")
                time.sleep(0.5)
            else:
                time.sleep(0.1)
                continue

            self.cast()
            last_cast = time.time()

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
