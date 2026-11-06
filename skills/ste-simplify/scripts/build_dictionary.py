#!/usr/bin/env python3
"""Run ste-build-dictionary without install: python3 build_dictionary.py PDF"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ste_simplify.build import main  # noqa: E402

sys.exit(main())
