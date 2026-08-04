import os
import sys

# Tests import `brain.*` exactly like the proof scripts do with PYTHONPATH=.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
