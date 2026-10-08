# Power Modes

A small Windows GUI for switching a laptop between three power profiles. It was written for an ASUS ROG Strix SCAR 16 that can't keep up with a weak USB-C charger, but it works on any Windows 10/11 machine.

| Mode | Max processor state | Energy Performance Preference |
|---|---|---|
| Full Power | 100% | 50 (balanced) |
| Intermediate | 80% | 65 |
| Power Save (Slow Charger) | 50% | 80 (efficiency) |

Each mode is applied to both AC and battery on the active power plan using the built-in `powercfg`. It needs no admin rights and no third-party packages.

## Download

Get `PowerModes-<version>-win64.zip` from the [Releases](../../releases) page, extract it, and run `PowerModesApp.exe`. Keep the `_internal` folder next to the exe.

## Run from source

Requires Python 3 with tkinter (included in the standard Windows installer).

```powershell
pythonw power_modes.py                         # GUI
python power_modes.py --apply "Power Save (Slow Charger)"   # headless
```

## Build the exe

```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean PowerModesApp.spec
```

The output is in `dist\PowerModesApp\`.

`capture_window.ps1` launches the exe and saves a screenshot of its window, which is useful for checking a build.

## Notes

- A charger that delivers less than the laptop's baseline draw can't charge it while it's running. Power Save mode slows the drain; charge with the full adapter or while the laptop is off.
- The app changes the current power plan in place. To undo, pick Full Power or reset the plan in Windows power settings.

## License

MIT. See [LICENSE](LICENSE).
