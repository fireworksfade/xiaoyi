# ESP32 设备 MQTT 协议

平台与设备之间只通过 MQTT 通信。IoT MCP 的诊断采集（`iot_diagnosis/mqtt.py`）和控制下发（`iot_control/mqtt.py`）都依赖本文约定；固件 [`packages/esp32-node`](../packages/esp32-node) 按本文实现。修改任何一方前先改本文。

## 连接参数

| 项目 | 约定 |
| --- | --- |
| Client ID | 等于 `device_id`，全局唯一；重复会导致 Broker 踢掉旧连接 |
| 会话 | MQTT 3.1.1，`clean_session=false`，离线期间 QoS1 命令由 Broker 保留并在重连后补投 |
| Keep Alive | 默认 30 秒，可在出厂 NVS 中配置 |
| 遗嘱 | 主题 `iot/{device_id}/status`，QoS1，retain，载荷 `{"online": false, "offline_reason": "client_lost"}` |
| 上线消息 | 每次连接成功后发布一条 retain 的完整 `status`，覆盖遗嘱 |
| 主动下线 | 重启、升级、回退前发布 retain 的 `{"online": false, "offline_reason": "restart" \| "firmware_update" \| "firmware_rollback"}`，再正常断开 |
| QoS | 设备上行和平台下行均为 QoS1 |

## 时间戳

`timestamp` 为 UTC ISO 8601（例如 `2026-11-11T08:00:00.123+00:00`），只在设备 SNTP 对时成功后携带。对时前产生的日志在对时后按单调时钟回填；无法回填时省略该字段，由服务端使用接收时间。设备绝不发送 1970 年这类未对时的时间，否则控制服务会丢弃该样本，恢复验证得不到证据。

## 设备上行

| 主题 | 用途 | 频率 |
| --- | --- | --- |
| `iot/{id}/status` | 当前状态，更新诊断的 current state，并作为控制恢复验证的证据 | 每个上报周期、命令执行后、上线时（retain） |
| `iot/{id}/telemetry` | 与 `status` 同载荷，追加历史测量 | 每个上报周期 |
| `iot/{id}/heartbeat` | `{"timestamp", "online": true, "uptime"}` | 每个上报周期 |
| `iot/{id}/logs` | 运行日志 | 事件驱动 |
| `iot/{id}/fault` | 故障事件 | 事件驱动 |
| `iot/{id}/cmd_ack` | 命令回执 | 每条命令一次；重复投递时重发同一回执 |

### status / telemetry 字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `timestamp` | string | 见上文；未对时则省略 |
| `online` | bool | 正常上报时恒为 `true` |
| `device_type` | string | `ESP32` |
| `name` | string | 设备显示名 |
| `firmware_version` | string | 正在运行的应用版本（`esp_app_desc_t.version`） |
| `idf_version` | string | 编译所用 ESP-IDF 版本 |
| `link_type` | string | `ethernet`（QEMU OpenETH）或 `wifi` |
| `wifi_status` | string | 仅 WiFi 设备：`connected` / `disconnected` |
| `rssi` | int | 仅 WiFi 设备，单位 dBm；以太网设备不上报，不伪造 |
| `mqtt_status` | string | `connected`（能发出即已连接） |
| `temperature` | number | 传感器有效时携带，保留两位小数 |
| `sensor_valid` | bool | 最近一次读取是否成功 |
| `sensor_calibrated` | bool | 是否已有校准记录（保存在 NVS，重启后保留） |
| `sensor_backend` | string | `model`（QEMU 热模型，无物理传感器）或 `ntc_adc` |
| `reporting_interval_seconds` | int | 当前上报间隔 |
| `uptime` | int | 自本次启动以来的秒数，重启归零 |
| `free_heap` / `min_free_heap` | int | 当前与历史最低空闲堆，字节 |
| `boot_count` | int | 累计启动次数（NVS） |
| `reset_reason` | string | 本次启动的复位原因，例如 `POWERON`、`SW`、`TASK_WDT`、`PANIC`。QEMU 节点每次重启都是重新上电，复位原因由 flash 里的 core dump 和 NVS 重启标记恢复，详见 [esp32-node README](../packages/esp32-node/README.md#compose-机群) |
| `mqtt_reconnects` | int | 本次启动后的重连次数 |
| `mqtt_keepalive_seconds` | int | 当前 MQTT Keep Alive，出厂默认 30 秒，可由 `set_mqtt_keepalive` 修改 |
| `rollback_version` | string | 另一个 OTA 分区里引导程序仍可启动的旧版本；没有可回退的版本时省略 |

### logs / fault 字段

日志：`{"timestamp", "level", "module", "message", "uptime_ms"}`。`level` 为 `INFO`、`WARNING`、`ERROR`。设备通过 `esp_log_set_vprintf` 转发 ESP-IDF 原始日志：所有组件的 `W`/`E` 级别，以及固件自身模块的 `I` 级别。`module` 即 ESP-IDF 日志 tag，例如 `mqtt_client`、`esp_https_ota`、`net`、`heap`。

故障：`{"timestamp", "fault_type", "level", "message", "uptime_ms"}`。当前 `fault_type`：

| fault_type | 触发 |
| --- | --- |
| `watchdog_reset` | 上次复位原因为 TASK_WDT / INT_WDT / WDT，附 core dump 摘要（任务、PC、回溯） |
| `panic_reset` | 上次复位原因为 PANIC，附 core dump 摘要 |
| `brownout_reset` | 掉电复位（QEMU 不会出现） |
| `ota_rollback` | 新固件未通过启动自检被回滚 |
| `out_of_memory` | 堆分配失败 |
| `sensor_read_failed` | 传感器读取失败 |

注意：恢复验证窗口内出现 `ERROR` / `CRITICAL` 级别的日志或故障，验证会直接判为失败。

## 平台下行

主题 `iot/{id}/cmd`，载荷：

```json
{
  "command_id": "CMD_...",
  "action": "restart_device",
  "parameters": {},
  "reason": "...",
  "issued_by": "...",
  "issued_at": "2026-11-11T08:00:00+00:00",
  "expires_at": "2026-11-11T08:30:00+00:00"
}
```

设备已对时且 `expires_at` 已过时，回执 `failed`；未对时则不校验有效期并记录警告。

### 回执

`iot/{id}/cmd_ack`：`{"command_id", "status": "applied" | "failed", "detail", "timestamp"}`。设备按 `command_id` 去重；重启、升级类命令的 ID 写入 NVS，重启后收到补投也不会再次执行。

### 动作

| action | 参数 | 设备行为 | 回执时机 |
| --- | --- | --- | --- |
| `reconnect_mqtt` | 无 | 停止并重新启动 esp-mqtt 客户端 | 重新连上 Broker 之后 |
| `reconnect_wifi` | 无 | WiFi：断开并重新关联；以太网：重启网口并重新 DHCP | 重新拿到 IP 且 MQTT 恢复之后 |
| `calibrate_sensor` | 无 | 重新初始化传感器驱动并写入校准记录 | 读数恢复之后 |
| `set_reporting_interval` | `seconds`: 1–3600 的整数 | 写入 NVS 并立即生效 | 写入成功后，随后立即上报 status |
| `restart_device` | 无 | 发回执、发布主动下线、`esp_restart()` | 重启之前 |
| `set_mqtt_keepalive` | `seconds`: 10–600 的整数 | 写入 NVS，用新的 Keep Alive 重新连接 Broker | 重新连上之后 |
| `update_firmware` | `version`: `[A-Za-z0-9._-]{1,31}` | 从 `{ota_base}/xiaoyi-node-{version}.bin` 下载，校验镜像内版本号后写入另一 OTA 分区并重启；新固件连上 MQTT 后才确认有效，否则下次复位自动回滚 | 写入并校验成功后、重启之前 |
| `rollback_firmware` | 无 | 另一个 OTA 分区有可启动的旧版本时，把它设为启动分区，发布主动下线（`firmware_rollback`）后重启；没有时回执 `failed` | 切换启动分区之后、重启之前 |
| `inject_fault` | `scenario` | 故障演练，见下文。不属于平台动作目录，只供演练和联调使用 | 立即 |

### 故障演练 inject_fault

| scenario | 固件行为 | 清除方式 |
| --- | --- | --- |
| `memory_leak` | 每秒真实泄漏约 2 KB 堆内存，降到 24 KB 底线后报 `out_of_memory` | 重启 |
| `watchdog_reset` | 写入 NVS：本版本固件每次启动 40–90 秒后让一个任务独占 CPU0，触发任务看门狗、panic、core dump 和重启 | 升级到其他版本或注入 `normal` |
| `panic` | 2 秒后写空指针，触发 `StoreProhibited` | 自动重启 |
| `sensor_error` | 传感器驱动返回总线超时 | `calibrate_sensor` 或重启 |
| `normal` | 停止上述演练并清除 NVS 中的启动故障；已泄漏的内存要到重启才会释放 | — |

网络类故障（`mqtt_timeout`、`unstable`）不在固件里伪造：QEMU 节点通过 Toxiproxy 在网络侧注入，见 [`packages/esp32-node/README.md`](../packages/esp32-node/README.md)。弱信号（`wifi_weak`）只能在 Wokwi 或真机上复现。
