import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="finvault-test-")
os.environ["FINVAULT_DATA_DIR"] = _tmp
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp) / 'test.db'}"
os.environ["FINVAULT_STATIC_DIR"] = str(Path(_tmp) / "nostatic")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import login_throttle  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    login_throttle.hits.clear()
    with TestClient(app) as c:
        c.headers["X-FinVault"] = "1"
        yield c
