"""Non-interactive FPS benchmark: CPU vs GPU detection speed on one lane video.

Run from backend/venv:
    python tools/bench_fps.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2

import config
from detection.detector import VehicleDetector


def resize_for_detection(frame):
    h, w = frame.shape[:2]
    scale = config.DETECTION_RESIZE_WIDTH / w
    return cv2.resize(frame, (config.DETECTION_RESIZE_WIDTH, int(h * scale)))


def bench(device: str, n_frames: int = 60) -> float:
    cap = cv2.VideoCapture(config.LANE_VIDEOS["lane1"])
    if not cap.isOpened():
        raise RuntimeError("Could not open lane1 video")

    detector = VehicleDetector()
    detector.device = device
    detector.model.to(device)

    frames = []
    for _ in range(n_frames):
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
        frames.append(resize_for_detection(frame))
    cap.release()

    # Warm up (first call pays model/CUDA init cost)
    detector.detect(frames[0])

    start = time.time()
    for frame in frames:
        detector.detect(frame)
    elapsed = time.time() - start
    return n_frames / elapsed


def main():
    print(f"Benchmarking on {config.LANE_VIDEOS['lane1']}, {config.DETECTION_RESIZE_WIDTH}px width\n")

    cpu_fps = bench("cpu")
    print(f"CPU:  {cpu_fps:.1f} FPS")

    import torch
    if torch.cuda.is_available():
        gpu_fps = bench("cuda")
        print(f"GPU:  {gpu_fps:.1f} FPS  ({gpu_fps / cpu_fps:.1f}x CPU)")
    else:
        print("GPU:  not available in this venv")


if __name__ == "__main__":
    main()
