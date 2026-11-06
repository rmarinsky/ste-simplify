#!/usr/bin/env python3
"""Run ste-fix without install: python3 ste_fix.py PATH ..."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ste_simplify.fix import main  # noqa: E402

sys.exit(main())
