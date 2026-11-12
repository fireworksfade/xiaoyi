# ESP32 设备仿真（xiaoyi-node）

平台的设备端是一份真实的 ESP-IDF 固件，同一份源码有两种运行方式：

| 运行方式 | 构建变体 | 用途 | 网络 | 传感器 |
| --- | --- | --- | --- | --- |
| **QEMU**（主力，长期运行） | `sdkconfig.defaults.qemu` | Compose 机群、故障演练、端到端测试 | OpenCores 以太网 + 用户态 NAT | 热模型（`sensor_backend=model`） |
| **Wokwi**（补充） | `sdkconfig.defaults.wokwi` | WiFi 建链与断线原因、ADC 传感器与校准 | WiFi 连接 `Wokwi-GUEST` | NTC 热敏电阻接 ADC1（`sensor_backend=ntc_adc`） |

设备与平台的 MQTT 约定见 [设备协议](../../docs/device-protocol.md)。

## 固件里哪些是真实运行的

- esp-mqtt 客户端：持久会话、QoS1、遗嘱、Keep Alive、自动重连，以及 `MQTT_EVENT_ERROR` 的原始错误码。
- ESP-IDF 日志：通过 `esp_log_set_vprintf` 原样转发到 `iot/{id}/logs`，离线期间排队，对时后按单调时钟回填时间戳。
- NVS：出厂数据（`factory` 命名空间，由烧录步骤写入）与运行配置（上报间隔、校准记录、启动计数）。
- OTA：`esp_https_ota` 从 OTA 服务器下载，校验镜像内版本号，写入另一 OTA 分区；新固件连上 Broker 后才确认有效，否则下次复位由引导程序自动回滚。另一个分区里的旧版本仍有效时，状态带 `rollback_version`，`rollback_firmware` 可以手动切回。
- MQTT Keep Alive 出厂为 30 秒，`set_mqtt_keepalive` 修改后写入 NVS 并重新连接。
- 崩溃：任务看门狗、panic、core dump 写入 flash，下次启动时上报复位原因与回溯。
- SNTP 对时，以及命令有效期 `expires_at` 校验。

QEMU 不模拟 WiFi 射频和传感器外设。QEMU 节点不上报 RSSI，也不伪造信号强度；温度来自固件内的热模型，并明确标注为 `sensor_backend=model`。

## Compose 机群

`docker compose up -d --build` 会构建 `xiaoyi-esp32-node:local` 镜像，并启动以下服务：

- `esp32-ota`：OTA 固件服务器，宿主机端口 8070。
- `toxiproxy`：网络故障注入，API 在宿主机 8474 端口。
- 9 台设备。

首次构建要拉取约 4.4 GiB 的 `espressif/idf:v5.5.4` 镜像。Debian、PyPI 和乐鑫资源的下载源可在 `.env` 中通过 `DEBIAN_MIRROR`、`PYPI_INDEX`、`IDF_GITHUB_ASSETS` 改成国内镜像，示例见 `.env.example`。

| 服务 | 设备 | 固件 | 现场问题 |
| --- | --- | --- | --- |
| esp32-01 / 02 / 03 / 07 | 车间、冷库等 | 1.1.4–1.3.1 | 正常 |
| esp32-04 | 成品仓库-温湿度终端 | 1.2.0 | 慢速堆泄漏，约一小时耗尽（`BOOT_FAULT=memory_leak`） |
| esp32-05 | 机房-边缘网关 | 1.2.0 | 上行每 10 分钟中断 75 秒，设备 Keep Alive 超时（`No PING_RESP`）后反复重连（Toxiproxy） |
| esp32-08 | 配电房-温度监测 | 1.3.1 | 工作任务死循环，任务看门狗导致崩溃循环；升级到其他版本后消失 |
| esp32-09 | 锅炉房-烟温监测 | 1.2.0 | 传感器总线超时 |
| esp32-10 | 温室大棚-环境监测 | 1.3.1 | 上行每 4 分钟被对端断开，设备反复重连（Toxiproxy） |

`ESP32_06`（办公区-环境终端）是 Wokwi 设备，不在 Compose 中。

每个容器就是一台设备：

- 容器的标准输出就是串口控制台：`docker compose logs -f esp32-08` 可以看到 `Guru Meditation`、看门狗输出和回溯。
- `docker compose restart esp32-02` 等于断电重启；`docker compose stop esp32-02` 等于断电，Broker 会在 1.5 倍 Keep Alive 后发布遗嘱。
- 设备自己重启（`restart_device`、OTA、panic、看门狗）时，QEMU 以 `-no-reboot` 运行并退出，入口脚本在同一个容器里重新上电。这样做的原因是 Espressif QEMU 在软件复位（`SW_CPU_RESET`）后外设状态不干净，下一次启动会在 `esp_timer_init` 中崩溃。重新上电会丢失 RTC 里的复位原因，所以 QEMU 构建开启了 `CONFIG_XIAOYI_EMULATED_POWER_CYCLE`，由固件从 flash 里真实留下的证据恢复复位原因：有 core dump 时，按其中的 panic 原因判定为 `TASK_WDT`、`INT_WDT` 或 `PANIC`；主动重启前写入的 NVS 标记对应 `SW`。
- flash 镜像保存在 `esp32-flash` 卷中，NVS、OTA 分区和 core dump 在重启后保留。修改 `FIRMWARE_VERSION`、`BOOT_FAULT` 等出厂参数后，需要先停机并重新烧录（等于恢复出厂）：

```bash
docker compose stop esp32-02
docker compose run --rm esp32-02 provision
docker compose up -d esp32-02
```

### 可升级的固件版本

镜像构建时会编译 `1.1.4 1.2.0 1.3.1 1.3.9 1.4.0`，以及一个故意启动自检失败、用来演练回滚的 `1.4.1-rc1`。所有版本都由 `esp32-ota` 提供下载，对应的 `.elf` 也放在同一目录（`http://127.0.0.1:8070/`），用于解析崩溃回溯：

```bash
xtensa-esp32-elf-addr2line -pfiaC -e xiaoyi-node-1.3.1.elf 0x400d1a2c
```

要构建其他版本，修改 `qemu/Dockerfile` 中的 `FIRMWARE_VERSIONS` 构建参数。请求一个不存在的版本时，OTA 会真实失败（HTTP 404），设备回执为 `failed`。

## 故障演练

### 固件内故障

固件内的故障通过 `inject_fault` 命令触发，场景见 [设备协议](../../docs/device-protocol.md#故障演练-inject_fault)：

```bash
docker compose exec -T mqtt mosquitto_pub -q 1 -t iot/ESP32_02/cmd -m '{"command_id":"DRILL_1","action":"inject_fault","parameters":{"scenario":"memory_leak"}}'
```

### 网络故障

网络故障通过 Toxiproxy 注入，每台设备有自己的代理：

```bash
docker compose exec esp32-02 netfault.py blackhole ESP32_02     # 上行完全中断
docker compose exec esp32-02 netfault.py latency ESP32_02 8000 4000
docker compose exec esp32-02 netfault.py reset ESP32_02          # 12 秒内设备发出的包都被对端重置
docker compose exec esp32-02 netfault.py resets ESP32_02 240     # 每 240 秒重置一次，前台持续运行
docker compose exec esp32-02 netfault.py clear ESP32_02
```

Broker 一侧的证据可以用 `docker compose logs -f mqtt` 查看，例如 `has exceeded timeout`、`already connected, closing old connection`。

Toxiproxy 对 Broker 一侧发的是 TCP RST。但 QEMU 用户态网络（slirp）在宿主机一侧终结 TCP，设备看到的是对端关闭连接：`transport error: esp_tls_last_esp_err=0x8008 (ESP_ERR_ESP_TLS_TCP_CLOSED_FIN)`。真机在 NAT 或负载均衡重置连接时通常看到的是 `sock_errno=104 (Connection reset by peer)`。

### 临时设备

临时设备不进入常驻机群，适合演练和端到端测试：

```bash
docker compose run -d --rm --name lab-01 -e DEVICE_ID=LAB_01 -e BROKER_URI=mqtt://mqtt:1883 esp32-node
```

## Wokwi

Wokwi 用来覆盖 QEMU 做不到的部分：WiFi 关联、断线原因码、RSSI、ADC 读数和校准。

1. 构建 WiFi 变体（在本目录执行，Windows PowerShell 中把 `$PWD` 写成 `${PWD}`）：

   ```bash
   docker run --rm -v "$PWD:/project" -w /project espressif/idf:v5.5.4 \
     idf.py -B build-wokwi -D SDKCONFIG=build-wokwi/sdkconfig \
     -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.defaults.wokwi" build
   ```

2. 用 VS Code 打开 `packages/esp32-node`，安装 Wokwi 扩展，执行 “Wokwi: Start Simulator”。`wokwi.toml` 与 `diagram.json` 已经配置了 ESP32 DevKitC 和接在 GPIO34 上的 NTC。
3. VS Code 扩展自带私有 IoT 网关，固件通过 `host.wokwi.internal:1883` 连到本机 Compose 中的 Broker；OTA 地址为 `host.wokwi.internal:8070`。网页版 Wokwi 的私有网关需要付费计划，免费的公共网关无法访问本机网络。
4. 在仿真界面拖动 NTC 的温度滑块可以改变读数；`calibrate_sensor` 会重新初始化 ADC 和校准方案。

### 故障场景

`wokwi/` 下的三个场景对应记忆中两条待确认经验（WiFi 断开原因码、NTC 开路/短路）。在 VS Code 中执行 “Wokwi: Select Config File”，选择场景目录下的 `wokwi.toml`，再执行 “Wokwi: Start Simulator”。

| 场景 | 接线或配置 | 预期串口日志 |
| --- | --- | --- |
| `wokwi/no-ap` | SSID 改为不存在的 `Wokwi-MISSING`，需要单独构建 `build-wokwi-noap` | `wifi disconnected, reason=201 (NO_AP_FOUND)`，并按间隔重试 |
| `wokwi/ntc-open` | 热敏电阻开路时模块输出为 0 V，用 GPIO34 直接接 GND 模拟 | `NTC reading at rail (raw=…): open or short circuit`，`sensor_valid=false` |
| `wokwi/ntc-short` | GPIO34 直接接 3V3 | 同上，`raw` 接近 4095 |

构建 `no-ap` 场景使用的固件：

```bash
docker run --rm -v "$PWD:/project" -w /project espressif/idf:v5.5.4 \
  idf.py -B build-wokwi-noap -D SDKCONFIG=build-wokwi-noap/sdkconfig \
  -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.defaults.wokwi;wokwi/sdkconfig.defaults.no-ap" build
```

`no-ap` 场景连不上 WiFi，所以平台收不到任何数据，证据只有串口日志。每个场景的 `wokwi.toml` 都设置了 `rfc2217ServerPort = 4000`：仿真运行时，串口通过 RFC2217（telnet）开放在本机 `127.0.0.1:4000`，脚本可以直接连上去读，不需要从界面复制。两个 NTC 场景能连上 Broker，可以在平台上发起诊断，再尝试 `calibrate_sensor`。

已知限制：

- Wokwi 的文档没有提供调节 RSSI 或模拟随机掉线的方法，所以弱信号场景仍然需要真机。实测 Wokwi 上报的 RSSI 会在 -69 到 -98 dBm 之间自行波动，不代表真实信号强度，诊断时不要据此判断信号弱。
- 默认 CPU 限速约 8 MHz。仿真时钟比真实时间慢时，Broker 一侧可能出现假的 Keep Alive 超时，演练时要排除这种情况。
- 设备 ID 默认为 `ESP32_06`，可在 `sdkconfig.defaults.wokwi` 中修改。

## 本地开发

```bash
# QEMU 变体，单独编译
docker run --rm -v "$PWD:/project" -w /project espressif/idf:v5.5.4 \
  idf.py -B build-qemu -D SDKCONFIG=build-qemu/sdkconfig \
  -D "SDKCONFIG_DEFAULTS=sdkconfig.defaults;sdkconfig.defaults.qemu" build
```

主要源码位于 `main/`：`link.c`（MQTT）、`commands.c`（命令）、`ota.c`、`report.c`（状态、复位原因与 core dump）、`log_forward.c`、`drills.c`（故障演练）、`sensor.c`、`net.c`。
