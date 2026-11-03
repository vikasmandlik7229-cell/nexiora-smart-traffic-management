"""Interactive ROI polygon + stop-line picker for a single lane video.

The preview window is resizable and the frame is scaled down to fit within
1280x720 if the source video is larger. Clicked points are converted back to
the original video's pixel coordinates before being printed, so the ROI still
lines up correctly when run_detection.py uses them at full resolution.

Usage (run from inside backend/, with the venv active):
    python tools/roi_picker.py --lane lane1

Controls:
    left-click      add a polygon point (lane boundary) while in POLYGON mode
    right-click/p   finish the polygon (needs >= 3 points) and switch to STOP-LINE mode
                    ('p' or Enter works the same as right-click - handy if your
                    trackpad's right-click doesn't reach the app)
    left-click      (in STOP-LINE mode) sets the stop-line y-coordinate
    s               save -> prints the lines to paste into config.py
    r               reset everything and start over
    q               quit
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np

import config

WINDOW_NAME = "ROI Picker - left-click to add points, right-click to finish polygon"
MAX_DISPLAY_WIDTH = 1280
MAX_DISPLAY_HEIGHT = 720


class PickerState:
    def __init__(self):
        self.polygon_points = []
        self.polygon_done = False
        self.stop_line_y = None
        self.flash_message = ""
        self.flash_until = 0.0
        self.flash_color = (0, 255, 0)

    def reset(self):
        self.polygon_points = []
        self.polygon_done = False
        self.stop_line_y = None

    def flash(self, message, color=(0, 255, 0), seconds=3.0):
        self.flash_message = message
        self.flash_color = color
        self.flash_until = time.time() + seconds


def on_mouse(event, x, y, flags, state: PickerState):
    if event == cv2.EVENT_LBUTTONDOWN:
        if not state.polygon_done:
            state.polygon_points.append((x, y))
        else:
            state.stop_line_y = y
    elif event == cv2.EVENT_RBUTTONDOWN:
        if not state.polygon_done and len(state.polygon_points) >= 3:
            state.polygon_done = True


def render(frame, state: PickerState):
    canvas = frame.copy()

    for pt in state.polygon_points:
        cv2.circle(canvas, pt, 4, (0, 255, 0), -1)
    if len(state.polygon_points) >= 2:
        pts = np.array(state.polygon_points, dtype=np.int32)
        cv2.polylines(canvas, [pts], isClosed=state.polygon_done, color=(0, 255, 0), thickness=2)

    if state.stop_line_y is not None:
        cv2.line(canvas, (0, state.stop_line_y), (canvas.shape[1], state.stop_line_y),
                  (0, 0, 255), 2)

    if not state.polygon_done:
        status = f"POLYGON mode: {len(state.polygon_points)} point(s) (need >= 3). Right-click or 'p' to finish."
    elif state.stop_line_y is None:
        status = "STOP-LINE mode: left-click to place the stop line."
    else:
        status = "Ready. Press 's' to print config lines, 'r' to reset, 'q' to quit."

    cv2.rectangle(canvas, (0, 0), (canvas.shape[1], 26), (0, 0, 0), -1)
    cv2.putText(canvas, status, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                (255, 255, 255), 1, cv2.LINE_AA)

    if state.flash_message and time.time() < state.flash_until:
        cv2.rectangle(canvas, (0, 30), (canvas.shape[1], 56), (0, 0, 0), -1)
        cv2.putText(canvas, state.flash_message, (6, 48), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    state.flash_color, 1, cv2.LINE_AA)

    return canvas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lane", required=True, choices=list(config.LANE_VIDEOS.keys()))
    args = parser.parse_args()

    video_path = config.LANE_VIDEOS[args.lane]
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    ret, frame = cap.read()
    cap.release()
    if not ret:
        raise RuntimeError(f"Could not read the first frame from: {video_path}")

    orig_h, orig_w = frame.shape[:2]
    scale = min(MAX_DISPLAY_WIDTH / orig_w, MAX_DISPLAY_HEIGHT / orig_h, 1.0)
    display_w, display_h = int(orig_w * scale), int(orig_h * scale)
    display_frame = cv2.resize(frame, (display_w, display_h)) if scale < 1.0 else frame

    state = PickerState()
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(WINDOW_NAME, display_w, display_h)
    cv2.setMouseCallback(WINDOW_NAME, on_mouse, state)

    while True:
        cv2.imshow(WINDOW_NAME, render(display_frame, state))
        key = cv2.waitKey(20) & 0xFF

        if key == ord('q'):
            break
        elif key == ord('r'):
            state.reset()
        elif key in (ord('p'), 13):  # 'p' or Enter - finish polygon (trackpads often can't right-click)
            if not state.polygon_done and len(state.polygon_points) >= 3:
                state.polygon_done = True
            elif not state.polygon_done:
                msg = "Need at least 3 points before finishing the polygon."
                print(msg)
                state.flash(msg, color=(0, 0, 255))
        elif key == ord('s'):
            if not state.polygon_done or state.stop_line_y is None:
                msg = "Not ready: finish the polygon (right-click or 'p') and set the stop line first."
                print(msg)
                state.flash(msg, color=(0, 0, 255))
                continue
            # Points were clicked in display space (scaled to fit the screen) -
            # convert back to the original video's pixel coordinates, which is
            # what config.py / run_detection.py operate on.
            orig_polygon = [(round(x / scale), round(y / scale)) for x, y in state.polygon_points]
            orig_stop_line_y = round(state.stop_line_y / scale)
            print("\nPaste these lines into backend/config.py:\n")
            print(f'    "{args.lane}": {orig_polygon},   # -> inside ROI_POLYGONS')
            print(f'    "{args.lane}": {orig_stop_line_y},   # -> inside STOP_LINES\n')
            state.flash("Saved! Values printed in the terminal window - go copy them.")

    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
