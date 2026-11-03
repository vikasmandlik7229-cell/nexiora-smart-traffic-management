"""Phase 2a/T1/T2: fine-tune yolov8n (or yolov8s) on UVH-26 using the local GPU.

Run from the separate CUDA-enabled venv at backend/training/venv_train,
never the project's main CPU-only venv - see CLAUDE.md section 4.5.

    python finetune_uvh26.py login      # once, paste an HF token when prompted
    python finetune_uvh26.py download
    python finetune_uvh26.py inspect    # look at uvh26_sample_check.png before continuing
    python finetune_uvh26.py convert    # full conversion: copies images + writes labels (4-class, legacy)
    python finetune_uvh26.py relabel    # fast path: rewrite labels only (5-class), reuses images already in uvh26_yolo/
    python finetune_uvh26.py report     # class distribution chart + sample label-check images
    python finetune_uvh26.py train --model yolov8n.pt --epochs 1 --fraction 0.05   # smoke test
    python finetune_uvh26.py train --model yolov8n.pt --epochs 50 --name uvh26_v8n_5cls

Annotation format (confirmed against the actual downloaded JSON, not just
the dataset card): plain COCO - top-level `images` / `annotations` /
`categories` lists, `bbox` is `[x, y, width, height]` in absolute pixels
(confirmed via `area` == width*height on real records), category ids are
1-14 with "Others" as the catch-all (not "Other").
"""
import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASET_DIR = HERE / "uvh26_data"
OUT_ROOT = HERE / "uvh26_yolo"
RUNS_DIR = HERE / "runs"

REPO_ID = "Vikas-mandlik/UVH-26-bucket"

# 5-class mapping (CLAUDE.md v3 section 4.1). Three-wheeler is its own
# "auto" class now (previously folded into car); Tempo-traveller moved
# from truck to bus. Order here fixes the trained model's class ids.
CLASS_MAP = {
    "Hatchback": "car", "Sedan": "car", "SUV": "car", "MUV": "car", "Van": "car",
    "Two-wheeler": "bike", "Bicycle": "bike",
    "Three-wheeler": "auto",
    "Bus": "bus", "Mini-bus": "bus", "Tempo-traveller": "bus",
    "Truck": "truck", "LCV": "truck",
    "Others": None,  # dropped - not a vehicle class the project tracks
}
TARGET_CLASSES = ["car", "bike", "auto", "bus", "truck"]  # final ids 0-4
TARGET_ID = {name: i for i, name in enumerate(TARGET_CLASSES)}


def step_login():
    from huggingface_hub import login

    login()


def step_download():
    import subprocess

    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    cmd = ["hf", "sync", f"hf://buckets/{REPO_ID}", str(DATASET_DIR)]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def _build_image_index(images_dir):
    """Images are sharded under images_dir/data/000/, /001/, etc, not flat."""
    data_dir = images_dir / "data"
    search_root = data_dir if data_dir.is_dir() else images_dir
    return {p.name: p for p in search_root.rglob("*") if p.is_file()}


def _load_coco(json_path):
    """Returns (images_by_id, anns_by_image_id, category_id_to_name)."""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    images_by_id = {img["id"]: img for img in data["images"]}
    anns_by_image = defaultdict(list)
    for ann in data["annotations"]:
        anns_by_image[ann["image_id"]].append(ann)
    category_id_to_name = {c["id"]: c["name"] for c in data["categories"]}
    return images_by_id, anns_by_image, category_id_to_name


def step_inspect():
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from PIL import Image

    train_dir = DATASET_DIR / "UVH-26-Train"
    json_path = train_dir / "UVH-26-MV-Train.json"
    images_by_id, anns_by_image, cat_names = _load_coco(json_path)
    print(f"{len(images_by_id)} images, {sum(len(v) for v in anns_by_image.values())} annotations")
    print("categories:", cat_names)

    print("Indexing image files under data/ (sharded into subfolders)...")
    file_index = _build_image_index(train_dir)
    print(f"found {len(file_index)} image files on disk")

    img_id = next(iter(images_by_id))
    img_rec = images_by_id[img_id]
    anns = anns_by_image[img_id]
    print("sample image record:", img_rec)
    print(f"{len(anns)} annotations on this image, first few:", anns[:3])

    img_path = file_index[img_rec["file_name"]]
    img = Image.open(img_path)

    fig, ax = plt.subplots(1, figsize=(12, 8))
    ax.imshow(img)
    for ann in anns:
        x, y, w, h = ann["bbox"]
        cls_name = cat_names[ann["category_id"]]
        rect = patches.Rectangle((x, y), w, h, linewidth=2, edgecolor="lime", facecolor="none")
        ax.add_patch(rect)
        ax.text(x, max(y - 4, 0), cls_name, color="lime", fontsize=9)

    out_path = HERE / "uvh26_sample_check.png"
    fig.savefig(out_path)
    print(f"Saved annotated sample to {out_path} - open it and confirm the boxes tightly fit the vehicles.")


def _yolo_lines_for_image(img_rec, anns):
    img_w, img_h = img_rec["width"], img_rec["height"]
    lines = []
    for ann in anns:
        target = CLASS_MAP.get(ann["_cls_name"])
        if target is None:
            continue
        x, y, w, h = ann["bbox"]
        x1, x2 = sorted((max(0, x), min(img_w, x + w)))
        y1, y2 = sorted((max(0, y), min(img_h, y + h)))
        if x2 <= x1 or y2 <= y1:
            continue
        xc, yc = ((x1 + x2) / 2) / img_w, ((y1 + y2) / 2) / img_h
        bw, bh = (x2 - x1) / img_w, (y2 - y1) / img_h
        lines.append(f"{TARGET_ID[target]} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
    return lines


def _write_data_yaml():
    names_block = "\n".join(f"  {i}: {name}" for i, name in enumerate(TARGET_CLASSES))
    yaml_content = (
        f"path: {OUT_ROOT}\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n"
        f"{names_block}\n"
    )
    (OUT_ROOT / "data.yaml").write_text(yaml_content)
    print(yaml_content)


def _convert_split(split, json_path, images_dir):
    """Full conversion: copies images AND writes labels. Use for a fresh dataset."""
    from tqdm import tqdm

    images_by_id, anns_by_image, cat_names = _load_coco(json_path)
    file_index = _build_image_index(images_dir)

    (OUT_ROOT / "images" / split).mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "labels" / split).mkdir(parents=True, exist_ok=True)

    kept = 0
    for img_id, img_rec in tqdm(images_by_id.items(), desc=split):
        src_img = file_index.get(img_rec["file_name"])
        if src_img is None or not src_img.exists():
            continue
        anns = anns_by_image.get(img_id, [])
        for a in anns:
            a["_cls_name"] = cat_names[a["category_id"]]
        lines = _yolo_lines_for_image(img_rec, anns)

        shutil.copy(src_img, OUT_ROOT / "images" / split / src_img.name)
        (OUT_ROOT / "labels" / split / (src_img.stem + ".txt")).write_text("\n".join(lines))
        kept += 1
    print(f"{split}: {kept} images converted")


def step_convert():
    _convert_split("train", DATASET_DIR / "UVH-26-Train" / "UVH-26-MV-Train.json", DATASET_DIR / "UVH-26-Train")
    _convert_split("val", DATASET_DIR / "UVH-26-Val" / "UVH-26-MV-Val.json", DATASET_DIR / "UVH-26-Val")
    _write_data_yaml()


def _relabel_split(split, json_path):
    """Fast path: images already copied under OUT_ROOT/images/{split}/ from an
    earlier `convert` run. Only rewrite labels/{split}/*.txt against the
    current CLASS_MAP/TARGET_CLASSES - no image I/O, no re-download needed."""
    from tqdm import tqdm

    images_by_id, anns_by_image, cat_names = _load_coco(json_path)
    existing_images = {p.name for p in (OUT_ROOT / "images" / split).glob("*")}

    labels_dir = OUT_ROOT / "labels" / split
    labels_dir.mkdir(parents=True, exist_ok=True)

    kept = 0
    for img_id, img_rec in tqdm(images_by_id.items(), desc=f"relabel-{split}"):
        file_name = img_rec["file_name"]
        if file_name not in existing_images:
            continue
        anns = anns_by_image.get(img_id, [])
        for a in anns:
            a["_cls_name"] = cat_names[a["category_id"]]
        lines = _yolo_lines_for_image(img_rec, anns)

        stem = Path(file_name).stem
        (labels_dir / f"{stem}.txt").write_text("\n".join(lines))
        kept += 1
    print(f"{split}: {kept} labels rewritten (5-class)")


def step_relabel():
    if not (OUT_ROOT / "images" / "train").exists():
        print("No existing uvh26_yolo/images/train found - run `convert` first (full copy), not `relabel`.")
        return
    _relabel_split("train", DATASET_DIR / "UVH-26-Train" / "UVH-26-MV-Train.json")
    _relabel_split("val", DATASET_DIR / "UVH-26-Val" / "UVH-26-MV-Val.json")
    _write_data_yaml()


def step_report():
    import random

    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from PIL import Image

    reports_dir = HERE / "reports"
    reports_dir.mkdir(exist_ok=True)
    label_check_dir = reports_dir / "label_check"
    label_check_dir.mkdir(exist_ok=True)

    # --- class distribution ---
    counts = {split: {name: 0 for name in TARGET_CLASSES} for split in ("train", "val")}
    for split in ("train", "val"):
        for label_file in (OUT_ROOT / "labels" / split).glob("*.txt"):
            text = label_file.read_text().strip()
            if not text:
                continue
            for line in text.splitlines():
                cls_id = int(line.split()[0])
                counts[split][TARGET_CLASSES[cls_id]] += 1

    print("Class instance counts:")
    for split in ("train", "val"):
        print(f"  {split}: {counts[split]}")
        small = [c for c, n in counts[split].items() if n < 500]
        if small:
            print(f"  WARNING: small classes in {split} (<500 instances): {small}")

    fig, ax = plt.subplots(figsize=(8, 5))
    x = range(len(TARGET_CLASSES))
    width = 0.35
    ax.bar([i - width / 2 for i in x], [counts["train"][c] for c in TARGET_CLASSES], width, label="train")
    ax.bar([i + width / 2 for i in x], [counts["val"][c] for c in TARGET_CLASSES], width, label="val")
    ax.set_xticks(list(x))
    ax.set_xticklabels(TARGET_CLASSES)
    ax.set_ylabel("instance count")
    ax.set_title("UVH-26 class distribution (5-class mapping)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(reports_dir / "class_distribution.png")
    print(f"Saved {reports_dir / 'class_distribution.png'}")

    # --- 6 random label-check images ---
    train_images = list((OUT_ROOT / "images" / "train").glob("*"))
    sample = random.sample(train_images, min(6, len(train_images)))
    for img_path in sample:
        label_path = OUT_ROOT / "labels" / "train" / f"{img_path.stem}.txt"
        img = Image.open(img_path)
        fig, ax = plt.subplots(figsize=(10, 7))
        ax.imshow(img)
        if label_path.exists() and label_path.read_text().strip():
            for line in label_path.read_text().strip().splitlines():
                cls_id, xc, yc, bw, bh = line.split()
                cls_id, xc, yc, bw, bh = int(cls_id), float(xc), float(yc), float(bw), float(bh)
                w, h = img.width, img.height
                x1 = (xc - bw / 2) * w
                y1 = (yc - bh / 2) * h
                rect = patches.Rectangle((x1, y1), bw * w, bh * h, linewidth=2, edgecolor="lime", facecolor="none")
                ax.add_patch(rect)
                ax.text(x1, max(y1 - 4, 0), TARGET_CLASSES[cls_id], color="lime", fontsize=9)
        fig.savefig(label_check_dir / f"{img_path.stem}.png")
        plt.close(fig)
    print(f"Saved {len(sample)} label-check images to {label_check_dir}")


def step_train(args):
    import torch
    from ultralytics import YOLO

    if not torch.cuda.is_available():
        print(
            "WARNING: CUDA not available in this environment. Make sure "
            "you're running from backend/training/venv_train with the "
            "CUDA-enabled torch install, not the project's main CPU-only "
            "venv - training on CPU is not practical for this dataset size."
        )
    else:
        print(f"Training on GPU: {torch.cuda.get_device_name(0)}")

    if args.resume:
        model = YOLO(RUNS_DIR / args.name / "weights" / "last.pt")
        model.train(resume=True)
        return

    model = YOLO(args.model)
    model.train(
        data=str(OUT_ROOT / "data.yaml"),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        fraction=args.fraction,
        device=0,
        patience=15,
        seed=0,
        workers=4,
        cache=False,
        amp=True,
        project=str(RUNS_DIR),
        name=args.name,
    )
    best = RUNS_DIR / args.name / "weights" / "best.pt"
    print(f"Done. Copy {best} into backend/data/models/ and update config.py + detector.py.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="step", required=True)

    for name in ("login", "download", "inspect", "convert", "relabel", "report"):
        sub.add_parser(name)

    train_p = sub.add_parser("train")
    train_p.add_argument("--model", default="yolov8n.pt")
    train_p.add_argument("--epochs", type=int, default=50)
    train_p.add_argument("--imgsz", type=int, default=640)
    train_p.add_argument("--batch", type=int, default=16)
    train_p.add_argument("--fraction", type=float, default=1.0)
    train_p.add_argument("--name", default="uvh26_v8n_5cls")
    train_p.add_argument("--resume", action="store_true")

    args = parser.parse_args()
    if args.step == "train":
        step_train(args)
    else:
        {
            "login": step_login,
            "download": step_download,
            "inspect": step_inspect,
            "convert": step_convert,
            "relabel": step_relabel,
            "report": step_report,
        }[args.step]()


if __name__ == "__main__":
    main()
