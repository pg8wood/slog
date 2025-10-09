#!/usr/bin/env python3
import os
import shlex
import subprocess

SCRIPTS_DIR = os.path.expanduser("~/.slog/scripts")
os.makedirs(SCRIPTS_DIR, exist_ok=True)

HELP_TEXT = {
    "record": "Start recording a script: record <name>",
    "end": "Stop recording the current script and save it",
    "list": "List all available scripts",
    "help": "Show this help message",
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

def main():
    recording = False
    record_name = None
    record_udid = None
    record_lines = []

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

        if cmd == "help":
            for command, desc in HELP_TEXT.items():
                print(f"{command:12} - {desc}")
            print("During recording, 'tap' and 'type' commands auto-expand to 'axe tap' and 'axe type' with UDID appended.")
            print("Any other shell command can also be executed.")
            continue

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

            if cmd in AXE_COMMANDS and len(parts) > 1:
                command_line = f"{AXE_COMMANDS[cmd]} {' '.join(parts[1:])} --udid {record_udid}"
                print(f"Captured command: {command_line}")
                record_lines.append(command_line)
                subprocess.run(command_line, shell=True)
                continue
            else:
                # append --udid if not present and if this is a command line
                if "--udid" not in parts:
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

        # execute arbitrary command
        try:
            subprocess.run(line, shell=True)
        except Exception as e:
            print(f"Error executing command: {e}")

if __name__ == "__main__":
    main()
