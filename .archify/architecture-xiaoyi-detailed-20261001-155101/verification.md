# 详细架构图验收记录

- 图类型：architecture
- 源码提交：ea1f5757f9813476279faa51f58ac21ca9dc42a3
- 内容：27 个组件、32 条关系、5 个重点视图
- 可编辑源文件：candidate.json
- 交付文件：xiaoyi-detailed.html
- 交付绑定收据：xiaoyi-detailed.delivery.json
- 最终验收收据：review-4/xiaoyi-detailed.finalize.json
- 验收摘要：review-4/xiaoyi-detailed.finalize-summary.json
- 浏览器证据：review-4/xiaoyi-detailed.browser-check.json
- 视觉检查：review-4/visual-check/xiaoyi-detailed.visual-check.json
- 源文件 SHA-256：09584607f94f08773fe19ddf91b2eae2c9a39ab444290d094bcae207ba67804f
- HTML SHA-256：65e16da09379df91c383c0989b6e2a0dc9ac3631c6161be7d2be7c71cf18c67f
- Showcase 验证：9/9，0 错误、0 警告
- 自动验收：validate、deliver、strict check、browser-check 全部通过；visual-check 的 containment、readability、viewerChrome、themeStates、captures 全部通过
- 视觉复核：已查看亮色与暗色 1440x900、2048x1320 截图，未见文字重叠或主题渲染异常；完整长图保留在 `review-4/visual-check/`。
- 路线交叉：自动几何检查通过，仍报告 5 处线路交叉和若干长路线建议；这些线路在截图中保持可追踪，未继续扩大画布进行布局重排。

保留最终验收记录；旧版架构图、布局备份、重复验收收据和预览截图已清理。一次因桌面宽度限制失败的布局尝试未纳入交付，最终结果以 `review-4/` 为准。收据中的绝对路径反映生成时的本地环境，内容校验值绑定交付文件。
