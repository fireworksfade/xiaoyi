#!/usr/bin/env python3
"""Factory-provision one emulated ESP32.

Writes the NVS "factory" namespace (device identity, broker, OTA server, boot
fault) with ESP-IDF's NVS partition generator and merges it with the
bootloader, partition table and the chosen firmware into a 4 MB flash image,
exactly as a production line would flash a blank module.
"""

from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("XIAOYI_ROOT", "/opt/xiaoyi"))
SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,63}$")
SAFE_VERSION = re.compile(r"^[A-Za-z0-9_.-]{1,31}$")
FAULTS = {"", "memory_leak", "watchdog_reset", "sensor_error"}


def setting(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


def run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(f"provision: {' '.join(command[:4])} failed")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: provision.py FLASH_DIR")
    flash_dir = Path(sys.argv[1])
    device_id = setting("DEVICE_ID", "")
    version = setting("FIRMWARE_VERSION", "1.3.1")
    fault = setting("BOOT_FAULT", "")
    if not SAFE_ID.match(device_id):
        raise SystemExit("provision: DEVICE_ID must match [A-Za-z0-9_.-]{1,63}")
    if not SAFE_VERSION.match(version):
        raise SystemExit("provision: FIRMWARE_VERSION must match [A-Za-z0-9_.-]{1,31}")
    if fault not in FAULTS:
        raise SystemExit(f"provision: BOOT_FAULT must be one of {sorted(FAULTS)}")
    app = ROOT / "firmware" / f"xiaoyi-node-{version}.bin"
    if not app.is_file():
        built = sorted(p.stem.removeprefix("xiaoyi-node-") for p in (ROOT / "firmware").glob("*.bin"))
        raise SystemExit(f"provision: firmware {version} was not built; available: {', '.join(built)}")

    rows = [
        ("factory", "namespace", "", ""),
        ("device_id", "data", "string", device_id),
        ("name", "data", "string", setting("DEVICE_NAME", device_id)),
        ("broker_uri", "data", "string", setting("BROKER_URI", "mqtt://mqtt:1883")),
        ("ota_base", "data", "string", setting("OTA_BASE_URL", "http://esp32-ota:8070")),
        ("interval", "data", "u32", str(int(setting("REPORT_INTERVAL", "10")))),
        ("temp_base", "data", "i32", str(round(float(setting("TEMP_BASE", "26.0")) * 10))),
        ("keepalive", "data", "u32", str(int(setting("KEEPALIVE", "30")))),
    ]
    if fault:
        rows += [("boot_fault", "data", "string", fault), ("fault_fw", "data", "string", version)]

    base = ROOT / "base"
    flash_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        nvs_csv = Path(tmp) / "factory.csv"
        nvs_bin = Path(tmp) / "nvs.bin"
        with nvs_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["key", "type", "encoding", "value"])
            writer.writerows(rows)
        run([sys.executable, "-m", "esp_idf_nvs_partition_gen", "generate",
             str(nvs_csv), str(nvs_bin), "0x6000"])
        staged = flash_dir / "flash.bin.tmp"
        run([
            sys.executable, "-m", "esptool", "--chip", "esp32", "merge_bin",
            "--fill-flash-size", "4MB", "-o", str(staged),
            "0x1000", str(base / "bootloader.bin"),
            "0x8000", str(base / "partition-table.bin"),
            "0x9000", str(nvs_bin),
            "0xf000", str(base / "ota_data_initial.bin"),
            "0x20000", str(app),
        ])
        staged.replace(flash_dir / "flash.bin")
    print(f"provision: {device_id} flashed with firmware {version}"
          + (f", boot fault {fault}" if fault else ""), flush=True)


if __name__ == "__main__":
    main()
