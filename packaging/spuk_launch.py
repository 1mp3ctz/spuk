"""PyInstaller entry point.

We can't point PyInstaller at spuk/__main__.py directly: as the entry script it
runs as top-level "__main__" with no package, so its relative imports
(`from .config import ...`) fail. Importing the package here gives those imports
their parent package, so they resolve.

multiprocessing.freeze_support() must run first: in a frozen app, libraries that
use multiprocessing re-launch this executable with bootstrap args
(`-B -S -I -c "from multiprocessing..."`). freeze_support intercepts those so
they never reach our argparse, and makes child processes work.
"""

import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()

    from spuk.__main__ import main

    main()
