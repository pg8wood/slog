#!/usr/bin/env python3
"""Interactive helper for `slog learn` that chats with OpenAI and writes scripts."""

import argparse
import json
import os
import re
import shlex
import sys
import textwrap
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional


OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
SYSTEM_PROMPT = textwrap.dedent(
    """
    You are Slog Learn, an automation planner plugged into the iOS Simulator MCP.
    Use AXe-style commands (tap/type) to operate the simulator. Always ask a concise
    follow-up question if you lack critical details before attempting to plan.

    When you have enough information to describe the automation flow, respond with
    ONLY a JSON object using this schema (do not wrap it in markdown):
    {
      "script_name": "lowercase-kebab-case-name",
      "description": "Short summary of what the script accomplishes",
      "steps": [
        {"action": "tap", "x": 0, "y": 0, "comment": "What this tap does"},
        {"action": "type", "text": "value to type", "comment": "Context"},
        {"action": "wait", "ms": 500, "comment": "Why we wait"},
        {"action": "run", "command": "axe something --flag", "comment": "Optional"}
      ]
    }

    Rules:
      - Supported actions: tap, type, wait, run.
      - Every tap MUST include explicit numeric coordinates (x, y) in simulator points.
      - Type steps must include the literal text to send.
      - Wait steps should use milliseconds (integer).
      - Run steps are for arbitrary shell commands (rare).
      - Provide a concise comment for every step so humans can understand it.
      - Do not emit the JSON payload until you are confident the plan is correct.
      - Outside of the final JSON response, converse naturally and feel free to ask
        clarifying questions.
    """
).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Guide OpenAI to learn a new slog script.")
    parser.add_argument("--config", required=True, help="Path to ~/.slog.json")
    parser.add_argument(
        "--model",
        default=os.environ.get("SLOG_OPENAI_MODEL", DEFAULT_MODEL),
        help=f"OpenAI model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Sampling temperature for OpenAI completions (default: 0.2)",
    )
    return parser.parse_args()


def load_config(config_path: str) -> Dict[str, Any]:
    if not os.path.exists(config_path):
        sys.exit(f"No slog config found at {config_path}. Run 'slog setup' first.")
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        sys.exit(f"Config at {config_path} is not valid JSON: {exc}")


def ensure_openai_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit("OPENAI_API_KEY is not set. Export it before running 'slog learn'.")
    return api_key


def call_openai(
    api_key: str,
    model: str,
    temperature: float,
    messages: List[Dict[str, str]],
) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    req = urllib.request.Request(
        OPENAI_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", errors="ignore")
        sys.exit(f"OpenAI API error ({err.code}): {detail}")
    except urllib.error.URLError as err:
        sys.exit(f"Failed to reach OpenAI API: {err.reason}")
    except json.JSONDecodeError as err:
        sys.exit(f"Invalid JSON from OpenAI API: {err}")

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        sys.exit(f"Unexpected response from OpenAI API: {data}")


def slugify(name: str) -> str:
    if not name:
        return "learned-script"
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "learned-script"


def normalize_number(value: Any) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"Expected a numeric value, got {value!r}")
    if num.is_integer():
        return str(int(num))
    return f"{num:.2f}".rstrip("0").rstrip(".")


def write_script(
    plan: Dict[str, Any],
    scripts_dir: str,
    udid: str,
    active_device: str,
    active_app: str,
) -> str:
    steps = plan.get("steps", [])
    if not isinstance(steps, list) or not steps:
        raise ValueError("Plan must include a non-empty 'steps' list.")

    script_name = slugify(plan.get("script_name") or plan.get("name") or plan.get("title"))
    base_name = script_name
    path = os.path.join(scripts_dir, f"{script_name}.sh")
    counter = 1
    while os.path.exists(path):
        script_name = f"{base_name}-{counter}"
        path = os.path.join(scripts_dir, f"{script_name}.sh")
        counter += 1

    lines: List[str] = [
        "#!/bin/bash",
        f"# Generated by slog learn for app '{active_app}' on device '{active_device}'",
    ]
    description = plan.get("description")
    if description:
        lines.append(f"# {description}")
    lines.append("")

    for idx, raw_step in enumerate(steps, start=1):
        if not isinstance(raw_step, dict):
            raise ValueError(f"Step {idx} is not an object: {raw_step!r}")
        action = str(raw_step.get("action", "")).strip().lower()
        comment = raw_step.get("comment")
        if action not in {"tap", "type", "wait", "run"}:
            raise ValueError(f"Step {idx} has unsupported action '{action}'.")
        if comment:
            lines.append(f"# {comment}")

        if action == "tap":
            x = normalize_number(raw_step.get("x"))
            y = normalize_number(raw_step.get("y"))
            lines.append(f"axe tap -x {x} -y {y} --udid {shlex.quote(udid)}")
        elif action == "type":
            text = raw_step.get("text")
            if text is None:
                raise ValueError(f"Step {idx} (type) is missing 'text'.")
            lines.append(f"axe type --udid {shlex.quote(udid)} {shlex.quote(str(text))}")
        elif action == "wait":
            ms = raw_step.get("ms")
            if ms is None:
                raise ValueError(f"Step {idx} (wait) is missing 'ms'.")
            try:
                seconds = max(float(ms) / 1000.0, 0.0)
            except (TypeError, ValueError):
                raise ValueError(f"Step {idx} (wait) has invalid 'ms': {ms!r}")
            lines.append(f"sleep {seconds:.3f}".rstrip("0").rstrip("."))
        elif action == "run":
            command = raw_step.get("command")
            if not command:
                raise ValueError(f"Step {idx} (run) is missing 'command'.")
            lines.append(str(command))
        lines.append("")

    os.makedirs(scripts_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")
    os.chmod(path, 0o755)
    return script_name


def prompt(prompt_text: str) -> str:
    try:
        return input(prompt_text)
    except EOFError:
        return ""


def main() -> None:
    args = parse_args()
    api_key = ensure_openai_key()
    config = load_config(args.config)

    active_device = config.get("activeDevice")
    active_app = config.get("activeApp")
    if not active_device or not active_app:
        sys.exit("Config is missing activeDevice or activeApp. Use 'slog switch' first.")

    devices = config.get("devices", {})
    apps = config.get("apps", {})
    device_meta = devices.get(active_device, {})
    app_meta = apps.get(active_app, {})
    udid = device_meta.get("udid")
    bundle_id = app_meta.get("bundleId", "unknown bundle id")
    if not udid:
        sys.exit(f"Active device '{active_device}' does not have a UDID in config.")

    user_goal = prompt("What should slog learn? ").strip()
    if not user_goal:
        sys.exit("No goal provided. Aborting.")

    scripts_dir = os.path.expanduser("~/.slog/scripts")
    context = textwrap.dedent(
        f"""
        User goal: {user_goal}
        Active device: {active_device} (UDID: {udid})
        Active app: {active_app} (bundleId: {bundle_id})
        Remember to describe every tap with coordinates and plan realistic waits.
        """
    ).strip()

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": context},
    ]

    print("Starting slog learn session with OpenAI. Type 'exit' to cancel.\n")

    while True:
        assistant_text = call_openai(api_key, args.model, args.temperature, messages)
        messages.append({"role": "assistant", "content": assistant_text})
        print(f"\nAI:\n{assistant_text}\n")

        parsed_plan: Optional[Dict[str, Any]] = None
        stripped = assistant_text.lstrip()
        if stripped.startswith("{"):
            try:
                parsed_plan = json.loads(assistant_text)
            except json.JSONDecodeError:
                parsed_plan = None

        if parsed_plan:
            try:
                script_name = write_script(parsed_plan, scripts_dir, udid, active_device, active_app)
            except ValueError as err:
                print(f"Plan validation failed: {err}")
                messages.append(
                    {
                        "role": "user",
                        "content": f"The previous JSON was invalid because: {err}. Please fix it.",
                    }
                )
                continue

            script_path = os.path.join(scripts_dir, f"{script_name}.sh")
            print(f"Saved script to {script_path}")
            print(f"Run it later with: slog run {script_name}")
            return

        user_reply = prompt("You: ").strip()
        if user_reply.lower() in {"exit", "quit"}:
            print("Exiting slog learn session without saving.")
            return
        if not user_reply:
            print("No response entered. Exiting.")
            return
        messages.append({"role": "user", "content": user_reply})


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
