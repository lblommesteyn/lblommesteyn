import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gridconstraint.app.build_ui import build, build_shard
if __name__ == "__main__":
    # usage: 06_build_ui.py shard <k> <n>   |   06_build_ui.py merge <n>
    if len(sys.argv) > 1 and sys.argv[1] == "shard":
        build_shard(int(sys.argv[2]), int(sys.argv[3]))
    else:
        build(n_shards=int(sys.argv[2]) if len(sys.argv) > 2 else 3)
