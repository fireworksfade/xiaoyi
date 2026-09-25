"""MCP 测试环境：数据库与外部存储指向临时路径，避免依赖仓库内数据目录。"""

import os
import tempfile
from pathlib import Path

_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="xiaoyi-mcp-tests-"))
os.environ.setdefault("DIAGNOSIS_DATABASE_PATH", str(_TEST_DATA_DIR / "iot_diagnosis.db"))
os.environ.setdefault("CONTROL_DATABASE_PATH", str(_TEST_DATA_DIR / "iot_control.db"))
os.environ.setdefault("MQTT_ENABLED", "false")
