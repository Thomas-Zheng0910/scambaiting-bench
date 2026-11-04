"""`bench lint` as a module: validate every case file, print problems."""

from __future__ import annotations

import sys

from harness.run import main

if __name__ == "__main__":
    sys.exit(main(["lint", *sys.argv[1:]]))
