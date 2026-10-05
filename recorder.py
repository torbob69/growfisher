# Dataset recorder: saves full Growtopia frames into dataset/raw/<session>/<event>/
# whenever the bot detects something. All disk IO runs on one background thread.
import json, os, queue, threading, time
from collections import deque
from datetime import datetime

import cv2
import numpy as np

import utils


class Recorder:
    def __init__(self, enabled, root="dataset/raw", fmt="jpg", jpg_quality=95, history=4,
                 history_dt=0.15, idle_every=20.0, max_per_class=1500, min_gap=1.0, on_log=None):
        self.enabled = enabled
        self.root, self.fmt = root, fmt
        self.params = ([cv2.IMWRITE_JPEG_QUALITY, jpg_quality] if fmt == "jpg"
                       else [cv2.IMWRITE_PNG_COMPRESSION, 1])
        self.history, self.history_dt = history, history_dt
        self.idle_every, self.max_per_class, self.min_gap = idle_every, max_per_class, min_gap
        self.log = on_log or print
        self._started = False

    def start(self, **session_meta):
        if not self.enabled: return
        self.dir = os.path.join(self.root, datetime.now().strftime("%Y%m%d_%H%M%S"))
        os.makedirs(self.dir, exist_ok=True)
        self._jsonl = open(os.path.join(self.dir, "events.jsonl"), "a", encoding="utf-8")
        self._jsonl.write(json.dumps({"type": "session", "t": time.time(), **session_meta},
                                     default=str) + "\n")
        # ponytail: each queued item pins a ~8MB frame; 24 caps that at ~200MB
        self._q = queue.Queue(maxsize=24)
        self._ring = deque(maxlen=self.history + 1)  # +1: newest sample is often the event frame itself
        self._lock = threading.Lock()
        self._counts, self._ids, self._last = {}, {}, {}
        self._dropped, self._last_idle = 0, 0.0
        self._after = []
        self._halt = threading.Event()
        self._sampler = threading.Thread(target=self._sample, daemon=True)
        self._writer = threading.Thread(target=self._write, daemon=True)
        self._sampler.start(); self._writer.start()
        self._started = True
        self.log(f"recording to {self.dir}")

    def stop(self):
        if not self._started: return
        self._started = False
        for t in self._after: t.join()  # let pending after-captures land (≤ max offset)
        self._halt.set()
        self._sampler.join()
        self._q.put(None)  # blocking is fine here: we're leaving the loop anyway
        self._writer.join()
        self._jsonl.close()
        counts = ", ".join(f"{k}={v}" for k, v in sorted(self._counts.items())) or "nothing"
        self.log(f"recorded {counts}; dropped {self._dropped} frames")

    # ------------------------------------------------------------ API ----

    def event(self, name, regions=None, pre=0, after=(), now=True, before=(), **meta):
        if not self._started: return
        t0 = time.time()
        with self._lock:
            if t0 - self._last.get(name, -1e9) < self.min_gap: return
            if self._counts.get(name, 0) >= self.max_per_class: return
            self._last[name] = t0
            eid = self._ids[name] = self._ids.get(name, 0) + 1
        cur = utils.latest_frame()
        if cur is None: return
        boxes = {k: utils.client_to_frame(v, cur.shape) for k, v in (regions or {}).items() if v}
        base = {"event": name, "event_id": eid, "regions": boxes, **meta}
        if pre:
            old = [(t, f) for t, f in list(self._ring) if f is not cur and t < t0 - 0.05][-pre:]
            for t, f in old:
                self._put(name, eid, t - t0, t, f, base)
        if before:  # ring frame nearest to each requested offset, e.g. (0.1, 0.2) = -0.1s, -0.2s
            ring = [(t, f) for t, f in list(self._ring) if f is not cur]
            picked = dict(min(ring, key=lambda r: abs(r[0] - (t0 - off))) for off in before) if ring else {}
            for t, f in sorted(picked.items()):
                self._put(name, eid, t - t0, t, f, base)
        if now:
            self._put(name, eid, 0.0, t0, cur, base)
        if after:
            th = threading.Thread(target=self._later, args=(name, eid, t0, after, base), daemon=True)
            th.start()
            self._after = [x for x in self._after if x.is_alive()] + [th]

    def idle(self, regions=None, **meta):
        if not self._started or time.time() - self._last_idle < self.idle_every: return
        self._last_idle = time.time()
        self.event("idle", regions=regions, **meta)

    def mark(self, name, **meta):
        if not self._started: return
        self._enqueue((None, None, {"type": "mark", "event": name, "t": time.time(), **meta}))

    # -------------------------------------------------------- internals ----

    def _later(self, name, eid, t0, offsets, base):
        for off in sorted(offsets):
            if self._halt.wait(max(0, t0 + off - time.time())): return
            f = utils.latest_frame()
            if f is not None:
                self._put(name, eid, off, time.time(), f, base)

    def _put(self, name, eid, off, t, frame, base):
        with self._lock:
            if self._counts.get(name, 0) >= self.max_per_class: return
        rel = f"{name}/{name}_{eid:05d}_{off:+.2f}.{self.fmt}"
        rec = {"type": "image", **base, "file": rel, "offset": round(off, 3), "t": t,
               "frame_wh": [frame.shape[1], frame.shape[0]]}
        if self._enqueue((rel, frame, rec)):
            with self._lock:
                self._counts[name] = self._counts.get(name, 0) + 1

    def _enqueue(self, item):
        try:
            self._q.put_nowait(item)
            return True
        except queue.Full:
            with self._lock:
                self._dropped += 1
            return False

    def _sample(self):
        # references only — every WGC frame is a fresh .copy() that nobody mutates
        while not self._halt.wait(self.history_dt):
            f = utils.latest_frame()
            if f is not None and (not self._ring or self._ring[-1][1] is not f):
                self._ring.append((time.time(), f))

    def _write(self):
        made = set()
        while (item := self._q.get()) is not None:
            rel, frame, rec = item
            try:
                if frame is not None:
                    path = os.path.join(self.dir, rel)
                    d = os.path.dirname(path)
                    if d not in made:
                        os.makedirs(d, exist_ok=True); made.add(d)
                    if not cv2.imwrite(path, np.ascontiguousarray(frame[..., :3]), self.params):
                        raise OSError(f"imwrite failed for {path}")
                self._jsonl.write(json.dumps(rec) + "\n")
                self._jsonl.flush()
            except Exception as e:
                self.log(f"recorder write error: {e}")
