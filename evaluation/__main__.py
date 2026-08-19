# Allow `python -m evaluation` to run the CLI.
from evaluation.cli import main

raise SystemExit(main())
