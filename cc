#!/usr/bin/env python3
"""cc — register a Claude/Codex session with metadata, then run it."""

import argparse
from datetime import datetime, timezone
import json
import os
import signal
import subprocess
import sys


REGISTRY_ENV_VAR = "AGENT_STATUS_REGISTRY"
DEFAULT_REGISTRY_PATH = os.path.expanduser("~/.agent-status/registrations.jsonl")
DEFAULT_COMMAND = ["claude"]


def current_utc_iso8601():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def resolve_registry_path(custom_path=None):
    if custom_path:
        return custom_path
    return os.environ.get(REGISTRY_ENV_VAR, DEFAULT_REGISTRY_PATH)


def ensure_registry_dir(path):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def write_registration(path, record):
    ensure_registry_dir(path)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Register a Claude/Codex session with metadata, then run it",
    )
    parser.add_argument(
        "--task",
        "-t",
        required=True,
        help="short task description to record",
    )
    parser.add_argument(
        "--registry",
        metavar="PATH",
        help="override registry path (defaults to AGENT_STATUS_REGISTRY)",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="command to run (default: claude)",
    )
    return parser.parse_args()


def build_command(args):
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        return list(DEFAULT_COMMAND)
    return command


def main():
    args = parse_args()
    command = build_command(args)
    registry_path = resolve_registry_path(args.registry)

    env = os.environ.copy()
    ghostty_surface_id = env.get("GHOSTTY_SURFACE_ID")
    cwd = os.getcwd()

    try:
        process = subprocess.Popen(command, env=env)
    except FileNotFoundError:
        sys.stderr.write(f"  Command not found: {command[0]}\n")
        return 127

    record = {
        "pid": process.pid,
        "started_at": current_utc_iso8601(),
        "cwd": cwd,
        "project": os.path.basename(cwd),
        "task": args.task,
        "command": command[0],
        "args": command[1:],
        "ghostty_surface_id": ghostty_surface_id,
        "registered_by": env.get("USER") or env.get("LOGNAME"),
    }

    try:
        write_registration(registry_path, record)
    except OSError as exc:
        sys.stderr.write(f"  Failed to write registry: {exc}\n")

    try:
        return process.wait()
    except KeyboardInterrupt:
        try:
            process.send_signal(signal.SIGINT)
        except ProcessLookupError:
            return 130
        return process.wait()


if __name__ == "__main__":
    raise SystemExit(main())
