"""PyInstaller entry point for the app's bundled backend (see build-backend.mjs)."""

from autopayroll.bridge import main

if __name__ == "__main__":
    main()
