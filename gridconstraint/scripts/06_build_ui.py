import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gridconstraint.app.build_ui import build
if __name__ == "__main__":
    build(limit=int(sys.argv[1]) if len(sys.argv) > 1 else None)
