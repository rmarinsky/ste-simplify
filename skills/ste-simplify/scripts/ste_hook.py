#!/usr/bin/env python3
"""Claude Code hook without installation. It is the same as "ste hook". See ste_simplify/hook.py."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ste_simplify import hook  # noqa: E402

if __name__ == "__main__":
    sys.exit(hook.main())
