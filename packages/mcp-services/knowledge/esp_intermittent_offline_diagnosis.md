# ESP32 设备间歇离线诊断

来源：Espressif ESP-IDF Wi-Fi 驱动、ESP-NETIF、电源管理与 LwIP 官方文档。
适用范围：ESP32、ESP-IDF 5.x/6.x、MQTT 长连接场景。

## 故障特征

设备在线状态反复跳变：`status.online` 在 0/1 之间震荡，heartbeat 停止数秒到数分钟后自行恢复；离线片段开始时常见一条 WARNING 日志（如 beacon loss、connection lost），随后日志与遥测完全静默；恢复后 uptime 不清零说明设备未重启，只是链路断开。与 mqtt_timeout 的区别在于：间歇离线时 WiFi 层同步断开（rssi 缺失或 wifi_status 非 connected），而 mqtt_timeout 通常 WiFi 正常、仅 MQTT 心跳超时。

## 常见根因

RSSI 长期低于 -75 dBm 的弱信号环境；AP 信道切换、负载均衡或漫游踢除客户端；DHCP 续租失败导致 IP 失效；modem sleep 与心跳周期配合不当，被 Broker 或 NAT 判定失活；堆内存耗尽导致 WiFi 任务崩溃后自动重启；路由器侧防火墙清理 NAT 表项使长连接中断；供电不稳引起射频性能下降。

## 确认步骤

第一步导出离线时间段前后的 status 与日志，确认断连从 WiFi 层还是 MQTT 层开始。第二步核对 `offline_reason` 字段：client_lost 表示进程异常或断电，graceful_shutdown 表示正常停机，其余多为链路故障。第三步对比 RSSI 曲线与离线时刻，确认是否每次离线都伴随信号跌落。第四步检查离线后 uptime 是否归零：归零说明设备重启，应按复位原因继续排查；未归零说明仅网络断开。第五步统计离线间隔与时长，周期性短离线多为 keep alive/NAT 问题，随机长离线多为信号或 AP 问题。

## 修复方法

弱信号场景调整天线位置、缩小与 AP 的距离或改用有线回传；下发 reconnect_wifi 可立即重建连接并清除网络类故障标志；疑似运行时异常时使用 restart_device（高风险，需审批）复位协议栈；NAT/心跳超时场景调短 MQTT keep alive 或开启 Broker 侧 persistent session；关闭不必要的 modem sleep 或调高主动门限；确认 DHCP 租约与 AP 侧客户端空闲超时配置。

## 验证方法

修复后持续观察至少一个完整业务周期，统计在线率与离线次数是否收敛到零；确认恢复验证窗口内状态采样全部在线且无新 ERROR 日志；断网重连演练后确认心跳、遥测与命令通道全部恢复正常节奏。
