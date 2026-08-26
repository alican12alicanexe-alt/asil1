#!/usr/bin/env python
"""Convenience launcher, so the simulator runs from a clone with no install.

    python run.py scenarios/corridor3
    python run.py scenarios/corridor3 --headless

Equivalent to ``python -m trainsim ...`` when run from the project root.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from trainsim.cli import main  # noqa: E402  (import after sys.path is set)

if __name__ == "__main__":
    sys.exit(main())
