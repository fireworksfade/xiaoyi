# Harness Desktop 可选插件验证记录

日期：2026-09-30。Windows，Desktop 0.2.0-rc.2，插件 @xiaoyi/dsh-iot 0.2.0。

## 主对话实机验证

使用 Desktop 自带 CLI 安装插件，重新启动后由用户手动连接。连接页显示 16 个业务工具，另有 2 个固定连接管理工具；数量随已启用的 MCP 目录和记忆开关变化。

在 Harness 主对话的标准模式、DeepSeek-V41-Flash（High）中完成三轮查询：

| 查询 | 实际原生调用 | 结果 |
| --- | --- | --- |
| 列出设备并统计在线／离线数量 | xiaoyi_connection_status、xiaoyi_iot-mcp-local__list_devices | 全量 12、离线 0、在线 12，主对话生成回答 |
| 检索 ESP32 MQTT 问题的知识和个人记忆 | xiaoyi_iot-mcp-local__search_knowledge、xiaoyi_search_memory | 两类检索正常返回，主对话回答包含来源 |
| 重新连接后查询 ESP32_05 状态 | xiaoyi_iot-mcp-local__get_device_status | 在线、WiFi connected、RSSI −53、MQTT disconnected，主对话正常完成 |

三轮后端记录均带 harness_native=true、Desktop 实例与独立轮次，最终为 completed；执行者为 deepseek-harness。后端只记录工具审计，没有 answer.delta 生成事件或后端聊天模型调度。验证依据为实际主对话轨迹与后端事件。

此处设备数据来自本地 IoT MCP 与默认模拟机群，验证的是 Desktop 到业务服务的调用链，不是物理设备验收。实机消息只执行查询，未发起诊断、控制、修复提案或记忆候选。

## 原生开关

在已连接状态关闭插件：组件显示“已关闭”，侧栏入口移除，后端连接租约 enabled=false。再次开启恢复组件，用户手动重新登录后恢复 16 个业务工具；最终保持开启且已连接。未在物理设备控制进行时切换开关，在途取消通过隔离测试覆盖。

## 自动测试与服务检查

- 插件构建及 TypeScript 编译通过，9 项 Node 测试通过：真实 Cordis 加载、原生动态注册／撤销、轮次隔离、直接调用、审计关闭、认证网关共存、凭据隔离和 SSE。
- 27 项相关后端回归通过（Harness、原生接口、诊断关联、审批、Dispatcher）；补充在途取消用例后，原生接口 3 项测试再次通过。
- 修改的原生 Python 服务、API 和测试 Ruff 检查通过。
- 真实 IoT MCP 的 SDK 冒烟成功注册 16 个工具，list_devices 返回正常，审计记录正常关闭。
- 可选面板 Chromium 集成通过：错误密码、连接、知识／记忆页面、附件、对话、SSE 和卸载。使用隔离数据库与 mock 后端，不调用真实设备；该测试不作为主对话证据。
- Docker 后端和 IoT MCP 健康；运行服务已加载 /api/v1/harness/native/*，数据库为 0010_harness_connections（head）。本次后端更新通过源码挂载加重启生效，未重建镜像。

## 范围

插件是平台扩展，业务服务仍独立部署。高风险审批、候选记忆确认与平台管理写操作保留人工流程。0.1.x 的 iframe/SSE 验证不能替代上述 0.2.0 主对话验证。其他 Desktop 版本需重新验证。

安装包通过仓库根目录 npm run plugin:pack 生成到 output/。构建产物、环境文件、账号凭据、数据库和本地审计日志不提交到仓库。
