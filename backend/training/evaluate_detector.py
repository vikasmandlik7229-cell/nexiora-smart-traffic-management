"""Phase T3: evaluate the fine-tuned UVH-26 detector two ways.

1. Compare mAP50/mAP50-95/precision/recall against stock COCO yolov8n on
   the same UVH-26 val set, with COCO's classes remapped onto ours
   (car/bike/bus/truck - COCO has no "auto" class, reported honestly as
   not detectable rather than silently scored as 0).
2. Sample 20 frames per real lane video, run both models, save side-by-side
   crops to reports/count_check/ with a CSV for manually typing true counts
   and comparing count error.

Run from backend/training/, with venv_train active:
    python evaluate_detector.py
"""
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import matplotlib.pyplot as plt
import numpy as np
from ultralytics import YOLO

import config

HERE = Path(__file__).resolve().parent
REPORTS_DIR = HERE / "reports"
COUNT_CHECK_DIR = REPORTS_DIR / "count_check"
YOLO_ROOT = HERE / "uvh26_yolo"
FINE_TUNED_WEIGHTS = HERE / "runs" / "uvh26_v8n_5cls" / "weights" / "best.pt"

OUR_CLASSES = ["car", "bike", "auto", "bus", "truck"]

# COCO class id -> our class name. COCO has no auto-rickshaw equivalent.
COCO_TO_OURS = {2: "car", 3: "bike", 1: "bike", 5: "bus", 7: "truck"}
COCO_CLASS_IDS = list(set(COCO_TO_OURS.keys()))


def load_yolo_labels(label_path: Path, img_w: int, img_h: int):
    """Returns list of (class_name, [x1,y1,x2,y2]) in pixel coords."""
    if not label_path.exists() or not label_path.read_text().strip():
        return []
    boxes = []
    for line in label_path.read_text().strip().splitlines():
        cls_id, xc, yc, bw, bh = line.split()
        cls_id, xc, yc, bw, bh = int(cls_id), float(xc), float(yc), float(bw), float(bh)
        x1 = (xc - bw / 2) * img_w
        y1 = (yc - bh / 2) * img_h
        x2 = (xc + bw / 2) * img_w
        y2 = (yc + bh / 2) * img_h
        boxes.append((OUR_CLASSES[cls_id], [x1, y1, x2, y2]))
    return boxes


def iou(box_a, box_b) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def average_precision(detections, num_gt: int, iou_threshold: float) -> float:
    """detections: list of (confidence, matched_iou) for one class, already
    sorted by confidence descending with each GT matched to at most one
    detection (greedy, highest-confidence-first, standard VOC/COCO style)."""
    if num_gt == 0:
        return 0.0
    tp = np.array([1 if d[1] >= iou_threshold else 0 for d in detections])
    fp = 1 - tp
    tp_cum = np.cumsum(tp)
    fp_cum = np.cumsum(fp)
    recall = tp_cum / num_gt
    precision = tp_cum / np.maximum(tp_cum + fp_cum, 1e-9)

    # 101-point interpolation (COCO style)
    ap = 0.0
    for t in np.linspace(0, 1, 101):
        p = precision[recall >= t].max() if np.any(recall >= t) else 0.0
        ap += p / 101
    return ap


def match_detections_to_gt(all_preds_by_class, all_gts_by_class):
    """all_preds_by_class[cls] = list of (confidence, box, image_id), sorted
    by confidence descending across the whole dataset.
    all_gts_by_class[cls] = {image_id: [box, box, ...]}
    Returns {cls: list of (confidence, best_iou)} for AP computation."""
    results = {}
    for cls, preds in all_preds_by_class.items():
        gts = all_gts_by_class.get(cls, {})
        matched = {img_id: [False] * len(boxes) for img_id, boxes in gts.items()}
        out = []
        for conf, box, img_id in sorted(preds, key=lambda p: -p[0]):
            gt_boxes = gts.get(img_id, [])
            best_iou, best_idx = 0.0, -1
            for i, gt_box in enumerate(gt_boxes):
                if matched[img_id][i]:
                    continue
                v = iou(box, gt_box)
                if v > best_iou:
                    best_iou, best_idx = v, i
            if best_idx >= 0:
                matched[img_id][best_idx] = True
            out.append((conf, best_iou))
        results[cls] = out
    return results


def evaluate_model_on_val(model_path: str, class_map: dict, classes_to_score, is_coco: bool):
    """Runs `model_path` over the UVH-26 val set and computes mAP50/mAP50-95
    per class in classes_to_score. class_map maps the model's own class id
    to our class names (identity map for the fine-tuned model, COCO_TO_OURS
    for stock COCO)."""
    model = YOLO(model_path)
    val_images_dir = YOLO_ROOT / "images" / "val"
    val_labels_dir = YOLO_ROOT / "labels" / "val"
    image_paths = sorted(val_images_dir.glob("*"))

    preds_by_class = defaultdict(list)
    gts_by_class = defaultdict(lambda: defaultdict(list))
    gt_counts = defaultdict(int)

    class_ids = list(class_map.keys())
    for img_id, img_path in enumerate(image_paths):
        img = cv2.imread(str(img_path))
        h, w = img.shape[:2]
        label_path = val_labels_dir / f"{img_path.stem}.txt"
        for cls_name, box in load_yolo_labels(label_path, w, h):
            gts_by_class[cls_name][img_id].append(box)
            gt_counts[cls_name] += 1

        results = model.predict(img, classes=class_ids, conf=0.25, verbose=False)[0]
        if results.boxes is None:
            continue
        for box, cls_id, conf in zip(results.boxes.xyxy.cpu().numpy(),
                                      results.boxes.cls.cpu().numpy(),
                                      results.boxes.conf.cpu().numpy()):
            cls_name = class_map.get(int(cls_id))
            if cls_name is None:
                continue
            preds_by_class[cls_name].append((float(conf), box.tolist(), img_id))

    matched = match_detections_to_gt(preds_by_class, gts_by_class)

    per_class = {}
    for cls in classes_to_score:
        if is_coco and cls == "auto":
            per_class[cls] = {"mAP50": None, "mAP50_95": None, "note": "not detectable (no COCO equivalent)"}
            continue
        dets = matched.get(cls, [])
        map50 = average_precision(dets, gt_counts[cls], 0.5)
        aps = [average_precision(dets, gt_counts[cls], t) for t in np.arange(0.5, 1.0, 0.05)]
        per_class[cls] = {"mAP50": map50, "mAP50_95": float(np.mean(aps)), "gtCount": gt_counts[cls]}

    return per_class


def run_val_comparison():
    print("Evaluating fine-tuned model (5 classes)...")
    finetuned_results = evaluate_model_on_val(
        str(FINE_TUNED_WEIGHTS), {i: name for i, name in enumerate(OUR_CLASSES)}, OUR_CLASSES, is_coco=False,
    )

    print("Evaluating stock COCO yolov8n (remapped classes)...")
    coco_results = evaluate_model_on_val(
        "yolov8n.pt", COCO_TO_OURS, OUR_CLASSES, is_coco=True,
    )

    return finetuned_results, coco_results


def sample_lane_frames(n_per_lane=20):
    COUNT_CHECK_DIR.mkdir(parents=True, exist_ok=True)
    finetuned = YOLO(str(FINE_TUNED_WEIGHTS))
    coco = YOLO("yolov8n.pt")

    rows = []
    for lane, video_path in config.LANE_VIDEOS.items():
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            print(f"Skipping {lane}: could not read frame count from {video_path}")
            continue
        frame_indices = sorted(random.sample(range(total_frames), min(n_per_lane, total_frames)))

        for idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue

            ft_res = finetuned.predict(frame, conf=0.25, verbose=False)[0]
            coco_res = coco.predict(frame, classes=COCO_CLASS_IDS, conf=0.25, verbose=False)[0]
            ft_count = 0 if ft_res.boxes is None else len(ft_res.boxes)
            coco_count = 0 if coco_res.boxes is None else len(coco_res.boxes)

            ft_frame = ft_res.plot()
            coco_frame = coco_res.plot()
            side_by_side = np.hstack([
                cv2.resize(ft_frame, (640, 480)),
                cv2.resize(coco_frame, (640, 480)),
            ])
            out_name = f"{lane}_frame{idx}.jpg"
            cv2.imwrite(str(COUNT_CHECK_DIR / out_name), side_by_side)

            rows.append({
                "lane": lane, "frame": idx, "image": out_name,
                "finetuned_count": ft_count, "coco_count": coco_count, "true_count": "",
            })
        cap.release()
        print(f"  {lane}: sampled {len(frame_indices)} frames")

    csv_path = REPORTS_DIR / "count_check_sheet.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["lane", "frame", "image", "finetuned_count", "coco_count", "true_count"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} sample frames to {COUNT_CHECK_DIR} and sheet to {csv_path}")
    print("Left half of each image = fine-tuned model, right half = stock COCO.")
    print("Fill in the 'true_count' column by eye, then compare against finetuned_count/coco_count.")


def write_report(finetuned_results, coco_results):
    REPORTS_DIR.mkdir(exist_ok=True)

    lines = [
        "# Detector Evaluation Results (T3)",
        "",
        "## mAP50 / mAP50-95 comparison: fine-tuned UVH-26 (5-class) vs stock COCO yolov8n",
        "",
        "| Class | Fine-tuned mAP50 | Fine-tuned mAP50-95 | COCO mAP50 | COCO mAP50-95 | GT instances |",
        "|---|---|---|---|---|---|",
    ]
    for cls in OUR_CLASSES:
        ft = finetuned_results[cls]
        co = coco_results[cls]
        co_map50 = "N/A (no COCO class)" if co["mAP50"] is None else f"{co['mAP50']:.3f}"
        co_map5095 = "N/A" if co["mAP50_95"] is None else f"{co['mAP50_95']:.3f}"
        lines.append(f"| {cls} | {ft['mAP50']:.3f} | {ft['mAP50_95']:.3f} | {co_map50} | {co_map5095} | {ft['gtCount']} |")

    lines += [
        "",
        "## Interpretation",
        "",
        "- The fine-tuned model detects all 5 classes including `auto` (auto-rickshaws), which "
        "stock COCO structurally cannot recognise at all - it has no matching class, so every "
        "auto-rickshaw is either missed entirely or misclassified as something else by COCO.",
        "- For car/bike/bus/truck, compare the two mAP50 columns directly: the fine-tuned model "
        "was trained specifically on this elevated-camera, Indian-traffic footage style (UVH-26), "
        "so it should outperform a generic COCO model trained on varied everyday photos.",
        "- `bus` and `truck` have the fewest ground-truth instances of the 5 classes (see "
        "class_distribution.png) - lower scores for these two are expected and is the class "
        "imbalance already flagged during data preparation.",
        "- This comparison runs on the UVH-26 validation set, which matches the fine-tuned "
        "model's training distribution by construction - see count_check_sheet.csv for a check "
        "against the *actual* lane videos this project uses, which is the more meaningful test.",
        "- Numbers here are computed with a from-scratch IoU-matching + 101-point interpolated AP "
        "implementation (not ultralytics' internal validator) so that COCO's un-mapped classes "
        "can be fairly excluded rather than scored as automatic failures.",
    ]
    (REPORTS_DIR / "DETECTOR_RESULTS.md").write_text("\n".join(lines))
    print(f"Saved {REPORTS_DIR / 'DETECTOR_RESULTS.md'}")

    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(OUR_CLASSES))
    width = 0.35
    ft_vals = [finetuned_results[c]["mAP50"] for c in OUR_CLASSES]
    co_vals = [0 if coco_results[c]["mAP50"] is None else coco_results[c]["mAP50"] for c in OUR_CLASSES]
    ax.bar(x - width / 2, ft_vals, width, label="fine-tuned (UVH-26)")
    ax.bar(x + width / 2, co_vals, width, label="stock COCO")
    ax.set_xticks(x)
    ax.set_xticklabels(OUR_CLASSES)
    ax.set_ylabel("mAP50")
    ax.set_title("Fine-tuned vs stock COCO (COCO bar = 0 where class doesn't exist)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "finetuned_vs_coco.png")
    print(f"Saved {REPORTS_DIR / 'finetuned_vs_coco.png'}")


def main():
    finetuned_results, coco_results = run_val_comparison()
    write_report(finetuned_results, coco_results)

    print("\nSampling real lane-video frames for a manual count check...")
    sample_lane_frames()

    (REPORTS_DIR / "eval_raw_results.json").write_text(json.dumps(
        {"finetuned": finetuned_results, "coco": coco_results}, indent=2, default=str))


if __name__ == "__main__":
    main()
