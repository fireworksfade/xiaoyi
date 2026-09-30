# Harness Desktop 主对话接入

插件 0.2.0 的安装与使用见 [插件说明](../packages/harness-plugin/README.md)，目标 Desktop 0.2.0-rc.2。

此接入是小忆平台的可选扩展，平台可以独立使用原有前端和后端 Agent。实机与测试范围见 [验证记录](harness-plugin-validation.md)。

## 原生调用链

Harness 主对话 → Harness 当前 DeepSeek 模型 → ctx.tools 原生工具 → 插件 Host → /api/v1/harness/native → MCP/记忆服务 → 工具结果 → 主对话回答。

后端聊天 Agent 与模型调度器不参与原生工具调用。后端创建带 harness_native、实例与轮次关联的 Run，用于审计、可信诊断、修复预算、记忆来源及命令追踪。每轮工具串行执行，主对话结束时关闭 Run。诊断工具本身可按原实现使用专业诊断服务。

GET /tools 返回允许目录；POST /runs 创建幂等上下文；POST /runs/{id}/call 检查所有者、实例、状态及最新策略后执行；POST /runs/{id}/close 结束记录。写请求要求 CSRF，所有请求要求登录及有效租约。

Host 适配 Harness 的 JSON Schema 子集，MCP 保留完整校验。身份和诊断记忆由后端注入；修复只能关联本轮成功诊断，采用记忆版本经预算边界校验。明确失败后的有界再诊断复用原服务。高风险提案及记忆候选需人工确认，审批和管理写工具不交给模型。

## 面板与凭据

侧栏首先显示主对话连接状态和工具数量。完整 React 平台是按需打开的数据与审批面板，iframe 通过专属 MessagePort 转发 API、附件及 SSE；普通浏览器保留同源代理。

Host 注册五条认证精确 POST 路由处理 RPC，与已有共享网关共存。Cookie/CSRF 只保存在 Host 内存，模型和 iframe 不接收凭据。面板桥接不能访问认证写入、租约或原生调用管理接口。

## 生命周期

harness_connections 按 (user_id, instance_id) 保存连接与租约。activate 建立租约，heartbeat 仅续期有效连接，deactivate 撤销连接并停止关联普通 Run 和原生调用。停用后的迟到心跳不会重新启用。

Host 停用撤销工具并中断请求，后端取消在途任务。90 秒租约与 5 秒扫描处理异常退出。已下发命令由控制后台继续追踪；不删除知识、记忆与历史，不停止其他实例任务。

## 交付

根目录 plugin:build/test/pack 构建 Host 与 Client bundle，声明目标 Host peer 版本，React 由 Desktop 共享模块提供。安装前需更新后端与迁移；可选面板需更新前端桥接代码。包不自动安装或启动业务服务。
