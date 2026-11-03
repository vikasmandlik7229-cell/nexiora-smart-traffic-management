"""Phase 4: listens for pending `commands` documents (manual overrides sent
from the controller dashboard) and applies them through the signal
controller's own safety-checked methods - never touches controller internals
directly, so the yellow-before-red / MAX_OVERRIDE_SECONDS guarantees always
hold regardless of what the dashboard requests.
"""
import threading
import time
from typing import Dict, Tuple

import config
from db.sql_client import get_client
from signals.controller import SignalController


def process_command(cmd: dict, controllers: Dict[str, SignalController]) -> Tuple[str, str]:
    """Returns (status, reason)."""
    junction_id = cmd.get("junctionId")
    controller = controllers.get(junction_id)
    if controller is None:
        return "rejected", f"unknown junction {junction_id}"

    cmd_type = cmd.get("type")
    if cmd_type == "force_green":
        lane = cmd.get("laneId")
        if lane not in controller.lanes:
            return "rejected", f"unknown lane {lane}"
        duration = min(cmd.get("durationS", config.MAX_OVERRIDE_SECONDS), config.MAX_OVERRIDE_SECONDS)
        controller.force_green(lane, duration)
        return "done", f"forced {lane} green for {duration}s"
    if cmd_type == "release":
        controller.release()
        return "done", "override released"
    return "rejected", f"unknown command type '{cmd_type}'"


def run_command_listener(controllers: Dict[str, SignalController], poll_interval: float = 2.0,
                          stop_event: threading.Event = None):
    client = get_client()
    stop_event = stop_event or threading.Event()
    while not stop_event.is_set():
        try:
            for cmd in client.read_pending("commands"):
                status, reason = process_command(cmd, controllers)
                client.write_command_status(cmd["id"], {"status": status, "reason": reason})
                print(f"Command {cmd['id']} ({cmd.get('type')} @ {cmd.get('junctionId')}): {status} - {reason}")
        except Exception as exc:
            # A transient database hiccup must not permanently kill this
            # daemon thread - log and retry next poll instead.
            print(f"run_command_listener: database error, will retry: {exc}")
        time.sleep(poll_interval)


def start_background(controllers: Dict[str, SignalController], poll_interval: float = 2.0):
    stop_event = threading.Event()
    thread = threading.Thread(target=run_command_listener, args=(controllers, poll_interval, stop_event), daemon=True)
    thread.start()
    return thread, stop_event
