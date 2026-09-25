# Mosquitto Broker 配置与日志诊断

来源：Eclipse Mosquitto 官方 mosquitto.conf 手册。
适用范围：Mosquitto 2.x、本地与实验室 MQTT Broker。

## 采集信息

记录 Mosquitto 版本、监听地址和端口、协议版本、客户端 ID、来源地址、连接与断开日志、Keep Alive、会话参数、持久化状态、消息大小和 inflight 限制。容器化部署还应记录端口映射、配置文件挂载、数据卷和容器重启次数。

## 连接失败

TCP connection refused 通常表示端口没有监听、地址或端口错误、容器未就绪，发生在 MQTT 认证之前。连接建立后收到 not authorized 或 bad user name or password，才进入身份或授权路径。Broker 只监听 loopback 时，其他容器或主机无法连接。排查应先确认监听，再确认网络路径，最后分析 MQTT CONNACK 和 Broker 日志。

## Keep Alive 与断线

Broker 会根据客户端 Keep Alive 或服务端限制清理失去心跳的连接。若大量客户端同时超时，应检查 Broker 负载、宿主网络和公共上游链路；只有单个设备超时时，应检查该设备调度、无线连接和 client_id。重复 client_id 会造成连接相互替换，需要从 Broker 日志核对旧连接关闭与新连接建立的时间。

## 持久化与会话恢复

启用持久化后，Broker 会周期性保存内存数据库。诊断重启后订阅或离线消息丢失时，应检查 persistence、persistence_location、目录写权限、数据卷是否真正持久化，以及关闭前是否有保存错误。会话恢复还取决于客户端 ID、Clean Start/Clean Session、Session Expiry 和消息 QoS，不能仅检查 Broker 文件是否存在。

## 容量与流控

消息过大、排队消息过多、inflight 达到限制或客户端处理过慢，都可能造成发布失败、延迟或断开。应记录单条消息大小、发布频率、队列深度、未确认消息和慢客户端。调整限制前先确认业务消息是否异常膨胀，以及消费者是否持续落后。

## 日志判读顺序

按同一 client_id 建立时间线：网络连接建立、CONNECT、CONNACK、订阅、发布、确认、心跳、断开。将 Broker 时间与设备 UTC 时间对齐。客户端只看到 disconnected 时，Broker 日志往往能区分正常关闭、Keep Alive 超时、协议错误、重复客户端 ID和服务端主动拒绝。

## 修复验证

修复后验证本机和设备网络路径、正确与错误凭据、Broker 重启后的会话恢复、重复 client_id 检测、Keep Alive、QoS 确认以及数据卷持久化。配置变更应保存版本和生效时间，便于诊断记录关联到准确配置。
