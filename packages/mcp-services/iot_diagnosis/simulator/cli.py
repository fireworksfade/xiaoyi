"""CLI 入口：单设备模式或机群模式。"""

from __future__ import annotations

import argparse
import logging
import signal
import threading
import time

from .device_simulator import DeviceSimulator
from .fleet_loader import load_fleet
from .models import DeviceProfile
from .command_handler import SCENARIOS

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ESP32 设备模拟器（单设备模式或 --fleet 机群模式）"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--device-id", default="ESP32_05")
    parser.add_argument("--scenario", choices=list(SCENARIOS), default="mqtt_timeout")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument(
        "--fleet",
        help="机群配置 JSON 路径；提供后忽略 --device-id/--scenario/--interval",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.fleet:
        profiles = load_fleet(args.fleet)
    else:
        profiles = [
            DeviceProfile(
                device_id=args.device_id,
                scenario=args.scenario,
                interval=args.interval,
            )
        ]

    logger.info("启动 %d 台模拟设备（MQTT %s:%d）", len(profiles), args.host, args.port)
    simulators = [DeviceSimulator(profile, args.host, args.port) for profile in profiles]
    for simulator in simulators:
        simulator.start()

    # SIGTERM（docker stop）与 SIGINT 统一走优雅下线：每台设备主动发布
    # online:false 后断开，而不是触发遗嘱里的 client_lost
    stop_requested = threading.Event()

    def _request_stop(signum, _frame) -> None:
        logger.info("收到退出信号（%s），正在下线全部模拟设备…", signal.Signals(signum).name)
        stop_requested.set()

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    try:
        while not stop_requested.is_set():
            time.sleep(1)
    finally:
        for simulator in simulators:
            simulator.stop()


if __name__ == "__main__":
    main()
