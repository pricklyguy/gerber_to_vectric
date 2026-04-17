# Gerber to DXF by The Prickly Guy

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](#requirements)
[![DXF](https://img.shields.io/badge/Output-DXF-c97a2b.svg)](#what-it-does)
[![GUI](https://img.shields.io/badge/Mode-GUI%20%2B%20CLI-1f1f1f.svg)](#running-the-app)
[![VCarve](https://img.shields.io/badge/Workflow-VCarve%20%2F%20Vectric-c97a2b.svg)](#suggested-vcarve-workflow)

Convert PCB **Gerber + Excellon drill files** into a **DXF** that works well in **VCarve / Vectric** workflows.

This project was built for the real-world CNC crowd: people making prototype boards, power boards, utility boards, and one-off PCB jobs who want a practical path from **EasyEDA / Gerber exports** into **Vectric** without wrestling five different CAM tools first.

---

## Why this exists

Most PCB tooling assumes one of two worlds:

- send everything to a board house
- use a dedicated PCB CAM workflow

This tool lives in the third world:

- design the board
- export Gerbers and drill files
- generate a DXF
- bring it into VCarve
- cut copper without losing your mind

---

## What it does

- Parses **Gerber RS-274X** copper layers
- Parses **Excellon drill** files
- Exports:
  - copper traces
  - flashed pads
  - drill holes
  - board outline
- Supports both:
  - **GUI mode**
  - **CLI mode**
- Auto-detects common file names for:
  - top copper
  - bottom copper
  - board outline
  - drill files
- Uses **Shapely** to buffer traces into real copper-width polygons
- Lightly welds overlapping copper geometry for cleaner DXF output
- Includes options for:
  - fallback trace width
  - optional isolation contour layers
  - optional copper fill region handling

---

## Screenshot

Add your GUI screenshot here once you save one in the repo:

```md
![Prickly Gerber to DXF GUI](docs/gui_screenshot.png)
```

You can also add a second image later for a VCarve import example:

```md
![DXF imported into VCarve](docs/vcarve_import.png)
```

---

## Current sweet spot

This tool currently works best for:

- simple 1-layer or 2-layer hobby boards
- utility / power distribution boards
- wide traces
- through-hole drilling workflows
- CNC-first board layouts
- VCarve / Vectric import workflows

### Best results for self-milled boards

For boards you plan to cut yourself on a CNC, these usually behave best:

- **wide traces**
- **larger clearances**
- **simple geometry**
- **no solid copper pour unless you really need it**

Copper pours are great for boards going to a fab house, but for CNC-milled boards they can add extra region/polarity complexity that makes export and cleanup more annoying than it needs to be.

---

## Repository structure

```text
gerber_to_vectric/
├── script/
│   ├── export_script.py
│   └── prickly_guy_small.png
├── docs/
│   ├── gui_screenshot.png
│   └── vcarve_import.png
├── requirements.txt
└── README.md
```

---

## Requirements

- Python 3.10+
- `ezdxf`
- `shapely`

Install dependencies:

```bash
pip install ezdxf shapely
```

Or from `requirements.txt`:

```bash
pip install -r requirements.txt
```

---

## Running the app

### GUI mode

Run with no arguments:

```bash
python script/export_script.py
```

Or explicitly:

```bash
python script/export_script.py --gui
```

### CLI mode

```bash
python script/export_script.py <gerber_directory> [output.dxf]
```

Example:

```bash
python script/export_script.py ./my_board ./my_board/pcb_complete.dxf
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

## Before / After idea for the repo

You can add a section like this later with screenshots from your actual workflow:

### Before
- raw Gerber export
- weird region behavior
- cleanup needed in VCarve

### After
- traces pulled in as usable copper-width geometry
- drills included
- board outline included
- far less manual cleanup

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

## Recommended CNC PCB design rules

For boards you plan to cut yourself:

- use wider traces than you would for fab
- increase copper clearance
- avoid copper pours unless truly needed
- keep geometry simple
- test on scrap first
- preview the DXF before committing a real board

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
