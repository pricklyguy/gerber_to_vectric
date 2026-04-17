# Gerber to DXF by The Prickly Guy

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](#requirements)
[![DXF](https://img.shields.io/badge/Output-DXF-c97a2b.svg)](#what-it-does)
[![GUI](https://img.shields.io/badge/Mode-GUI%20%2B%20CLI-1f1f1f.svg)](#running-the-app)
[![VCarve](https://img.shields.io/badge/Workflow-VCarve%20%2F%20Vectric-c97a2b.svg)](#suggested-vcarve-workflow)

Convert PCB **Gerber + Excellon drill files** into a **DXF** that works well in **VCarve / Vectric** workflows.

This project was built for the real-world CNC crowd: people making prototype boards, power boards, utility boards, and one-off PCB jobs who want a practical path from **EasyEDA / Gerber exports** into **Vectric** without wrestling five different CAM tools first.

---

## Features

- Parses **Gerber RS-274X** copper layers
- Parses **Excellon drill** files
- Exports:
  - copper traces
  - flashed pads
  - drill holes
  - board outline
- Supports:
  - **GUI mode**
  - **CLI mode**
- Auto-detects common top, bottom, outline, and drill files
- Uses **Shapely** to convert traces into real copper-width polygons
- Includes options for:
  - fallback trace width
  - optional isolation contour layers
  - optional copper fill region handling

---


## Screenshot

Add GUI screenshot here once in the repo:

```md
![Prickly Gerber to DXF GUI](docs/images/gui_main.png)
```

add a second image for a VCarve import example:

```md
![DXF imported into VCarve](docs/vcarve_import.png)
```

---

## Best use case

This tool currently works best for:

- simple 1-layer or 2-layer hobby boards
- power / utility boards
- wide traces
- through-hole workflows
- CNC-first PCB designs
- VCarve / Vectric import workflows

For boards you plan to mill yourself, you’ll usually get the cleanest results by:

- using wider traces
- increasing clearances
- keeping geometry simple
- avoiding solid copper pours unless you really need them

---



---

## Requirements

- Python 3.10+
- `ezdxf`
- `shapely`

Install:
Download the script and save it to whatever file/folder you want it in.  
From Windows you can double click and open from there. (you must associate it with python, once)
```md
![Prickly Gerber to DXF GUI](docs/gui_screenshot.png)
```
From PowerShell cd into the folder/directory you saved it in.
Make sure requirements are installed (Python, ezdxf, shapely)
run this command: python *script_name*.py
That's it.
```bash
pip install ezdxf shapely
```

Or:

```bash
pip install -r requirements.txt
```

---

## Running the app

### GUI mode

Run with no arguments:

```bash
python export_script.py
```

Or explicitly:

```bash
python export_script.py --gui
```

### CLI mode

```bash
python export_script.py <gerber_directory> [output.dxf]
```

Example:

```bash
python export_script.py ./my_board ./my_board/pcb_complete.dxf
```

If no output path is provided, it defaults to:

```text
pcb_complete.dxf
```

---

## GUI options

The GUI supports:

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

## Suggested VCarve workflow

1. Export the DXF using this tool
2. Import the DXF into VCarve
3. Separate layers if needed:
   - copper
   - drills
   - board outline
4. Use VCarve weld/join tools only where needed
5. Create toolpaths for:
   - copper isolation / contour
   - drilling
   - board cutout

---

## Auto-detected file types

The script looks for common naming patterns.

### Top copper
- `.GTL`
- `.TOP`
- `.CMP`
- files containing `TOPLAYER`

### Bottom copper
- `.GBL`
- `.BOT`
- `.SOL`
- files containing `BOTTOMLAYER`

### Board outline
- `.GKO`
- `.GM1`
- `.GML`
- files containing `OUTLINE`

### Drill files
- `.DRL`
- `.TXT`
- `.XLN`

---



## Known limitations

This is a practical CNC shop tool, not a full Gerber CAM suite.

### Things that generally work well
- simple hobby boards
- thick traces
- through-hole boards
- VCarve-based workflows

### Things that can still be tricky
- solid copper pours
- region-heavy boards
- unusual Gerber edge cases
- very complex aperture / region combinations
- fab-first boards that are not designed with CNC cutting in mind

---


## Planned improvements

- smarter copper region handling
- better pad / drill edge behavior
- optional debug preview window
- improved DXF layer naming
- packaged executable release
- broader support for more Gerber exporters

---

## Credits

Built by **Prickly Guy** for real-world CNC PCB experiments, VCarve workflows, and that timeless shop feeling of:

> “This should be simple... why is the copper angry?”

---

## Disclaimer

Always verify imported geometry before cutting.

This tool can save a lot of time, but CNC + PCB work is still very much a:

**measure twice, zero carefully, let the spindle scream once**  
kind of situation.
