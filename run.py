"""Run the shared kit from any current directory, without installing a package."""
import sys
sys.dont_write_bytecode = True
from stylekit.__main__ import main
if __name__ == '__main__':
    raise SystemExit(main())
