"""python -m nesting: start the nesting server (see nesting/README.md)."""
import sys

from .server import main

sys.exit(main(sys.argv))
