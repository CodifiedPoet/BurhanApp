#!/usr/bin/env python3
"""Simple launcher for BurhanApp."""

import sys
import os

# Ensure the src directory is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from scanmaker.__main__ import main

if __name__ == "__main__":
    main()
