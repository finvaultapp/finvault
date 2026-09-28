"""Run FinVault locally with the built frontend.

    python scripts/serve_local.py [data_dir]
"""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
os.environ.setdefault("FINVAULT_DATA_DIR", sys.argv[1] if len(sys.argv) > 1 else str(root / "data"))
os.environ.setdefault("FINVAULT_STATIC_DIR", str(root.parent / "frontend" / "dist"))
sys.path.insert(0, str(root))

import uvicorn  # noqa: E402

uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
