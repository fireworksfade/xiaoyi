# ESP-MQTT 错误事件与连接故障诊断

来源：Espressif ESP-MQTT 官方文档；OASIS MQTT 5.0 规范。
适用范围：ESP32、ESP-IDF 5.x/6.x、MQTT 3.1.1 与 MQTT 5 客户端。

## 典型症状

设备反复出现 MQTT disconnected、connection refused、not authorized、bad user name or password、broker unavailable、transport error、TLS error、keep alive timeout，或者连接成功后很快再次断开。ESP-MQTT 的 MQTT_EVENT_ERROR 会通过 error_handle 提供错误类型；诊断时应同时记录 error_type、连接返回码、底层 esp-tls 错误、socket errno、Broker 地址、端口和客户端 ID，不能只保留“连接失败”这一条文本。

## 分类方法

连接拒绝且返回认证相关原因时，优先检查用户名、密码、客户端证书以及 Broker 端授权配置。Broker unavailable、connection refused 或 socket refused 通常指向地址错误、端口错误、Broker 未启动、监听地址不匹配或网络路径不可达。DNS 解析错误应与 TCP 超时分开处理；先记录解析后的目标 IP，再检查网关和路由。

相同 client_id 被另一连接使用时，旧连接可能被 Broker 主动关闭，日志会表现为周期性上线和掉线。应检查设备 ID 到 client_id 的生成规则，确保每台设备唯一。Keep Alive 超时表示在约定窗口内没有有效控制报文到达 Broker；可能是任务阻塞、网络丢包、心跳间隔过大，也可能是 Broker 的 Server Keep Alive 覆盖了客户端配置。

## 确认步骤

第一步记录 MQTT_EVENT_ERROR 的完整字段和断线前最后一条事件。第二步分别验证 DNS、TCP 端口和 MQTT CONNECT，避免把三层问题合并成一个“Broker 故障”。第三步对照 Broker 日志确认是服务端拒绝、客户端主动断开还是超时清理。第四步检查 client_id、Clean Start/Clean Session、Session Expiry、Keep Alive、QoS 和重连间隔。第五步观察 WiFi 是否同时断开；如果 WiFi 状态稳定而 MQTT 失败，应优先留在 MQTT 或传输层排查。

## 处理建议

认证错误应修正凭据或服务端授权后再重试，避免无间隔重连。网络与 Broker 暂时不可用时使用有上限的指数退避。Keep Alive 应大于正常调度抖动和最坏网络延迟，并确保 MQTT 任务能及时获得 CPU。需要持久会话时正确配置 Session Expiry，并保存订阅恢复状态。处理完成后至少验证连接持续时间、PINGREQ/PINGRESP、订阅恢复和 QoS 消息确认。

## 容易误判

WiFi 显示 connected 不代表 DNS、TCP 或 Broker 可达。connection refused 不等于认证失败；它通常发生在 MQTT CONNECT 之前。MQTT disconnected 只是结果，不是根因。日志中若同时出现 watchdog、heap low 或长时间任务阻塞，应优先解决设备运行时问题，因为它们会间接造成心跳超时。
