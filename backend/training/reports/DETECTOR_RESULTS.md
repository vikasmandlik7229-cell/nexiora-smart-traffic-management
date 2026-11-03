# Detector Evaluation Results (T3)

## mAP50 / mAP50-95 comparison: fine-tuned UVH-26 (5-class) vs stock COCO yolov8n

| Class | Fine-tuned mAP50 | Fine-tuned mAP50-95 | COCO mAP50 | COCO mAP50-95 | GT instances |
|---|---|---|---|---|---|
| car | 0.890 | 0.789 | 0.594 | 0.442 | 13642 |
| bike | 0.830 | 0.640 | 0.092 | 0.029 | 30892 |
| auto | 0.861 | 0.736 | N/A (no COCO class) | N/A | 10467 |
| bus | 0.760 | 0.656 | 0.316 | 0.260 | 2339 |
| truck | 0.770 | 0.644 | 0.219 | 0.165 | 6087 |

## Interpretation

- The fine-tuned model detects all 5 classes including `auto` (auto-rickshaws), which stock COCO structurally cannot recognise at all - it has no matching class, so every auto-rickshaw is either missed entirely or misclassified as something else by COCO.
- For car/bike/bus/truck, compare the two mAP50 columns directly: the fine-tuned model was trained specifically on this elevated-camera, Indian-traffic footage style (UVH-26), so it should outperform a generic COCO model trained on varied everyday photos.
- `bus` and `truck` have the fewest ground-truth instances of the 5 classes (see class_distribution.png) - lower scores for these two are expected and is the class imbalance already flagged during data preparation.
- This comparison runs on the UVH-26 validation set, which matches the fine-tuned model's training distribution by construction - see count_check_sheet.csv for a check against the *actual* lane videos this project uses, which is the more meaningful test.
- Numbers here are computed with a from-scratch IoU-matching + 101-point interpolated AP implementation (not ultralytics' internal validator) so that COCO's un-mapped classes can be fairly excluded rather than scored as automatic failures.