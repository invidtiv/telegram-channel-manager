#!/usr/bin/env python3
"""Entry point for running the backend with proper path setup."""

import sys
import os
from pathlib import Path

# Add parent directory to path
backend_dir = Path(__file__).parent
project_dir = backend_dir.parent
sys.path.insert(0, str(project_dir))

# Load environment variables
env_file = project_dir / "config" / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key, value)

# Import and run
from backend.main import app
import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
