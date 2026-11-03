"""Predicted queue growth and extra delay from an accident, using a simple
arrival-rate x clearance-time model. Explicitly a labelled assumption (per
CLAUDE.md section 10), not a calibrated traffic model: clearance times per
severity are illustrative, tune them against real incident data if you
ever have it.
"""
import config

CLEARANCE_MINUTES = {"low": 5, "medium": 15, "high": 30, "critical": 60}


def predicted_impact(severity: str, arrival_rate_pcu_per_min: float, lane_capacity_pcu: float = None) -> dict:
    lane_capacity_pcu = lane_capacity_pcu if lane_capacity_pcu is not None else config.LANE_CAPACITY_PCU
    clearance_min = CLEARANCE_MINUTES.get(severity, CLEARANCE_MINUTES["medium"])
    predicted_queue_pcu = arrival_rate_pcu_per_min * clearance_min
    overflow_pcu = max(0.0, predicted_queue_pcu - lane_capacity_pcu)
    extra_delay_min = overflow_pcu / max(arrival_rate_pcu_per_min, 0.1)

    return {
        "severity": severity,
        "clearanceMinutes": clearance_min,
        "arrivalRatePcuPerMin": arrival_rate_pcu_per_min,
        "predictedQueuePcu": predicted_queue_pcu,
        "predictedDelayMin": extra_delay_min,
        "congestionLevel": "high" if overflow_pcu > 0 else ("medium" if predicted_queue_pcu > lane_capacity_pcu * 0.5 else "low"),
    }
