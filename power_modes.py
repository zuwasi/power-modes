"""
Power Modes - a small GUI to switch the laptop between three power profiles.

Modes:
  Full Power                 -> CPU uncapped, boost clocks (use the 240W adapter)
  Intermediate               -> CPU capped at 80%, efficiency-leaning
  Power Save (Slow Charger)  -> CPU capped at 50%, max efficiency, for weak chargers

No admin rights or third-party packages needed (uses powercfg, built into Windows).
"""

import ctypes
import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk

PROC_SUBGROUP = "54533251-82be-4824-96c1-47b60b740d00"
PROC_MAX = "bc5038f7-23e0-4960-96da-33abaf5935ec"
EPP = "36687f9e-e3a5-4dbf-b1dc-15eb381c6863"

MODES = {
    "Full Power": {
        "max_state": 100,
        "epp": 50,
        "title": "Full Power (240W adapter)",
        "explanation": (
            "What this does:\n"
            "  - Max processor state: 100% on AC and battery, so the CPU can\n"
            "    boost to its full speed at any time.\n"
            "  - Energy Performance Preference: 50 (balanced), so Windows lets\n"
            "    the CPU boost aggressively instead of holding back.\n\n"
            "Use this when:\n"
            "  You are plugged into the original 240W ASUS adapter, or running\n"
            "  on battery and need maximum speed (compiles, games, scans).\n\n"
            "Power impact: highest draw. A slow charger cannot keep up with\n"
            "  this mode; the battery will drain even while plugged in."
        ),
    },
    "Intermediate": {
        "max_state": 80,
        "epp": 65,
        "title": "Intermediate (balanced saving)",
        "explanation": (
            "What this does:\n"
            "  - Max processor state: 80% on AC and battery. The CPU still has\n"
            "    plenty of headroom but cannot hold its hottest boost clocks.\n"
            "  - Energy Performance Preference: 65 (efficiency-leaning).\n\n"
            "Use this when:\n"
            "  You want good everyday responsiveness with noticeably less heat\n"
            "  and fan noise, on a charger that is not the 240W one.\n\n"
            "Power impact: moderate. Cuts peak CPU draw roughly in half while\n"
            "  keeping the machine feeling quick for normal work."
        ),
    },
    "Power Save (Slow Charger)": {
        "max_state": 50,
        "epp": 80,
        "title": "Power Save (for slow chargers)",
        "explanation": (
            "What this does:\n"
            "  - Max processor state: 50% on AC and battery. This is the single\n"
            "    biggest software lever for cutting power draw.\n"
            "  - Energy Performance Preference: 80 (strong efficiency).\n"
            "  - Docker Desktop / WSL are NOT touched; close Docker manually if\n"
            "    it is running, since its VM is a major power consumer.\n\n"
            "Use this when:\n"
            "  You are on a 45-65W USB-C charger and want the battery to hold\n"
            "  steady or slowly charge instead of draining.\n\n"
            "Power impact: lowest draw. Even so, the Strix SCAR's idle hardware\n"
            "  (dGPU, big screen, RGB) may still exceed a very weak charger."
        ),
    },
}

MODE_NAMES = list(MODES)


def run_powercfg(args):
    result = subprocess.run(
        ["powercfg"] + args, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"powercfg {args[0]} failed")
    return result.stdout


def apply_mode(name):
    mode = MODES[name]
    for side in ("/setacvalueindex", "/setdcvalueindex"):
        run_powercfg([side, "SCHEME_CURRENT", PROC_SUBGROUP, PROC_MAX, str(mode["max_state"])])
        run_powercfg([side, "SCHEME_CURRENT", PROC_SUBGROUP, EPP, str(mode["epp"])])
    run_powercfg(["/setactive", "SCHEME_CURRENT"])


def read_current_max_state():
    out = run_powercfg(["/query", "SCHEME_CURRENT", PROC_SUBGROUP, PROC_MAX])
    ac = dc = None
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Current AC Power Setting Index"):
            ac = int(line.split("0x")[1], 16)
        elif line.startswith("Current DC Power Setting Index"):
            dc = int(line.split("0x")[1], 16)
    return ac, dc


def read_battery_percent():
    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", ctypes.c_byte),
            ("BatteryFlag", ctypes.c_byte),
            ("BatteryLifePercent", ctypes.c_byte),
            ("Reserved1", ctypes.c_byte),
            ("BatteryLifeTime", ctypes.c_ulong),
            ("BatteryFullLifeTime", ctypes.c_ulong),
        ]

    sps = SYSTEM_POWER_STATUS()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(sps)):
        return None
    pct = sps.BatteryLifePercent
    return None if pct == 255 else pct


def match_mode_name(ac, dc):
    if ac is None:
        return None
    for name, mode in MODES.items():
        if mode["max_state"] == ac:
            return name
    return None


class PowerModesApp(tk.Tk):
    def __init__(self, icon_path=None):
        super().__init__()
        self.title("Power Modes")
        self.resizable(False, False)
        self.configure(bg="#1e2229")
        if icon_path:
            try:
                self.iconbitmap(icon_path)
            except tk.TclError:
                pass

        pad = {"padx": 16, "pady": 8}

        header = tk.Label(
            self,
            text="ROG Strix SCAR 16 - Power Modes",
            font=("Segoe UI", 16, "bold"),
            bg="#1e2229",
            fg="#f5f6fa",
        )
        header.grid(row=0, column=0, columnspan=2, sticky="w", **pad)

        battery = read_battery_percent()
        battery_text = f"Battery: {battery}%" if battery is not None else "Battery: unknown"
        self.battery_label = tk.Label(
            self, text=battery_text, font=("Segoe UI", 10), bg="#1e2229", fg="#9aa3b0"
        )
        self.battery_label.grid(row=1, column=0, columnspan=2, sticky="w", padx=16, pady=0)

        tk.Label(
            self, text="Mode:", font=("Segoe UI", 11), bg="#1e2229", fg="#f5f6fa"
        ).grid(row=2, column=0, sticky="e", padx=(16, 8), pady=8)

        self.mode_var = tk.StringVar(value=MODE_NAMES[0])
        self.dropdown = ttk.Combobox(
            self, textvariable=self.mode_var, values=MODE_NAMES, state="readonly", width=30
        )
        self.dropdown.grid(row=2, column=1, sticky="w", padx=(0, 16), pady=8)
        self.dropdown.bind("<<ComboboxSelected>>", lambda _e: self.update_explanation())

        self.explanation = tk.Label(
            self,
            text="",
            font=("Segoe UI", 10),
            bg="#262b34",
            fg="#d8dde6",
            justify="left",
            anchor="nw",
            wraplength=520,
            padx=14,
            pady=12,
        )
        self.explanation.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=16, pady=(4, 8))

        self.status = tk.Label(
            self, text="", font=("Segoe UI", 10, "bold"), bg="#1e2229", fg="#7ee787"
        )
        self.status.grid(row=4, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 4))

        buttons = tk.Frame(self, bg="#1e2229")
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", padx=16, pady=(0, 14))

        apply_btn = tk.Button(
            buttons,
            text="Apply mode",
            font=("Segoe UI", 10, "bold"),
            bg="#3572e0",
            fg="white",
            activebackground="#2a5cb8",
            activeforeground="white",
            relief="flat",
            padx=18,
            pady=4,
            command=self.on_apply,
        )
        apply_btn.pack(side="left", padx=(0, 8))

        refresh_btn = tk.Button(
            buttons,
            text="Refresh current",
            font=("Segoe UI", 10),
            bg="#3a414d",
            fg="#d8dde6",
            activebackground="#4a5260",
            activeforeground="white",
            relief="flat",
            padx=12,
            pady=4,
            command=self.refresh_current,
        )
        refresh_btn.pack(side="left")

        self.update_explanation()
        self.refresh_current()

    def update_explanation(self):
        mode = MODES[self.mode_var.get()]
        self.explanation.configure(text=mode["explanation"])

    def refresh_current(self):
        ac, dc = read_current_max_state()
        battery = read_battery_percent()
        if battery is not None:
            self.battery_label.configure(text=f"Battery: {battery}%")
        name = match_mode_name(ac, dc)
        if name:
            self.mode_var.set(name)
            self.update_explanation()
            self.status.configure(
                text=f"Current settings match: {name} (CPU max {ac}% on AC, {dc}% on battery)",
                fg="#7ee787",
            )
        else:
            self.status.configure(
                text=f"Current settings are custom (CPU max {ac}% on AC, {dc}% on battery)",
                fg="#e3b341",
            )

    def on_apply(self):
        name = self.mode_var.get()
        try:
            apply_mode(name)
        except RuntimeError as exc:
            messagebox.showerror("Power Modes", f"Could not apply {name}:\n{exc}")
            return
        self.refresh_current()


def find_icon():
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.join(base, "power_modes.ico")
    return candidate if os.path.exists(candidate) else None


def main():
    if "--apply" in sys.argv:
        # headless mode for testing/automation: power_modes.py --apply "<mode name>"
        idx = sys.argv.index("--apply")
        if idx + 1 >= len(sys.argv):
            print("Usage: power_modes.py --apply \"<mode name>\"")
            return 1
        mode_name = sys.argv[idx + 1]
        if mode_name not in MODES:
            print(f"Unknown mode: {mode_name}. Valid: {', '.join(MODE_NAMES)}")
            return 1
        apply_mode(mode_name)
        ac, dc = read_current_max_state()
        print(f"Applied: {mode_name} (CPU max {ac}% on AC, {dc}% on battery)")
        return 0

    app = PowerModesApp(icon_path=find_icon())
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
