import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "artifacts", "api-server"))

from app import app  # noqa: E402, F401
