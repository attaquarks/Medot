"""PyInstaller entrypoint: preserves `medot` package context so the
module's relative imports resolve inside the frozen executable."""
from medot.__main__ import main

if __name__ == "__main__":
    raise SystemExit(main())
