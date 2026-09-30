# 小忆 IoT — DeepSeek Harness Desktop 插件

插件 **0.2.0**，目标 Desktop **0.2.0-rc.2**，包名 `@xiaoyi/dsh-iot`。

登录后，设备、知识、诊断和记忆工具直接注册到 Harness 的工具运行时。用户在 **Desktop 主对话**发送消息，由 Harness 当前配置的 **DeepSeek 模型**选择工具、读取结果并回答。主对话工具调用不启动小忆后端的聊天 Agent，也不使用后端聊天模型配置。原平台界面是可选的数据与审批面板。

Python 后端、IoT MCP、MQTT 和数据库仍负责业务执行、权限、诊断关联、修复预算、记忆和审计。安装包不会自动部署这些服务。前端服务仅在打开数据与审批面板时需要；主对话原生工具不依赖前端页面。

这是小忆平台的可选扩展。平台原有的独立浏览器对话、模型配置与部署方式继续可用；插件不替换平台主架构。IoT MCP 诊断工具内部的专业诊断服务继续使用自己的配置。

## 构建与安装

在仓库根目录执行：

```powershell
npm ci
npm run plugin:build
npm run plugin:test
npm run plugin:pack
```

输出 `output/xiaoyi-dsh-iot-0.2.0.tgz`，包含构建后的 Host、Client、类型声明、bundle 配置、图标和说明，不含项目数据、环境文件或密钥。

先部署本次更新的后端代码并应用 `0010_harness_connections` 迁移：

```powershell
docker compose up -d --build backend iot-mcp
docker compose exec -T backend python scripts/bootstrap_local_mcp.py
```

后端容器启动时执行迁移；生产部署按原项目流程执行 `python -m app.cli deploy`。可选平台面板需要 `npm run dev` 启动前端。

当前开发 Compose 挂载本地源码。仅修改已挂载的代码或迁移时，重启相应容器即可生效；依赖、Dockerfile 或服务配置改变时需重建。详见根 README 的 [Docker 更新说明](../../README.md#更新-docker-服务)。

在 Desktop → 插件 → 添加插件，填写包的绝对路径，例如 `D:\last-work\output\xiaoyi-dsh-iot-0.2.0.tgz`，随后开启“小忆 IoT”。也可通过 **Desktop 自带** CLI 安装：

```powershell
& "D:\DeepSeek\resources\runtime\cli\bin\dsh.cmd" plugin --profile desktop add "D:\last-work\output\xiaoyi-dsh-iot-0.2.0.tgz"
```

更新安装包后，完全退出并重新打开 Desktop，以清除 Host 模块缓存。不要用另行 npm 安装的 CLI 修改 Desktop profile。

从侧栏“小忆 IoT”登录小忆后端账号。看到“主对话工具已连接”和工具数量后，回到 **Harness 主对话**创建新一轮消息。例如：

> 使用小忆工具列出设备，再查询 ESP32_05 的状态。只做只读查询。

DeepSeek 模型与 API Key 使用 Harness 自身的配置。插件登录的是小忆业务平台，不是模型账号。重启、退出连接或关闭插件后需要重新连接。

## 工具与操作

目录来自后端已启用、已连接的 MCP 服务。名称以 `xiaoyi_` 开头，保留服务别名以区分来源；数量取决于 MCP 配置和记忆开关。

| 类别 | 主对话能力 |
| --- | --- |
| 设备与日志 | 列出设备，读取状态、日志与动作结果 |
| 知识与诊断 | 查询知识，诊断故障，查看诊断记录 |
| 修复 | 基于本轮可信诊断执行低风险动作；高风险动作创建待审批提案 |
| 记忆 | `xiaoyi_search_memory`、`xiaoyi_get_memory`、`xiaoyi_propose_memory` |
| 连接管理 | `xiaoyi_connection_status`、`xiaoyi_refresh_tools` |

只注册 `read_only` 和 `proposal_only` 工具。停用工具、审批决定、知识摄取和删除等人工管理工具不交给模型。后端每次调用重新检查策略。提案审批、候选记忆确认、知识上传、模型设置及 MCP 管理通过“打开数据与审批面板”进行，保留权限、CSRF 和版本校验。

0.1.x 的任务委派工具已从主对话目录移除。后端为原生调用创建的 Run 只记录审计、预算与记忆上下文，不排队执行后端模型。Harness 每轮结束会关闭审计记录；主对话回答保存在 Harness。

## 启用和停用

- 开启：加载连接面板和两个管理工具；登录后动态注册业务工具。
- 关闭：撤销工具、面板、RPC 和 SSE，终止在途请求，撤销租约并停止这个用户、这个实例关联的活动 Run。
- 已下发命令由业务后台继续跟踪；关闭插件不能撤回已发出的命令。
- 知识、记忆和历史保留；重新开启不会自动重发任务或命令。
- 心跳 20 秒，租约 90 秒。异常退出后，后端约每 5 秒扫描并停止过期连接任务。
- 其他客户端、MQTT、数据库、Qdrant 和共享记忆任务不受开关影响。

使用 Desktop 原生插件开关；如果版本提示重启，按提示重启。

## 地址与凭据

默认后端 `http://127.0.0.1:8000`，可选前端 `http://127.0.0.1:3000`。在 Desktop profile 的 `cordis.patch.yml` 覆盖配置：

```yaml
- id: xiaoyi-iot
  config:
    backendUrl: http://127.0.0.1:8000
    frontendUrl: http://127.0.0.1:3000
    instanceId: xiaoyi-desktop
    requestTimeoutMs: 30000
```

地址允许本机 HTTP 或 HTTPS，不含路径、查询或凭据。不同 Desktop 实例使用不同 `instanceId`。

Cookie/CSRF 只保存在 Host 内存，模型、iframe 和安装包不接收凭据。模型不能指定用户身份、租约实例、记忆归属或修复关联标识。插件不读取或保存 Harness 的模型密钥。

## 验证

`npm run plugin:test` 覆盖真实 Cordis 加载、卸载、原生注册、每轮隔离、直接调用路径、审计关闭与 Host 凭据隔离。后端 `test_harness_native.py` 和 `test_harness.py` 覆盖无模型调度、权限、诊断关联、重复调用拦截、租约失效及取消。

`npm run plugin:test:browser` 验证可选面板，需要隔离后端（独立数据库、`AGENT_RUNTIME=mock`、无真实设备）于 18002 和前端于 13000，可通过 `HARNESS_TEST_BACKEND/FRONTEND` 覆盖。这项测试不作为 Desktop 主对话验证证据。

实机验证详情见 [验证记录](../../docs/harness-plugin-validation.md)。旧版 0.1.3 的 iframe/SSE 验证不能替代 0.2.0 主对话工具验证。兼容目标仅为 Desktop 0.2.0-rc.2。
