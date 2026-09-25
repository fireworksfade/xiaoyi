# MQTT Keep Alive、Session 与 QoS 故障诊断

来源：OASIS MQTT 5.0 官方规范。
适用范围：MQTT 3.1.1/5.0 客户端与 Broker，ESP32 设备。

## Keep Alive

Keep Alive 是客户端承诺发送控制报文的最大空闲间隔。Broker 在超过协议允许的等待窗口仍未收到控制报文时会关闭网络连接。诊断 keep alive timeout 时，应记录客户端配置值、Broker 返回的 Server Keep Alive、最后一个发送和接收报文时间、PINGREQ/PINGRESP、任务调度延迟与网络往返时间。

持续超时通常来自 MQTT 循环没有及时执行、CPU 被高优先级任务占用、WiFi 短暂中断、严重丢包、客户端 Keep Alive 小于现场网络抖动，或 Broker 采用了更小的服务端值。只增大 Keep Alive 可能延后故障发现，不能替代对任务阻塞和网络质量的检查。

## Clean Start 与 Session Expiry

Clean Start 决定连接时是否丢弃已有会话，Session Expiry 决定断线后会话保留多久。设备重连后订阅消失、离线消息丢失或重复订阅时，应核对这两个参数，并检查 CONNACK 的 Session Present。需要持久会话时，客户端 ID 必须稳定且唯一；每次生成随机客户端 ID 会使 Broker 无法恢复原会话。

相同客户端 ID 同时连接时，Broker 通常保留新连接并关闭旧连接，表现为两台设备交替掉线。应记录断开 Reason Code，并检查设备 ID 到客户端 ID 的映射。

## QoS 状态机

QoS 0 没有确认，网络中断时消息可能直接丢失。QoS 1 使用 PUBLISH 与 PUBACK，重发可能造成重复消息，业务层需要幂等。QoS 2 还包含 PUBREC、PUBREL 和 PUBCOMP；任一步状态未保存或报文标识冲突都可能造成卡住、重复或会话恢复失败。

诊断 QoS 故障时记录 packet identifier、DUP 标志、确认报文、重发次数、inflight 数量和 Broker Reason Code。Packet identifier in use 通常说明客户端状态机、会话恢复或标识回收存在问题，而不是简单的网络超时。

## 消息与会话过期

Message Expiry 会让消息在规定时间后失效；设备恢复连接却收不到旧消息时，需要区分消息已经过期、会话已经过期、订阅未恢复和 Broker 未保存消息。排查顺序是确认客户端 ID，再检查 Session Present、Session Expiry、订阅状态、消息 QoS、Message Expiry 和 Broker 持久化配置。

## 验证清单

修复后持续观察多次网络中断与恢复，验证连接不被重复客户端顶替、订阅能够按预期恢复、QoS 1 重复消息可安全处理、QoS 2 状态完整，以及 Keep Alive 在最坏调度和网络条件下仍能正常完成心跳。
