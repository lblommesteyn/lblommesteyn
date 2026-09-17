import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gridconstraint.eval.benchmark import run
if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "queue"
    run(mode=mode)
