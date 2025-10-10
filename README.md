# slog
Because Simulator Logins shouldn’t be a slog.

![slog demo](demo.gif)

---

## 🪵 What is slog?
A tiny CLI that launches your iOS Simulator app and taps through the login screen so you don’t have to.

- Saves/loads config at `~/.slog.json`
- EZ add & switch apps, accounts, and devices
- You're now one command away from being logged in

---

## ⚙️ Requirements
- macOS with Xcode Simulators installed (`xcrun simctl` is available)
- Homebrew
- An app with a single-screen login flow (Username + Password fields + Login button).
  - For more complex login flows, use `slog repl` to build and run a custom login script.
---

## 🍺 Install (Homebrew)
> [!NOTE]
> You may see errors when using `brew install`, like `Failed to fix install linkage` when homebrew installs the `AXe` dependency. This can safely be ignored. From their [README](https://github.com/cameroncooke/AXe/blob/main/README.md#install-via-homebrew): 
> > This is because the binaries are already codesigned and Homebrew is attempting to resign them, which is not necessary.

```bash
brew install pg8wood/tap/slog
```

---

## 🚀 Quick start
```bash

# First-time setup
slog setup

# Config
slog add                           # interactive
slog add <account|app|device>      # explicit
slog config                        # print current config

# Switching
slog switch                        # interactive
slog switch <account|app|device>   # explicit

# Login
slog                               # interactive
slog login                         # explicit
slog repl                          # open interactive REPL (record/list/run scripts)

# Post-login scripts
slog repl                          # run, record, and replay AXe commands in your simulator or arbitrary commands
slog run <script>                  # run previously recorded script non-interactively
```


---

## 📝 Notes
- The first time you use orientation or menu automation, macOS may prompt Terminal for “Automation” permissions (System Events).
> [!CAUTION]
> Credentials are stored locally in `~/.slog.json`. This app is only intended to store dev credentials. It is your responsibility to maintain a higher standard of security for your production accounts. 

---

## 🧭 Roadmap
- Re-enable landscape once AXe rotation is fixed ([`AXe #5`](https://github.com/cameroncooke/AXe/issues/5))
- Keychain storage for secure accounts

