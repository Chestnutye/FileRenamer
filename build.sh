#!/bin/bash

# Build script for Mac/Linux
# Ensure venv is active and pyinstaller is installed

if ! command -v pyinstaller &> /dev/null
then
    echo "PyInstaller could not be found. Installing..."
    pip install pyinstaller
fi

echo "Building FileRenamer..."
pyinstaller --noconfirm --onedir --windowed --name "FileRenamer" \
    --add-data "core:core" \
    --add-data "ui:ui" \
    --hidden-import "PIL" \
    --hidden-import "PIL._tkinter_finder" \
    main.py

echo "Build complete. Check dist/FileRenamer"
