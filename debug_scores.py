# ponytail: live match scores + capture freshness. Run while fishing, watch splash.
import json, time, cv2, numpy as np
import utils
from utils import grab_window, diff

REGIONS = ("splash", "uranium", "nothing", "emptier", "empty_fish")
calib = json.load(open("calib.json"))
needles = {n: cv2.imread(f"{n}.png") for n in REGIONS}

prev_frame = None
while True:
    grab_window()  # refresh _latest_frame handle
    fresh = utils._latest_frame is not prev_frame  # new .copy() each frame -> identity works
    prev_frame = utils._latest_frame

    parts = []
    for n in REGIONS:
        hay = cv2.cvtColor(np.array(grab_window(tuple(calib[f"{n}_img"]))), cv2.COLOR_RGB2BGR)
        score = cv2.minMaxLoc(cv2.matchTemplate(hay, needles[n], cv2.TM_CCOEFF_NORMED))[1]
        parts.append(f"{n}={score:.2f}")
    d = diff(tuple(calib["splash_img"]), "splash.png")  # what the bot now fires on
    print(("LIVE " if fresh else "FROZEN") + f" | splash_diff={d:5.1f} | " + "  ".join(parts), flush=True)
    time.sleep(0.2)
