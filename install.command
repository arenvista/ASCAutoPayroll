#!/bin/sh
# macOS double-click entry point. Finder runs .command files in Terminal;
# this just hands off to install.sh, which handles macOS and Linux alike.
DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$DIR/install.sh"
