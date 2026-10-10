"""Run the shared selection scenario through the real CLI."""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
FIXTURE = Path(__file__).resolve().parent
REPOSITORY = FIXTURE.parents[2]
sys.path[:0] = [str(REPOSITORY), str(REPOSITORY / "src")]
from tests.fixtures.support.rule_selection import main
if __name__ == "__main__":
    main(FIXTURE)
