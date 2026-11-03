"""Diagnostic: estimate how much the camera moves across each lane video.

Samples frames at a fixed interval and measures frame-to-frame global shift
with phase correlation. Reports whether each lane looks like a fixed camera
(safe for the static ROI_POLYGONS/STOP_LINES approach) or a moving one
(panning/zooming/drifting - the static ROI will drift out of alignment),
and finds the longest contiguous "stable" window if the clip isn't fixed
the whole way through.

Usage (run from inside backend/, with the venv active):
    python tools/check_camera_motion.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

import config

SAMPLE_SECONDS = 0.5
RESIZE = (320, 180)
STABLE_SHIFT_PX = 1.5   # phase-correlation shift (at 320x180 scale) below this = "stable" step


def analyze(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return None
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    frame_interval = max(int(round(fps * SAMPLE_SECONDS)), 1)
    hann = cv2.createHanningWindow(RESIZE, cv2.CV_32F)

    prev_gray = None
    shifts = []       # per sampled step
    timestamps = []   # time of the *later* frame in each step
    idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % frame_interval == 0:
            small = cv2.resize(frame, RESIZE)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).astype(np.float32)
            if prev_gray is not None:
                (dx, dy), _response = cv2.phaseCorrelate(prev_gray, gray, hann)
                shifts.append((dx ** 2 + dy ** 2) ** 0.5)
                timestamps.append(idx / fps)
            prev_gray = gray
        idx += 1

    cap.release()
    return timestamps, shifts


def longest_stable_window(timestamps, shifts):
    best_start, best_end = None, None
    cur_start = None
    for t, s in zip(timestamps, shifts):
        if s < STABLE_SHIFT_PX:
            if cur_start is None:
                cur_start = t
            cur_end = t
            if best_start is None or (cur_end - cur_start) > (best_end - best_start):
                best_start, best_end = cur_start, cur_end
        else:
            cur_start = None
    return best_start, best_end


def main():
    for lane, path in config.LANE_VIDEOS.items():
        result = analyze(path)
        if result is None:
            print(f"{lane}: could not open {path}")
            continue
        timestamps, shifts = result
        if not shifts:
            print(f"{lane}: not enough frames to analyze")
            continue

        shifts_np = np.array(shifts)
        mean_shift = shifts_np.mean()
        max_shift = shifts_np.max()
        verdict = "STATIC" if mean_shift < STABLE_SHIFT_PX else "MOVING"

        print(f"\n{lane}: {verdict}  (mean shift {mean_shift:.2f}px, max {max_shift:.2f}px per "
              f"{SAMPLE_SECONDS}s step)")

        if verdict == "MOVING":
            start, end = longest_stable_window(timestamps, shifts)
            if start is not None and (end - start) >= 2.0:
                print(f"  Longest stable window: {start:.1f}s - {end:.1f}s "
                      f"(~{end - start:.1f}s) - could trim to this range.")
            else:
                print("  No usable stable window found - recommend swapping this clip "
                      "for fixed-angle footage.")


if __name__ == "__main__":
    main()
