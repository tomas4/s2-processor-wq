#!/usr/bin/env bash
set -e

# ==============================================================================
# CONFIGURATION
# Set the absolute or relative path to your main Python processing script
# ==============================================================================
PYTHON_SCRIPT="/path/to/s2_l2a_processor.py"
VENV_DIR="$HOME/.cache/s2_processor_venv"
REQUIRED_PACKAGES=("numpy" "gdal")

# 1. Check if the target Python script exists
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "[ERROR] Python script not found at: $PYTHON_SCRIPT" >&2
    exit 1
fi

# 2. Create virtual environment if it does not exist
if [ ! -d "$VENV_DIR" ]; then
    echo "[INFO] Virtual environment not found. Creating venv at: $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

# 3. Activate virtual environment
source "$VENV_DIR/bin/activate"

# 4. Check and install missing requirements
for pkg in "${REQUIRED_PACKAGES[@]}"; do
    if ! python -c "import $pkg" &>/dev/null; then
        echo "[INFO] Required package '$pkg' missing. Installing..."
        pip install --upgrade pip
        pip install "$pkg"
    fi
done

# 5. Execute Python script and pass all command-line arguments ($@)
python "$PYTHON_SCRIPT" "$@"