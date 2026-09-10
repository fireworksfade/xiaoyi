import os
import tempfile
from pathlib import Path


TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="xiaoyi-backend-tests-"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(TEST_DATA_DIR / 'test.db').as_posix()}"
os.environ["AGENT_RUNTIME"] = "mock"
