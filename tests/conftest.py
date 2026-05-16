import sys
from pathlib import Path

# Ensure the project root is on sys.path so `import quota_monitor` works without install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
