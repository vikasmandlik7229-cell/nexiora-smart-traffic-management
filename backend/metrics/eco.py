"""Idle fuel and CO2 estimates from waiting vehicle-seconds.

Assumptions (config.py, labelled there as rough/tunable):
    IDLE_FUEL_L_PER_HOUR - litres/hour an idling vehicle burns
    CO2_KG_PER_L         - kg CO2 produced per litre of petrol burned
"""
import config


def idle_fuel_litres(waiting_vehicle_seconds: float) -> float:
    return waiting_vehicle_seconds * config.IDLE_FUEL_L_PER_HOUR / 3600.0


def co2_kg(fuel_litres: float) -> float:
    return fuel_litres * config.CO2_KG_PER_L


def savings(adaptive_waiting_s: float, fixed_waiting_s: float) -> dict:
    """Positive numbers = adaptive used less fuel / produced less CO2 than fixed."""
    adaptive_fuel = idle_fuel_litres(adaptive_waiting_s)
    fixed_fuel = idle_fuel_litres(fixed_waiting_s)
    return {
        "adaptiveFuelL": adaptive_fuel,
        "fixedFuelL": fixed_fuel,
        "fuelSavedL": fixed_fuel - adaptive_fuel,
        "adaptiveCo2Kg": co2_kg(adaptive_fuel),
        "fixedCo2Kg": co2_kg(fixed_fuel),
        "co2SavedKg": co2_kg(fixed_fuel) - co2_kg(adaptive_fuel),
    }
