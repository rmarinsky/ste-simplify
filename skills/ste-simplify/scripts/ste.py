#!/usr/bin/env python3
"""Run ste without install: python3 ste.py prepare|scan|fix ..."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ste_simplify.cli import main  # noqa: E402

sys.exit(main())
