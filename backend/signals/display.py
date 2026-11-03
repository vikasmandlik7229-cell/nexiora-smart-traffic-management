"""Draws realistic traffic-light + countdown overlays and the adaptive-vs-fixed
comparison panel onto a lane's video frame.
"""
import time

import cv2

LIGHT_COLORS = {
    "green": (0, 200, 0),
    "yellow": (0, 200, 220),
    "red": (0, 0, 220),
}
OFF_COLOR = (40, 40, 40)


def draw_traffic_light(frame, state: str, top_left=(10, 10)):
    """Three stacked circles (red/yellow/green), the active one lit up."""
    x, y = top_left
    radius = 14
    spacing = 32
    cv2.rectangle(frame, (x - 6, y - 6), (x + radius * 2 + 6, y + spacing * 3 + 6), (20, 20, 20), -1)
    for i, color_name in enumerate(("red", "yellow", "green")):
        center = (x + radius, y + radius + i * spacing)
        lit = color_name == state
        color = LIGHT_COLORS[color_name] if lit else OFF_COLOR
        cv2.circle(frame, center, radius, color, -1)
    return frame


def draw_countdown(frame, phase_ends_at: float, position=(10, 115)):
    remaining = max(0, int(phase_ends_at - time.time()))
    cv2.putText(frame, f"{remaining}s", position, cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
    return frame


def draw_mode_banner(frame, mode: str, position=(10, 150)):
    cv2.putText(frame, f"MODE: {mode.upper()}", position, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2, cv2.LINE_AA)
    return frame


def draw_emergency_banner(frame, lane: str, eta_s: float, position=(10, 115)):
    text = f"EMERGENCY - AMBULANCE APPROACHING ({lane}, ETA {eta_s:.0f}s)"
    cv2.rectangle(frame, (position[0] - 5, position[1] - 20), (position[0] + 560, position[1] + 10), (0, 0, 180), -1)
    cv2.putText(frame, text, position, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
    return frame


def draw_accident_suspect(frame, bbox, reason: str):
    x1, y1, x2, y2 = bbox
    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 140, 255), 3)
    cv2.putText(frame, "ACCIDENT?", (x1, max(y1 - 8, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 140, 255), 2, cv2.LINE_AA)
    return frame


def draw_accident_banner(frame, severity: str, predicted_delay_min: float, detour: str = None, position=(10, 140)):
    text = f"ACCIDENT ({severity}) - predicted delay {predicted_delay_min:.0f} min"
    if detour:
        text += f" - detour: {detour}"
    cv2.rectangle(frame, (position[0] - 5, position[1] - 20), (position[0] + 620, position[1] + 10), (0, 100, 200), -1)
    cv2.putText(frame, text, position, cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA)
    return frame


def draw_metrics_panel(frame, adaptive_summary: dict, fixed_summary: dict, eco_savings: dict, top_left=(10, 180)):
    x, y = top_left
    lines = [
        f"Avg wait  adaptive: {adaptive_summary['averageWaitSeconds']:.1f}s  "
        f"fixed: {fixed_summary['averageWaitSeconds']:.1f}s",
        f"Fuel saved: {eco_savings['fuelSavedL']:.3f} L   CO2 saved: {eco_savings['co2SavedKg']:.3f} kg",
    ]
    for i, line in enumerate(lines):
        cv2.putText(frame, line, (x, y + i * 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return frame
