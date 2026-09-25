# ESP32 致命错误、重启原因与 Backtrace 诊断

来源：Espressif ESP-IDF Fatal Errors、Core Dump 和系统 API 官方文档。
适用范围：ESP32、ESP-IDF 5.x/6.x。

## 必须采集的信息

设备启动后记录 esp_reset_reason、固件版本、构建标识、启动时间和最小空闲堆。发生 Panic 时保存 Guru Meditation 错误名称、Core 编号、寄存器、EXCCAUSE、EXCVADDR、完整 Backtrace，以及重启前最后一段业务日志。地址只有和产生该固件的 ELF 文件匹配时才能正确解析。

## 重启原因分类

POWERON 表示上电；SW 表示软件主动重启；PANIC 表示异常或断言触发；INT_WDT 与 TASK_WDT 分别指向中断长期阻塞或任务长期不让出 CPU；BROWNOUT 表示电压跌落；DEEPSLEEP 表示从深睡眠唤醒。若 uptime 周期性归零，应先用 reset reason 分类，再判断网络或应用故障。

LoadProhibited 或 StoreProhibited 常见于空指针、悬空指针或非法地址访问，EXCVADDR 可辅助判断。IllegalInstruction 可能由损坏的函数指针、任务函数错误返回或代码内存异常引起。Stack overflow、stack smashing 和 corrupt heap 说明内存边界或生命周期存在问题。Brownout 常与供电能力不足、启动或无线发射电流峰值、线缆压降有关。

## 确认步骤

第一步确认日志与 ELF 构建版本一致。第二步使用 IDF Monitor、addr2line 或 coredump-info 解码首个异常栈帧；Backtrace 顶部通常最接近触发点。第三步结合 reset reason 判断这是首次异常还是 Panic 后再次被看门狗复位。第四步检查异常前的 heap、任务栈高水位、供电和关键状态转换。第五步在同一固件和相同输入下复现，并保留首次故障现场。

## Core Dump

Core Dump 可以保存崩溃任务寄存器、调用栈和其他任务快照，适合重启后的事后分析。启用后应同时保存固件 ELF、分区信息和构建标识。coredump-info 用于生成摘要，coredump-debug 可进入调试会话。若采集 DRAM，文件会更大，但可以获得更多全局数据和堆信息。

## 处理建议

指针异常应回溯对象生命周期和边界检查；Watchdog 应定位长临界区、禁中断代码、死循环或没有阻塞点的高优先级任务；Brownout 应测量电源轨最低电压并检查电源余量；栈溢出应先测量高水位，再调整任务栈或减少大局部变量。不要只通过自动重启隐藏故障，否则会丢失最有价值的现场证据。
