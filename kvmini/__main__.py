"""
Main entry point for kvmini CLI.
"""

import os
import sys

# Add the parent directory to the Python path so we can import the existing modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kvmini.cli import main

if __name__ == "__main__":
    main()
