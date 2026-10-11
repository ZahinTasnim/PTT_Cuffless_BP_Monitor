#!/bin/sh
# Usage: sh validation/run_validation.sh <folder containing s10_sit.csv, s10_walk.csv, ... (500 Hz recordings)>
set -e
DATA="${1:?give the folder that holds the recording CSV files}"
WORK="${2:-validation/work}"
python3 validation/prepare_inputs.py "$DATA" "$WORK"
python3 validation/validate_on_ptt_dataset.py "$DATA" "$WORK"
python3 validation/make_validation_figures.py "$DATA" "$WORK"
