#!/bin/sh
# ASCAutoPayroll installer for macOS and Linux.
# - Installs uv (the Python package manager) if it's missing
# - Installs the app and its dependencies
# - Creates a double-clickable launcher
#
# Usage:  ./install.sh      (or double-click install.command on macOS)
set -eu

# Resolve the project directory (where this script lives).
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$SCRIPT_DIR"

say()  { printf '\033[1;34m==>\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33mWARNING:\033[0m %s\n' "$1" >&2; }
die()  { printf '\033[1;31mERROR:\033[0m %s\n' "$1" >&2; exit 1; }

say "Installing ASCAutoPayroll"

# 1. Ensure uv is available (per-session PATH is enough for this run).
if ! command -v uv >/dev/null 2>&1; then
    say "Installing uv (one-time)..."
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        die "Need curl or wget to install uv. Install one and re-run."
    fi
    # uv installs to ~/.local/bin; make it usable in this shell.
    [ -f "$HOME/.local/bin/env" ] && . "$HOME/.local/bin/env"
    PATH="$HOME/.local/bin:$PATH"
    export PATH
fi

command -v uv >/dev/null 2>&1 || \
    die "uv is still not on PATH. Open a new terminal and run ./install.sh again."

# 2. Install the app + dependencies into a local virtual environment.
say "Installing dependencies (this may take a minute)..."
uv sync

# 3. Firefox is required by Selenium at runtime.
if command -v firefox >/dev/null 2>&1 || [ -d "/Applications/Firefox.app" ]; then
    say "Firefox detected."
else
    warn "Firefox not found. Install it from https://www.mozilla.org/firefox/ before running."
fi

# 4. Create a launcher appropriate to the platform.
if [ "$(uname -s)" = "Darwin" ]; then
    LAUNCHER="$SCRIPT_DIR/AutoPayroll.command"
    cat > "$LAUNCHER" <<EOF
#!/bin/sh
cd "$SCRIPT_DIR"
exec uv run autopayroll
EOF
    chmod +x "$LAUNCHER"
    say "Created launcher: AutoPayroll.command (double-click in Finder to run)"
else
    LAUNCHER="$SCRIPT_DIR/AutoPayroll.sh"
    cat > "$LAUNCHER" <<EOF
#!/bin/sh
cd "$SCRIPT_DIR"
exec uv run autopayroll
EOF
    chmod +x "$LAUNCHER"

    # Best-effort desktop entry so it shows up in the app menu (Linux).
    APPS_DIR="$HOME/.local/share/applications"
    if [ -d "$APPS_DIR" ] || mkdir -p "$APPS_DIR" 2>/dev/null; then
        cat > "$APPS_DIR/ascautopayroll.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=ASCAutoPayroll
Comment=UMBC timesheet automation
Exec=$LAUNCHER
Path=$SCRIPT_DIR
Terminal=true
Categories=Utility;
EOF
        say "Created app-menu entry: ASCAutoPayroll"
    fi
    say "Created launcher: AutoPayroll.sh"
fi

echo
say "Done. Launch the app with any of:"
echo "    ./AutoPayroll.sh            (Linux)"
echo "    double-click AutoPayroll.command   (macOS)"
echo "    uv run autopayroll         (from a terminal, anywhere in this folder)"
