"""python -m pcb2vectric            -> GUI
   python -m pcb2vectric DIR OUT   -> command line"""

import sys

if len(sys.argv) > 1:
    from .cli import run

    run()
else:
    from .gui.app import main

    main()
