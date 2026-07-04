from utils import get_mouse_pos, get_image, click, press, match, read_number, read_text
import time, random, json, os
from threading import Event

CONFIG_PATH = "config.json"
CONFIG_KEYS = ("water_pos", "bait_pos", "deto_pos", "recycle_pos", "first_fish_pos",
               "uranium_img", "splash_img", "empty_fish_img")


class Autofisher:

    def load_config(self):
        if not os.path.exists(CONFIG_PATH):
            return False
        with open(CONFIG_PATH) as f:
            data = json.load(f)
        for k in CONFIG_KEYS:
            if k not in data:
                return False  # partial config → re-run calibration
            setattr(self, k, data[k])
        return True

    def save_config(self):
        data = {k: getattr(self, k) for k in CONFIG_KEYS}
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)

    def __init__(self):
        self.stop_event = Event()
        if not self.load_config():
            self.water_pos = get_mouse_pos()
            self.bait_pos = get_mouse_pos()
            self.deto_pos = get_mouse_pos()
            self.recycle_pos = get_mouse_pos()
            self.first_fish_pos = get_mouse_pos()
            self.uranium_img = get_image("uranium")
            self.splash_img = get_image("splash")
            self.empty_fish_img = get_image("empty_fish")
            self.save_config()

    def log(self, msg):
        print(msg)

    def stopped(self):
        return self.stop_event.is_set()

    def delay(self):
        return random.uniform(0.1, 0.35)

    def cast(self):
        time.sleep(self.delay())
        click(*self.bait_pos)
        time.sleep(self.delay())
        click(*self.water_pos)

    def recycle_inventory(self):
        while not match(self.empty_fish_img, "empty_fish.png"):
            click(*self.first_fish_pos)
            time.sleep(self.delay())
            click(*self.recycle_pos)
            time.sleep(2)

            number = read_number()
            # print(f"[ocr] parsed={number}")
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
            # cooldown — skip every check while the cast/catch is still animating
            if time.time() - last_cast < self.CAST_COOLDOWN:
                time.sleep(0.1)
                continue

            text = read_text()  # one OCR per iteration, reused below

            if "There was nothing on the line!" in text:
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
            elif "You can't fish here, find an emptier spot!" in text:
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
    af = Autofisher()
    try:
        af.loop()
    except KeyboardInterrupt:
        af.stop_event.set()
        af.log("stopped by user")