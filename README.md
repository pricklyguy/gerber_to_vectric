# Gerber to DXF by The Prickly Guy

Convert PCB **Gerber + Excellon drill files** into a **DXF** that works well in **VCarve / Vectric** workflows.

Built for CNC-milled PCB experiments where you want copper traces, pads, drills, and board outline in a format that is actually usable without a bunch of CAM gymnastics.

---

## Features

- Converts **Gerber RS-274X** copper layers into DXF geometry
- Parses **Excellon drill** files
- Exports:
  - copper traces
  - flashed pads
  - drill holes
  - board outline
- Supports both:
  - **GUI mode** with a dark Prickly-themed Tkinter interface
  - **CLI mode** for quick direct use
- Auto-detects common Gerber / Excellon file names
- Uses **Shapely** to buffer trace centerlines into real copper-width polygons
- Includes options for:
  - fallback trace width
  - optional isolation contour layer generation
  - optional copper fill region handling

---

## Why this exists

Most PCB export workflows are designed for sending boards to a fab house.

This tool is for the other crowd:

- you designed a board in EasyEDA or a similar tool
- you want to mill it yourself on a CNC
- you want a DXF that imports into VCarve cleanly
- you still want drills and board outline included

Basically: less fighting, more cutting.

---

## Current sweet spot

This project currently works best for:

- simple 1-layer or 2-layer hobby boards
- wide traces
- utility / power distribution boards
- through-hole drilling workflows
- VCarve / Vectric import workflows

### Recommended for CNC-milled boards

For boards you are cutting yourself, these usually behave best:

- **wide traces**
- **larger clearances**
- **simple geometry**
- **no solid copper pour unless you really need it**

Copper pours are great for fabbed boards, but they often add a bunch of region/polarity complexity that makes CNC DXF conversion more annoying than it needs to be.

---

## Requirements

- Python 3.10+
- `ezdxf`
- `shapely`

Install dependencies:

```bash
pip install ezdxf shapely
```

Or, if using a `requirements.txt`:

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

If no output path is provided, the script defaults to:

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

- **Include copper fill regions**  
  Leave this off unless you need it.

- **Generate isolation contour layers (`*_ISO`)**  
  Useful if you want extra contour options in VCarve.

- **Fallback trace width**  
  Used when the source trace aperture width is not resolved the way you want.

---

## Suggested VCarve workflow

1. Export the DXF using this tool
2. Import the DXF into VCarve
3. Separate layers if needed:
   - copper
   - drills
   - board outline
4. Use VCarve weld/join tools only where necessary
5. Create your toolpaths:
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

This is a practical shop tool, not a full Gerber CAM suite.

### Things that generally work well
- simple hobby boards
- thick traces
- through-hole boards
- VCarve-based CNC workflows

### Things that can still be tricky
- solid copper pours
- region-heavy boards
- unusual Gerber edge cases
- very complex aperture / region combinations
- designs intended purely for fab-first workflows

---

## Recommended CNC PCB design rules

For boards you plan to cut yourself:

- use wider traces than you would for a fab house
- increase trace clearance
- avoid copper pours unless needed
- keep geometry simple
- test on scrap first

---

## Example project structure

```text
gerber_to_vectric/
├── script/
│   ├── export_script.py
│   └── prickly_guy_small.png
├── requirements.txt
└── README.md
```

---

## Roadmap ideas

- smarter copper region handling
- better drill/pad edge behavior
- optional debug preview window
- better DXF layer naming
- packaged executable release
- broader support for more Gerber exporters

---

## Screenshot

_Add a screenshot of the GUI here once you are ready._

Example GitHub markdown:

```md
![Prickly Gerber to DXF GUI](docs/gui_screenshot.png)
```

---

## Credits

Built by **Prickly Guy** for real-world CNC PCB experiments, VCarve workflows, and the timeless pursuit of making copper do what it’s told.

---

## Disclaimer

Always verify imported geometry before cutting.

This tool can save a lot of time, but CNC + PCB work is still very much a:

**measure twice, zero carefully, let the spindle scream once** kind of situation.
