#!/bin/bash
# Run the FastAPI backend

cd "$(dirname "$0")"
export PYTHONPATH="$(dirname "$0")/..:$PYTHONPATH"

# Load environment variables from config/.env
if [ -f ../config/.env ]; then
    export $(cat ../config/.env | grep -v '^#' | xargs)
fi

python main.py
