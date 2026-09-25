# ESP32 WiFi 断线原因与重连诊断

来源：Espressif ESP-IDF Wi-Fi Driver 与 esp_wifi API 官方文档。
适用范围：ESP32 Station 模式，ESP-IDF 5.x/6.x。

## 典型症状

常见日志包括 WIFI_EVENT_STA_DISCONNECTED、beacon timeout、no AP found、auth fail、handshake timeout、association leave、RSSI 过低以及反复 connected/disconnected。诊断必须保存断线 reason code、SSID、BSSID、信道、RSSI、重试次数和事件时间；只有“WiFi disconnected”无法区分信号、认证、接入点和应用状态机问题。

## 原因分类

no AP found 通常与 SSID 不存在、扫描信道限制、AP 离线或信号太弱有关。auth fail 和 handshake timeout 应检查密码、认证模式、PMF 配置以及 AP 兼容性。beacon timeout 表示一段时间未收到 AP Beacon，常见于弱信号、干扰、AP 切换信道或设备长时间无法调度 WiFi 任务。RSSI 持续低于约 -75 dBm 时应优先检查距离、天线方向、外壳遮挡、供电噪声和同信道拥塞。

ESP-IDF 的一次 esp_wifi_connect 调用只发起一次连接尝试；如果应用没有在断线事件中重新连接，设备不会自动无限恢复。扫描与连接同时发生还可能返回状态冲突，因此重连状态机应避免在正在连接时重复启动扫描或连接。

## 确认步骤

第一步按时间对齐断线 reason、RSSI、MQTT 状态和设备 uptime。第二步扫描目标 SSID，记录 AP 数量、BSSID、信道和信号强度。第三步固定到已知稳定 AP 进行对照，区分设备问题与现场无线环境。第四步核对应用是否收到断线事件并执行了有限退避重连。第五步检查 DHCP 是否成功；已关联 AP 但没有 IP 地址时，应归类为地址获取或网络层故障，而不是射频断线。

## 处理建议

为重连设置退避和最大快速重试次数，避免高频扫描进一步占用无线资源。多 AP 环境可按 BSSID 或信号阈值选择候选 AP。弱信号场景调整天线、AP 位置与信道，并记录修复前后的 RSSI 和丢包率。认证失败时先校验凭据和认证模式，不要无限重试。连接恢复后应确认 IP、DNS、MQTT 和业务上报均恢复，不能只以 WIFI_EVENT_STA_CONNECTED 作为完成标志。

## 容易误判

RSSI 瞬时正常不能排除周期性干扰，建议观察时间序列。MQTT 掉线可能只是 WiFi 断线的后果。设备重启后 WiFi 重新连接不代表重连逻辑正确，应结合 reset reason 和 uptime 判断是否通过重启掩盖了问题。
