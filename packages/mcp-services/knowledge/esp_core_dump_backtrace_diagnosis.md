# ESP32 Core Dump 与 Backtrace 分析

来源：Espressif ESP-IDF Core Dump 与 Fatal Errors 官方文档。
适用范围：ESP32、ESP-IDF 5.x/6.x。

## 采集要求

Core Dump 用于保存崩溃时的寄存器、任务控制块和任务栈。每份转储必须绑定准确的固件版本、构建 ID、ELF 文件、分区表和设备 ID。使用错误版本的 ELF 解码会得到看似合理但实际错误的函数名和行号。

可将转储保存到 Flash 或通过 UART 输出。Flash 方式适合设备自动重启后的现场保留，UART 方式便于实验室调试。若启用 DRAM 捕获，可获得更多全局数据和堆信息，但会增加存储需求。设计分区时需要为最大任务数量和栈快照预留空间，并检查转储校验结果。

## 分析流程

第一步保存未经裁剪的 Panic 日志和 Core Dump。第二步确认 ELF 与设备运行固件完全一致。第三步使用 idf.py coredump-info 生成崩溃任务、寄存器、调用栈和任务列表摘要。第四步先查看 Panic 原因、EXCCAUSE 和 EXCVADDR，再看崩溃任务的最上层有效栈帧。第五步检查其他任务是否持有相关锁、等待队列或占用关键资源。需要交互检查变量和栈内容时再使用 coredump-debug。

## Backtrace 判读

Backtrace 是程序计数器与栈指针组成的调用链。最顶部有效帧通常最接近异常点，但断言、内存损坏和回调间接调用可能让真正根因更早发生。LoadProhibited 或 StoreProhibited 结合 EXCVADDR 可判断是否接近空指针或明显非法地址。栈内容损坏时调用链可能截断或出现无效地址，应同时检查 stack smashing、overflow 和 heap corruption 日志。

## 常见场景

空指针访问需要追踪对象初始化和错误分支。Use-after-free 需要检查异步回调与对象生命周期。栈溢出应结合任务高水位和大局部变量。Heap corruption 的触发位置通常只是检测点，真正越界写可能更早发生，可结合 heap poisoning 与 tracing 缩小范围。Watchdog 转储应检查被阻塞任务以及阻止调度的高优先级任务。

## 归档建议

每个故障案例保存设备 ID、发生时间、固件构建 ID、reset reason、Panic 文本、解码后的首个有效帧、根因提交和修复验证结果。地址和原始二进制转储不适合直接作为语义检索主体，应另外生成结构化中文摘要供 RAG 检索。
