"""Emergency-vehicle (ambulance/police/fire) classifier.

These weights are ADOPTED, not trained by this project - see
data/models/emergency_cls/SOURCE.md for exactly where they came from and
why (CLAUDE.md 4.2: Phase T4 was blocked, no ambulance/emergency-vehicle
dataset was ever found on this machine).

How it works: a crop of a tracked car/bus/truck is embedded with CLIP
ViT-B/16 (open_clip, pretrained tag "datacomp_xl_s13b_b90k" - this must
match exactly, since the logistic-regression probe below was trained on
that specific embedding space, not on a different CLIP checkpoint), then a
tiny logistic-regression head (just three numpy arrays - coef, intercept,
classes - no sklearn object involved at inference) scores it as
ambulance / police / fire / other.

Recognition alone never grants signal priority (CLAUDE.md safety rule 4) -
it only ever creates a `vision`-sourced emergency_requests entry and a
controller-only alert for a human to check, per the "alert_only"
VISION_EMERGENCY_POLICY default (see run_signals.py's detection_loop and
emergency/authorised.py, which deliberately skips validating these
requests against the RFID registry since they never carry a real
vehicleId/tagId).
"""
from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

import config
from detection.detector import resolve_device

MODEL_DIR = Path(config.DATA_DIR) / "models" / "emergency_cls"
CLIP_ARCH = "ViT-B-16"
CLIP_PRETRAINED = "datacomp_xl_s13b_b90k"  # must match the probe's training embedding space exactly
EMERGENCY_CLASSES = ("ambulance", "police", "fire")
VOTE_HISTORY = 5   # how many recent crops to remember per track
VOTE_TOP_N = 3      # a track's score = mean of its top-3 crops, matching the source repo's own validated method


class _Clip:
    """Lazy-loaded CLIP ViT-B/16 image encoder (open_clip). Loading this
    downloads the pretrained weights (~350MB) from the open_clip/Hugging
    Face hub the first time it ever runs on this machine, then caches
    them locally - needs one internet connection, not one per run."""

    def __init__(self, device: str):
        import open_clip
        self.device = device
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            CLIP_ARCH, pretrained=CLIP_PRETRAINED, device=device)
        self.model.eval()

    def embed(self, crops_bgr: List[np.ndarray]) -> np.ndarray:
        """OpenCV-style BGR numpy crops -> (n, 512) L2-normalised embeddings."""
        import torch
        if not crops_bgr:
            return np.zeros((0, 512), dtype=np.float32)
        batch = [self.preprocess(Image.fromarray(c[..., ::-1])) for c in crops_bgr]
        with torch.no_grad():
            x = torch.stack(batch).to(self.device)
            e = self.model.encode_image(x).float()
            e = e / e.norm(dim=-1, keepdim=True)
        return e.cpu().numpy()


class EmergencyClassifier:
    """Scores cropped vehicle images for ambulance/police/fire vs normal.
    Use with TrackVotes (below) for a stable per-track decision rather than
    trusting any single frame."""

    def __init__(self, model_dir: Path = MODEL_DIR, device: Optional[str] = None):
        probe_path = model_dir / "probe.npz"
        op_path = model_dir / "operating_point.json"
        if not probe_path.exists() or not op_path.exists():
            raise FileNotFoundError(
                f"Emergency classifier weights not found under {model_dir} - "
                f"see data/models/emergency_cls/SOURCE.md.")

        z = np.load(probe_path)
        self.coef = z["coef"]                              # (4, 512)
        self.intercept = z["intercept"]                     # (4,)
        self.classes = [str(c) for c in z["classes"]]        # e.g. ["ambulance","police","fire","other"]
        self.emergency_idx = [self.classes.index(c) for c in EMERGENCY_CLASSES]

        self.operating_point = json.loads(op_path.read_text())
        self.t_exempt = self.operating_point["t_exempt"]
        self.t_review = self.operating_point["t_review"]

        self.device = device or resolve_device()
        self._clip: Optional[_Clip] = None   # created on first real use, not at import time

    def _ensure_clip(self):
        if self._clip is None:
            print(f"EmergencyClassifier: loading CLIP {CLIP_ARCH} ({CLIP_PRETRAINED}) on "
                  f"{self.device} (first use only)...")
            self._clip = _Clip(self.device)

    def score_crops(self, crops_bgr: List[np.ndarray]) -> List[Tuple[float, str]]:
        """-> one (emergency_probability, most_likely_type) per crop.
        emergency_probability = P(ambulance) + P(police) + P(fire), the
        same "probe_em" metric operating_point.json's thresholds were
        tuned against - never just the raw "ambulance" column alone."""
        if not crops_bgr:
            return []
        self._ensure_clip()
        E = self._clip.embed(crops_bgr)                       # (n, 512)
        logits = E @ self.coef.T + self.intercept              # (n, 4)
        exp = np.exp(logits - logits.max(axis=1, keepdims=True))
        probs = exp / exp.sum(axis=1, keepdims=True)
        out = []
        for row in probs:
            em_probs = row[self.emergency_idx]
            em_score = float(em_probs.sum())
            best_type = EMERGENCY_CLASSES[int(np.argmax(em_probs))]
            out.append((em_score, best_type))
        return out

    def status_for_score(self, score: Optional[float]) -> Optional[str]:
        if score is None:
            return None
        if score >= self.t_exempt:
            return "exempt"
        if score >= self.t_review:
            return "review"
        return None


class TrackVotes:
    """Per-track rolling history of classifier scores, turned into one
    stable decision instead of trusting a single frame - mirrors the source
    repo's own method (mean of a track's 3 highest-scoring crops)."""

    def __init__(self, history: int = VOTE_HISTORY, top_n: int = VOTE_TOP_N):
        self._top_n = top_n
        self._scores: Dict[int, deque] = defaultdict(lambda: deque(maxlen=history))
        self._types: Dict[int, deque] = defaultdict(lambda: deque(maxlen=history))

    def add(self, track_id: int, score: float, vehicle_type: str) -> None:
        self._scores[track_id].append(score)
        self._types[track_id].append(vehicle_type)

    def track_score(self, track_id: int) -> Optional[float]:
        scores = self._scores.get(track_id)
        if not scores:
            return None
        top = sorted(scores)[-self._top_n:]
        return float(np.mean(top))

    def track_type(self, track_id: int) -> Optional[str]:
        types = self._types.get(track_id)
        if not types:
            return None
        return max(set(types), key=list(types).count)

    def forget(self, track_id: int) -> None:
        self._scores.pop(track_id, None)
        self._types.pop(track_id, None)
