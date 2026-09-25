# ESP32 内存泄漏、碎片与低内存诊断

来源：Espressif ESP-IDF Heap Memory Debugging 与 RAM Usage 官方文档。
适用范围：ESP32、内部 RAM 与 PSRAM、ESP-IDF 5.x/6.x。

## 典型症状

日志可能包含 heap low、out of memory、malloc failed、CORRUPT HEAP、Bad head、Bad tail、assertion failed，或者设备运行数小时后网络连接逐渐不稳定并最终重启。总空闲堆看似充足但大块分配失败时，通常需要检查最大连续空闲块和碎片，而不是只看 free heap。

## 关键观测值

周期记录 heap_caps_get_free_size、heap_caps_get_minimum_free_size 和 heap_caps_get_largest_free_block，并按内部 RAM、DMA、可执行内存和 PSRAM 能力分类。同步记录任务栈高水位、连接数量、消息队列长度、当前业务阶段和 uptime。若 free heap 单调下降且长期不恢复，应怀疑泄漏；若总量稳定但 largest free block 持续下降，应怀疑碎片。

## 诊断步骤

第一步画出 free heap、minimum free heap 和 largest block 随 uptime 的变化。第二步缩小到触发下降的功能区间，例如 MQTT 重连、HTTP 请求、传感器采样或配置刷新。第三步启用独立 heap tracing，在可控时间窗内记录分配与释放；泄漏模式用于寻找未释放对象，全部分配模式可辅助定位堆损坏附近的分配者。第四步启用 heap poisoning 或完整性检查，将发现损坏的位置提前到更接近真正写越界的位置。第五步检查任务退出、错误分支和重连路径是否遗漏释放。

## 常见根因

重复创建 MQTT、HTTP 或定时器对象但未销毁；失败重试路径遗漏 free；队列消费速度低于生产速度；可变长度消息造成频繁分配；大块缓冲区在内部 RAM 与 PSRAM 间分配策略不正确；数组越界破坏堆元数据；任务局部变量过大造成栈溢出并表现为随机堆异常。

## 处理建议

对长期对象采用明确所有权，保证成功和失败路径都释放资源。高频路径优先复用固定缓冲区或对象池。对队列和缓存设置容量上限。只有在确认调用需要的内存能力后才选择 PSRAM。调整任务栈前先测量高水位，避免盲目扩大。修复后进行长时间循环测试，要求 free heap 不再单调下降、largest block 保持稳定，并验证 MQTT 和传感器任务持续运行。

## 容易误判

heap trace 时间窗结束后才释放的正常对象可能看起来像泄漏。仅增加堆大小可能延迟复现而不会解决根因。网络超时和 MQTT 心跳失败可能是低内存或任务阻塞的次生表现，诊断时应关联同一时间窗口内的内存指标。
