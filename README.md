# Gerber to DXF by The Prickly Guy

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](#requirements)
[![DXF](https://img.shields.io/badge/Output-DXF-c97a2b.svg)](#what-it-does)
[![GUI](https://img.shields.io/badge/Mode-GUI%20%2B%20CLI-1f1f1f.svg)](#running-the-app)
[![VCarve](https://img.shields.io/badge/Workflow-VCarve%20%2F%20Vectric-c97a2b.svg)](#suggested-vcarve-workflow)

Convert PCB **Gerber + Excellon drill files** into a **DXF** that works well in **VCarve / Vectric** workflows.

This project was built for the real-world CNC crowd: people making prototype boards, power boards, utility boards, and one-off PCB jobs who want a practical path from **EasyEDA / Gerber exports** into **Vectric** without wrestling five different CAM tools first.

---

## Quick Start

1. [Download the script](#getting-the-script) and save it somewhere on your PC
2. [Install the requirements](#install-requirements) — Python 3.10+ and two packages
3. Double-click the script (Windows) or run `python export_script.py` from a terminal
4. Load your Gerber files in the GUI and click **Export DXF**

---

## Features

- Parses **Gerber RS-274X** copper layers
- Parses **Excellon drill** files
- Exports:
  - copper traces
  - flashed pads
  - drill holes
  - board outline
- Supports **GUI mode** and **CLI mode**
- Auto-detects common top, bottom, outline, and drill files
- Uses **Shapely** to convert traces into real copper-width polygons
- Includes options for:
  - fallback trace width
  - optional isolation contour layers
  - optional copper fill region handling

---

## Screenshots

GUI:

![Prickly Gerber to DXF GUI](https://raw.githubusercontent.com/pricklyguy/gerber_to_vectric/main/doc/images/gui_main.png)

VCarve Pro import result:

![DXF imported into VCarve](https://raw.githubusercontent.com/pricklyguy/gerber_to_vectric/main/doc/images/vcarve_import.png)

---

## Getting the Script

On this GitHub page, click the script file name, then click the **Raw** button, then right-click the page and choose **Save As** to download it. Save it to whatever folder makes sense — a dedicated project folder works well.

---

## Install Requirements

You need **Python 3.10 or newer** and two packages: `ezdxf` and `shapely`.

### Install Python (if you don't have it)

Download from [python.org](https://www.python.org/downloads/). During install, **check the box that says "Add Python to PATH"** — this saves a lot of trouble later.

### Install the packages

Open PowerShell or a terminal, and run:

```bash
pip install ezdxf shapely
```

That's it for setup.

---

## Running the App (Windows)

### Option 1 — Double-click (easiest)

You can double-click `export_script.py` directly to launch the GUI. The first time you do this, Windows will ask what program to open it with — choose Python.

If you haven't associated `.py` files with Python yet, here's how:

![Associate .py files with Python](https://raw.githubusercontent.com/pricklyguy/gerber_to_vectric/main/doc/images/associate.png)

### Option 2 — PowerShell

Open PowerShell, navigate to the folder where you saved the script, and run:

```bash
python export_script.py
```

![Running from PowerShell](https://raw.githubusercontent.com/pricklyguy/gerber_to_vectric/main/doc/images/powershell.png)

---

## Running the App (Linux)

*(Coming soon)*

---

## GUI Mode

Run with no arguments (or double-click):

```bash
python export_script.py
```

Or explicitly:

```bash
python export_script.py --gui
```

## CLI Mode

```bash
python export_script.py <gerber_directory> [output.dxf]
```

Example:

```bash
python export_script.py ./my_board ./my_board/pcb_complete.dxf
```

If no output path is provided, it defaults to:

```
pcb_complete.dxf
```

---

## GUI Options

- Top copper
- Bottom copper
- Board outline
- Drill files
- Output DXF path
- Isolation offset
- Fallback trace width
- Include copper fill regions
- Generate isolation contour layers (`*_ISO`)
- Use regions only (ignore stroke traces)

### Notes

**Include copper fill regions**
Leave this off unless you specifically need region-based copper in your export.

**Generate isolation contour layers (`*_ISO`)**
Useful when you want extra contour options in VCarve.

**Fallback trace width**
Used when the source trace aperture width is not resolved the way you want.

---

## Suggested VCarve Workflow

1. Export the DXF using this tool
2. Import the DXF into VCarve
3. Separate layers if needed (copper, drills, board outline)
4. Use VCarve weld/join tools only where needed
5. Create toolpaths for copper isolation, drilling, and board cutout

---

## Best Use Case

This tool currently works best for:

- Simple 1-layer or 2-layer hobby boards
- Power / utility boards
- Wide traces
- Through-hole workflows
- CNC-first PCB designs
- VCarve / Vectric import workflows

For boards you plan to mill yourself, you'll usually get the cleanest results by using wider traces, increasing clearances, keeping geometry simple, and avoiding solid copper pours unless you really need them.

---

## Auto-Detected File Types

The script looks for common naming patterns:

| Layer | Extensions / Patterns |
|---|---|
| Top copper | `.GTL`, `.TOP`, `.CMP`, `TOPLAYER` |
| Bottom copper | `.GBL`, `.BOT`, `.SOL`, `BOTTOMLAYER` |
| Board outline | `.GKO`, `.GM1`, `.GML`, `OUTLINE` |
| Drill files | `.DRL`, `.TXT`, `.XLN` |

---

## Known Limitations

This is a practical CNC shop tool, not a full Gerber CAM suite.

**Generally works well:** simple hobby boards, thick traces, through-hole boards, VCarve-based workflows

**Can still be tricky:** solid copper pours, region-heavy boards, unusual Gerber edge cases, very complex aperture/region combinations, fab-first boards not designed with CNC cutting in mind

---

## Planned Improvements

- Smarter copper region handling
- Better pad / drill edge behavior
- Optional debug preview window
- Improved DXF layer naming
- Packaged executable release
- Broader support for more Gerber exporters
- Linux install instructions

---

## Credits

Built by **Prickly Guy** for real-world CNC PCB experiments, VCarve workflows, and that timeless shop feeling of:

> "This should be simple... why is the copper angry?"

---

## Disclaimer

Always verify imported geometry before cutting.

This tool can save a lot of time, but CNC + PCB work is still very much a **measure twice, zero carefully, let the spindle scream once** kind of situation.
