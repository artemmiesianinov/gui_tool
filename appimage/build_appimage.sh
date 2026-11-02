#!/bin/bash
#
# Builds a DroneCAN GUI Tool AppImage for x86_64 Linux.
#
# The AppImage bundles a portable Python (from python-appimage), the project wheel and all its dependencies,
# including Qt through the PyQt6 wheels, so nothing needs to be installed on the target system.
#
# Usage, from anywhere:
#   appimage/build_appimage.sh
#
# Environment variables:
#   PYTHON_VERSION   Python version to bundle (default 3.12)
#   LINUX_TAG        manylinux tag of the base Python image (default manylinux_2_28_x86_64)
#
# The result is written to dist/DroneCAN_GUI_Tool-<version>-x86_64.AppImage.

set -euo pipefail

PYTHON_VERSION="${PYTHON_VERSION:-3.12}"
LINUX_TAG="${LINUX_TAG:-manylinux_2_28_x86_64}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$SOURCE_DIR/dist"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

# Build tooling lives in its own venv so it doesn't touch the development environment
echo "== Setting up build tools"
python3 -m venv "$WORK_DIR/tools"
"$WORK_DIR/tools/bin/pip" install -q -U pip build python-appimage

echo "== Building the project wheel"
"$WORK_DIR/tools/bin/python" -m build --wheel --outdir "$WORK_DIR/wheel" "$SOURCE_DIR"
WHEEL="$(ls "$WORK_DIR"/wheel/dronecan_gui_tool-*.whl)"
VERSION="$(basename "$WHEEL" | cut -d- -f2)"

# python-appimage takes the application name from the recipe directory name
echo "== Preparing the AppImage recipe"
RECIPE="$WORK_DIR/dronecan_gui_tool"
mkdir -p "$RECIPE"
cp "$SCRIPT_DIR/dronecan_gui_tool.desktop" "$SCRIPT_DIR/entrypoint.sh" "$RECIPE/"
cp "$SOURCE_DIR/dronecan_gui_tool/icons/dronecan_gui_tool.png" "$RECIPE/"
echo "$WHEEL" > "$RECIPE/requirements.txt"

echo "== Building the AppDir (Python $PYTHON_VERSION, $LINUX_TAG)"
cd "$WORK_DIR"
"$WORK_DIR/tools/bin/python-appimage" build app --no-packaging -p "$PYTHON_VERSION" -l "$LINUX_TAG" "$RECIPE"
APPDIR="$WORK_DIR/DroneCAN GUI Tool-x86_64"

# Parts of the extracted base image are only accessible by their owner, which appimagetool rejects
# because the AppImage is run by other users
chmod -R a+rX "$APPDIR"

echo "== Packaging the AppImage"
"$WORK_DIR/tools/bin/python-appimage" install appimagetool
APPIMAGETOOL="$("$WORK_DIR/tools/bin/python-appimage" which appimagetool)"
mkdir -p "$DIST_DIR"
OUTPUT="$DIST_DIR/DroneCAN_GUI_Tool-$VERSION-x86_64.AppImage"
# Build next to the destination and rename, so a previous AppImage that is still running doesn't block the overwrite
ARCH=x86_64 "$APPIMAGETOOL" --no-appstream "$APPDIR" "$OUTPUT.tmp"
mv -f "$OUTPUT.tmp" "$OUTPUT"
echo "== Built $OUTPUT"
