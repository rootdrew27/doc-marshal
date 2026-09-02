"""`python -m doc_marshal`, so the package runs from a checkout or a vendored copy with no install."""

import sys

from .cli import main

sys.exit(main())
