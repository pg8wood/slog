#!/usr/bin/env python3
import os
import shlex
import subprocess

SCRIPTS_DIR = os.path.expanduser("~/.slog/scripts")
os.makedirs(SCRIPTS_DIR, exist_ok=True)

# Global device UDID for tap/type/axe commands
current_udid = None

HELP_TEXT = {
    "record": "Start recording a script: record <name>",
    "end": "Stop recording the current script and save it",
    "list": "List all available scripts",
    "help": "Show this help message",
    "tap": "Tap on the screen at coordinates X Y (e.g., `tap 200 400`).",
    "type": "Type the given text into the active field (e.g., `type hello@world.com`).",
    "device": "Set the target simulator UDID for subsequent commands (e.g., `device <udid>`).",
    "<script_name>": "Run the named script",
}

AXE_COMMANDS = {
    "tap": "axe tap",
    "type": "axe type",
}

def list_scripts():
    scripts = [f[:-3] for f in os.listdir(SCRIPTS_DIR) if f.endswith(".sh")]
    if scripts:
        print("Available scripts:")
        for s in scripts:
            print(f"  {s}")
    else:
        print("No scripts found.")

def run_script(name):
    script_path = os.path.join(SCRIPTS_DIR, f"{name}.sh")
    if not os.path.isfile(script_path):
        print(f"No script named '{name}' found.")
        return
    subprocess.run(["bash", script_path])

def print_help():
    print("record       - Start recording a script: record <name>")
    print("end          - Stop recording the current script and save it")
    print("list         - List all available scripts")
    print("help         - Show this help message")
    print("tap          - Tap on the screen at coordinates X Y (e.g., `tap 200 400`).")
    print("type         - Type the given text into the active field (e.g., `type hello@world.com`).")
    print("device       - Set the target simulator UDID for subsequent commands (e.g., `device <udid>`).")
    print("<script_name> - Run the named script")
    print()
    print("During recording, 'tap' and 'type' commands auto-expand to 'axe tap' and 'axe type' with UDID appended.")
    print("Any other shell command can also be executed.")

def main():
    global current_udid
    recording = False
    record_name = None
    record_udid = None
    record_lines = []

    # Print welcome banner before entering the command loop
    print("Welcome to slog REPL 🎛️")

    # Show shortcuts only the first time user runs the REPL
    import pathlib
    seen_file = os.path.expanduser("~/.slog_repl_seen")
    if not os.path.exists(seen_file):
        print("Type `help` to see available commands.")
        print("Common shortcuts:")
        print("  tap <x> <y>")
        print("  type <text>")
        print("  device <udid>")
        print("You can also run any shell command. Commands are executed immediately and recorded when in record mode.")
        # Create the marker file to indicate the shortcuts have been shown
        try:
            pathlib.Path(seen_file).touch(exist_ok=True)
        except Exception:
            # Fallback: just write a line
            with open(seen_file, "w") as f:
                f.write("seen\n")

    while True:
        try:
            line = input("slog> ").strip()
        except EOFError:
            print()
            break
        if not line:
            continue

        parts = shlex.split(line)
        if not parts:
            continue
        cmd = parts[0]
        args = parts[1:]

        # Device command: set the global UDID
        if cmd == "device":
            if len(args) != 1:
                print("Usage: device <udid>")
                continue
            current_udid = args[0]
            print(f"Set current device UDID to: {current_udid}")
            continue

        # Help
        if cmd == "help":
            print_help()
            continue

        # TAP shorthand: tap X Y
        if cmd == "tap" and len(args) == 2:
            x, y = args
            if not (x.isdigit() and y.isdigit()):
                print("Error: tap command requires two numbers. Usage: tap <x> <y>")
                continue
            if not current_udid:
                print("No device set. Use: device <udid>")
                continue
            tap_cmd = f"axe tap --udid {current_udid} -x {x} -y {y}"
            if recording:
                record_lines.append(tap_cmd)
                print(f"Captured command: {tap_cmd}")
            subprocess.run(tap_cmd, shell=True)
            continue

        # TYPE shorthand: type <text>
        if cmd == "type" and len(args) >= 1:
            if not current_udid:
                print("No device set. Use: device <udid>")
                continue
            text = " ".join(args)
            type_cmd = f'axe type --udid {current_udid} "{text}"'
            if recording:
                record_lines.append(type_cmd)
                print(f"Captured command: {type_cmd}")
            subprocess.run(type_cmd, shell=True)
            continue

        # Recording logic
        if recording:
            if cmd == "end":
                # save the script
                script_path = os.path.join(SCRIPTS_DIR, f"{record_name}.sh")
                with open(script_path, "w") as f:
                    f.write("#!/bin/bash\n")
                    for l in record_lines:
                        f.write(l + "\n")
                os.chmod(script_path, 0o755)
                print(f"Stopped recording '{record_name}', saved to {script_path}")
                recording = False
                record_name = None
                record_udid = None
                record_lines = []
                continue

            # AXe commands: tap/type
            if cmd in AXE_COMMANDS and len(parts) > 1:
                # Use recording UDID
                if not record_udid:
                    print("No UDID set for recording. Recording session is broken.")
                    continue
                command_line = f"{AXE_COMMANDS[cmd]} {' '.join(parts[1:])} --udid {record_udid}"
                print(f"Captured command: {command_line}")
                record_lines.append(command_line)
                subprocess.run(command_line, shell=True)
                continue
            else:
                # If "--udid" not present, append
                if "--udid" not in parts and record_udid:
                    command_line = line + f" --udid {record_udid}"
                else:
                    command_line = line
                print(f"Captured command: {command_line}")
                record_lines.append(command_line)
                subprocess.run(command_line, shell=True)
                continue

        # not recording
        if cmd == "record":
            if len(parts) != 2:
                print("Usage: record <name>")
                continue
            record_name = parts[1]
            record_path = os.path.join(SCRIPTS_DIR, f"{record_name}.sh")
            if os.path.exists(record_path):
                print(f"Warning: script '{record_name}' already exists and will be overwritten.")
            record_udid = input("Enter UDID: ").strip()
            recording = True
            record_lines = []
            print(f"Started recording '{record_name}' with UDID {record_udid}")
            continue

        if cmd == "list":
            list_scripts()
            continue

        if cmd == "end":
            print("Not currently recording.")
            continue

        # check if cmd is a stored script name
        script_path = os.path.join(SCRIPTS_DIR, f"{cmd}.sh")
        if os.path.isfile(script_path) and len(parts) == 1:
            run_script(cmd)
            continue

        # AXe command expansion (axe tap/type)
        if cmd == "axe" and len(parts) >= 2:
            axe_cmd = parts[1]
            if axe_cmd in ("tap", "type"):
                # Check for --udid in args
                if "--udid" not in parts and not current_udid:
                    print("No device set. Use: device <udid>")
                    continue
                # If --udid not present, append
                if "--udid" not in parts:
                    # Find where to insert
                    new_line = line + f" --udid {current_udid}"
                else:
                    new_line = line
                if recording:
                    record_lines.append(new_line)
                    print(f"Captured command: {new_line}")
                subprocess.run(new_line, shell=True)
                continue

        # execute arbitrary command
        try:
            subprocess.run(line, shell=True)
        except Exception as e:
            print(f"Error executing command: {e}")

if __name__ == "__main__":
    main()
