Source: https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32/api-reference/storage/nvs_flash.html

API 参考

存储 API

非易失性存储库

在 GitHub 上编辑

非易失性存储库

[English]

简介

非易失性存储 (NVS) 库主要用于在 flash 中存储键值格式的数据。本文档将详细介绍 NVS 常用的一些概念。

初始化

NVS 使用分区表中类型为 data 、子类型为 nvs 的分区。该库可以通过以下方式初始化：

nvs_flash_init() 初始化标签为 nvs 的默认 NVS 分区。

nvs_flash_init_partition() 通过其标签初始化特定的 NVS 分区。

nvs_flash_init_partition_ptr() 从 esp_partition_t 指针初始化 NVS 分区。

初始化完成后，应用程序使用 nvs_open() （用于默认分区）或 nvs_open_from_partition() （用于按标签指定的特定分区）访问 NVS 命名空间。

备注

启用 CONFIG_NVS_BDL_STACK 后，NVS 也可以通过块设备层 (BDL) 运行，从而支持标准 flash 分区以外的其他存储后端。在 BDL 模式下， nvs_flash_init_partition_ptr() 不可用，但 nvs_flash_init_partition_bdl() 可用于自定义块设备初始化。详情见 内部实现 > 底层存储 。

备注

如果 NVS 分区被截断（例如，当分区表布局发生更改时），应擦除其内容。ESP-IDF 构建系统提供了 idf.py erase-flash 目标，用于擦除 flash 芯片的所有内容。

键值对

NVS 的操作对象为键值对，其中键是 ASCII 字符串，当前支持的最大键长为 15 个字符。值可以为以下几种类型：

整数类型： uint8_t 、 int8_t 、 uint16_t 、 int16_t 、 uint32_t 、 int32_t 、 uint64_t 、 int64_t

浮点数类型： float 和 double

以零终止的类 C 字符串

长度可变的二进制数据 (BLOB)

备注

NVS 最适合存储数量适中、相对稳定的小型数据，例如设备配置、校准数据或状态标志，而不是少量的大型 string 或 blob 数据。这里所说的“小型数据”并不意味着 NVS 适合存储持续增长或频繁重写的数据集，例如事件日志或周期性采集的测量数据。随着这类数据不断累积，分区很容易被填满并产生碎片，导致空间回收更加频繁，同时加速 flash 磨损。如果需要存储大型 blob 或字符串数据，或需要持续追加数据，建议改用 ESP-IDF 提供的文件系统。

备注

无论特定 SoC 是否配备 FPU，均支持浮点类型 float 和 double 。

键在其命名空间内必须唯一。向现有键写入新值会替换之前的键值对。实际数据类型由最近一次写入操作决定。

在读取值时，会进行数据类型检查。如果读取操作期望的数据类型与该键对应条目的数据类型不匹配，则返回错误 ESP_ERR_NVS_TYPE_MISMATCH 。

记录大小限制

单个存储值的最大大小取决于其数据类型：

数据类型

值的最大大小

整数和浮点数

大小由类型决定（1 到 8 字节）；始终存储在单个条目中。

字符串

4000 字节，包括空字符终止符。

二进制大对象

508,000 字节，或者分区大小的 97.6% 减去 4000 字节，以较小者为准。

备注

上文提到的字符串和 blob 大小限制是数据分区为空（无碎片）的情况下能达到的理论上限。实际运行时可存储的最大数据大小通常会更小，具体取决于分区的碎片程度。参见 空间占用 ，了解 NVS 如何分配条目以及碎片为何会影响可用存储空间。

命名空间

为减少不同组件之间键名的潜在冲突，NVS 将每个键值对分配到一个命名空间。命名空间的命名规则遵循键名的命名规则，例如，最多可占 15 个字符。此外，单个 NVS 分区最多只能容纳 254 个不同的命名空间。命名空间的名称在调用 nvs_open() 或 nvs_open_from_partition 中指定。调用后将返回一个不透明句柄，用于后续调用 nvs_get_* 、 nvs_set_* 和 nvs_commit() 函数。这样，句柄就与命名空间和分区关联，键名不会与其他命名空间中的同名键发生冲突。

open_mode 参数控制访问级别和安全行为：

NVS_READONLY ：只读访问权限。所有写操作将被拒绝。

NVS_READWRITE ：标准读写访问权限。被擦除的数据会被标记为已删除，但仍保留在 flash 中。

NVS_READWRITE_PURGE ：安全的读写访问权限。已擦除的数据将从 flash 中物理移除。

备注

在不同的 NVS 分区中，同名的命名空间被视为相互独立的命名空间。

C++ API

除上文所述的 C API 外，NVS 还在 nvs_flash/include/nvs_handle.hpp 中提供了 C++ 类接口（命名空间 nvs ）。

使用 nvs::open_nvs_handle() 或 nvs::open_nvs_handle_from_partition() 打开命名空间。这些函数返回 std::unique_ptr<nvs::NVSHandle> 。当该 std::unique_ptr 被销毁时，句柄会自动关闭（RAII），因此无需另行调用关闭函数。

nvs::NVSHandle 提供与 C API 对应的方法，包括：

set_item / get_item — 面向整型、浮点型和枚举类型的类型化读写

set_string / get_string — 字符串值

set_blob / get_blob — 二进制 blob 值

commit 、 erase_item 、 erase_all 、 purge_all 、 find_key 及相关辅助方法

open_mode 的取值（ NVS_READONLY 、 NVS_READWRITE 、 NVS_READWRITE_PURGE ）以及键名和命名空间约束与 C API 相同。完整的类与函数说明见下文 API 参考 ，完整示例见 storage/nvs/nvs_rw_value_cxx 。

NVS 迭代器

迭代器允许根据指定的分区名称、命名空间和数据类型轮询 NVS 中存储的键值对。

使用以下函数，可执行相关操作：

nvs_entry_find ：创建一个不透明句柄，用于后续调用 nvs_entry_next 和 nvs_entry_info 函数；

nvs_entry_next ：让迭代器指向下一个键值对；

nvs_entry_info ：返回每个键值对的信息。

总的来说，所有通过 nvs_entry_find() 获得的迭代器（包括 NULL 迭代器）都必须使用 nvs_release_iterator() 释放。

nvs_entry_find() 和 nvs_entry_next() 在除发生参数错误之外的所有情况下，都会将给定的迭代器设为 NULL 或有效的迭代器（即返回 ESP_ERR_NVS_NOT_FOUND 时除外）。发生参数错误时，给定的迭代器不会被修改。因此，最佳实践是在调用 nvs_entry_find() 之前先将迭代器初始化为 NULL ，以避免在释放迭代器之前进行繁琐的错误检查。

安全性、篡改性及鲁棒性

NVS 与 ESP32 flash 加密系统不直接兼容。然而，如果 NVS 加密与 ESP32 flash 加密一起使用，数据仍可以加密形式存储。详情请参考 NVS 加密 。

如果未启用 NVS 加密，任何对 flash 芯片有物理访问权限的用户都可以读取、修改、擦除或添加键值对。启用 NVS 加密后，在不知道相应的 NVS 加密密钥的情况下，无法读取、修改或添加键值对并将其识别为有效键值对。但是，针对擦除操作没有相应的防篡改功能。

当 flash 处于不一致状态时，NVS 库会尝试恢复。在任何时间点关闭设备电源，然后重新打开电源，不会导致数据丢失；但如果关闭设备电源时正在写入新的键值对，这一键值对可能会丢失。该库还应该能够在 flash 中存在任何随机数据的情况下正常初始化。

数据清除与安全

默认情况下，当 NVS 更新或擦除键值对时，flash 中的数据仅在元数据部分被标记为已擦除。这些值实际仍存在于 flash 中。这种做法可以提升写入性能。

对于需要更高安全性、必须将敏感数据从 flash 中物理删除的应用（即通过将所有位清零），NVS 提供了两种机制：

一次性清除

nvs_purge_all() 函数会清除命名空间内所有标记为已擦除的条目。该功能适用于尚未使用连续清除模式，且应用需要清理现有已擦除 flash 内容的场景。此函数可与以 NVS_READWRITE 或 NVS_READWRITE_PURGE 模式打开的句柄配合使用。

连续清除模式

以 NVS_READWRITE_PURGE 模式打开的命名空间句柄，除了将已擦除或覆盖的值标记为已擦除外，还会自动清除这些值所占用的 flash 空间。

备注

以 NVS_READWRITE_PURGE 模式打开 NVS 命名空间时，不会清理 flash 中被标记为已擦除的数据。若命名空间中存在已更新或已擦除的数据，在使用连续清除模式前，请先执行一次性清除。

备注

相较于标准的标记为已擦除模式，清除操作会增加额外的 flash 写入次数。在决定是否使用数据清除功能时，应用程序需要在安全需求和 flash 写入性能之间进行权衡。

特殊使用场景

NVS 中的大量数据

虽然不推荐这样做，但 NVS 可以存储数以万计的键，且 NVS 分区的大小可达数兆字节级别。

备注

NVS 组件会在堆上占用 RAM。占用量取决于 flash 上的 NVS 分区大小以及正在使用的键数量。为估算 RAM 用量，请参考以下近似数值：每 1 MB NVS flash 分区消耗 22 KB RAM；每 1000 个键消耗 5.5 KB RAM。

备注

使用 nvs_flash_init() 进行 NVS 初始化所需的时间与现有键的数量成正比。初始化 NVS 时，通常每 1000 个键需要 0.5 秒。

备注

NVS 初始化耗时会随着分区内数据量的增加以及值更新次数的增多而逐渐增长。为避免应用程序在客户实际使用过程中因初始化过程意外触发看门狗超时，请提前在包含所有键（包括预期更新历史）的 NVS 分区上测试初始化过程。

默认情况下，内部 NVS 会在内部 RAM 中分配堆内存。对于较大的 NVS 分区或大量键，应用程序可能仅因 NVS 的开销就耗尽内部 RAM 的堆内存。

如果应用程序所使用的模组配备了通过 SPI 连接的 PSRAM，则可通过启用 Kconfig 选项 CONFIG_NVS_ALLOCATE_CACHE_IN_SPIRAM 来克服这一限制。该选项会将 RAM 分配重定向到通过 SPI 连接的 PSRAM。

当启用 SPIRAM 且 CONFIG_SPIRAM_USE 设为 CONFIG_SPIRAM_USE_CAPS_ALLOC 时，此选项可在 menuconfig 菜单的 nvs_flash 组件中使用。

备注

使用 SPI 接口的 PSRAM 后，NVS 整数操作的 API 耗时约为原来的 2.5 倍。

电源不稳定状态

当 NVS 用于弱电源或不稳定电源系统（如太阳能或电池供电系统）时，flash 擦除操作可能偶尔无法彻底完成，而应用程序无法检测到这一问题。这会导致实际 flash 内容与预留页面的预期布局不一致。在极少数情况下（特别是在意外断电时），可能造成可用 NVS 页面耗尽，导致分区初始化失败并返回 ESP_ERR_NVS_NO_FREE_PAGES 错误。

为解决此问题，可通过 Kconfig 选项 CONFIG_NVS_FLASH_VERIFY_ERASE 启用 flash 擦除操作的验证机制，通过回读受影响页面进行检测。若在 flash_erase 操作后页面未完全擦除为 0xFF ，系统将重试擦除操作直至页面被正确清空。包括首次尝试在内的擦除尝试总次数可通过 Kconfig 选项 CONFIG_NVS_FLASH_ERASE_ATTEMPTS 进行配置。

备注

在可写分区上初始化 NVS 时，如果发现分区处于不一致的状态，NVS 库会尝试执行恢复操作。该操作可能涉及擦除和重写部分页面，而在电源持续不稳定的环境下，进而可能导致出厂默认数据意外丢失。因此，建议将关键的出厂默认数据保存在单独的只读分区中，这样就不会对其执行恢复操作。

在引导加载程序代码中使用 NVS

本指南所述的标准 NVS API 可供正在运行的应用程序使用。此外，还可以在自定义引导加载程序代码中从 NVS 读取数据。更多信息见 在引导程序中使用 NVS 指南。

NVS 加密

详情请参考 NVS 加密 。

NVS 分区生成程序

NVS 分区生成程序帮助生成 NVS 分区二进制文件，可使用烧录程序将二进制文件单独烧录至特定分区。烧录至分区上的键值对由 CSV 文件提供，详情请参考 NVS 分区生成程序 。

可以直接使用函数 nvs_create_partition_image 通过 CMake 创建分区二进制文件，无需手动调用 nvs_partition_gen.py 工具:

nvs_create_partition_image(<partition><csv>[FLASH_IN_PROJECT][DEPENDSdepdepdep...])

位置参数 :

参数

描述

partition

NVS 分区名

csv

解析的 CSV 文件路径

可选参数 :

参数

描述

FLASH_IN_PROJECT

将生成的镜像与工程一并烧录

DEPENDS

指定命令依赖的文件

在没有指定 FLASH_IN_PROJECT 的情况下，也支持生成分区镜像，不过此时需要使用 idf.py <partition>-flash 手动进行烧录。举个例子，如果分区名为 nvs ，则需使用的命令为 idf.py nvs-flash 。

目前，仅支持从组件中的 CMakeLists.txt 文件调用 nvs_create_partition_image ，且此选项仅适用于非加密分区。

应用示例

ESP-IDF storage/nvs 目录下提供了数个代码示例：

storage/nvs/nvs_rw_value

演示如何读取及写入 NVS 单个整数值。

此示例中的值表示 ESP32 模组重启次数。NVS 中数据不会因为模组重启而丢失，因此只有将这一值存储于 NVS 中，才能起到重启次数计数器的作用。

该示例也演示了如何检测读取/写入操作是否成功，以及某个特定值是否在 NVS 中尚未初始化。诊断程序以纯文本形式提供，有助于追踪程序流程，及时发现问题。

storage/nvs/nvs_rw_blob

演示如何读取及写入 NVS 单个整数值和 BLOB（二进制大对象），并在 NVS 中存储这一数值，即便 ESP32 模组重启也不会消失。

value - 记录 ESP32 模组软重启次数和硬重启次数。

blob - 内含记录模组运行次数的表格。此表格将被从 NVS 读取至动态分配的 RAM 上。每次手动软重启后，表格内运行次数即增加一次，新加的运行次数被写入 NVS。下拉 GPIO0 即可手动软重启。

该示例也演示了如何执行诊断程序以检测读取/写入操作是否成功。

storage/nvs/nvs_rw_value_cxx

这个例子与 storage/nvs/nvs_rw_value 完全一样，只是使用了 C++ 的 NVS 句柄类（通过 nvs::open_nvs_handle() 获取 nvs::NVSHandle ）。

storage/nvs/nvs_statistics

该示例演示了如何获取并解读 NVS 使用情况统计信息：包括指定 NVS 分区中的空闲、已用、可用、总条目数、以及命名空间数量。

默认的 NVS 分区会在运行本示例前被擦除，以确保干净的运行环境。随后，会写入模拟的字符串类型数据。

在写入数据前后分别获取使用情况统计信息，并将两者的差异与新占用条目的预期值进行比较。

本示例的第二部分展示了 NVS 分区碎片化对 blob 存储开销的影响。

storage/nvs/nvs_iteration

该示例演示了如何遍历特定（或任意）NVS 数据类型的条目，以及如何获取这些条目的相关信息。

默认的 NVS 分区会在运行本示例前被擦除，以确保干净的运行环境。随后，会写入包含不同 NVS 整型数据类型的模拟数据。

之后，本示例会遍历各个数据类型以及通用的 NVS_TYPE_ANY 类型，并记录在每次遍历过程中获取到的信息。

内部实现

键值对日志

NVS 按顺序存储键值对，新的键值对添加在最后。因此，如需更新某一键值对，实际是在日志最后增加一对新的键值对，同时将旧的键值对标记为已擦除。

备注

NVS 组件在设计上包含 flash 磨损均衡。执行写入操作时，新数据会追加写入现有条目之后的空闲空间，而旧数据失效后不会立即触发 flash 擦除操作。NVS 将存储空间组织为页和条目，从而降低了 flash 擦除操作的频率。对于可存储在单个条目中的数据类型，在理想情况下（每次擦除对应一整页均为单条目写入），flash 擦除与写入操作的频率比可以有效降低为原来的 1/126。实际情况下，这一比例通常会更低，且主要取决于分区的使用率：随着有效数据增长，NVS 会更频繁地执行空间回收，从而导致擦除与写入次数之比增大。此外，对于较大且从未被覆盖的数据块，它们可能会长期占用同一个 NVS 页。由于空间回收仅会选择包含已擦除条目的页，这类页面不会参与擦除循环，因此会减少参与磨损均衡的 flash 空间比例。

页面和条目

NVS 库在其操作中主要使用两个实体：页面和条目。页面是一个逻辑结构，用于存储部分的整体日志。逻辑页面对应 flash 的一个物理扇区，正在使用中的页面具有与之相关联的 序列号 。序列号赋予了页面顺序，较高的序列号对应较晚创建的页面。页面有以下几种状态：

空或未初始化

页面对应的 flash 扇区为空白状态（所有字节均为 0xff ）。此时，页面未存储任何数据且没有关联的序列号。

活跃状态

此时 flash 已完成初始化，页头部写入 flash，页面已具备有效序列号。页面中存在一些空条目，可写入数据。任意时刻，至多有一个页面处于活跃状态。

写满状态

flash 已写满键值对，状态不再改变。
用户无法向写满状态下的页面写入新键值对，但仍可将一些键值对标记为已擦除。

擦除状态

未擦除的键值对将移至其他页面，以便擦除当前页面。这一状态仅为暂时性状态，即 API 调用返回时，页面应脱离这一状态。如果设备突然断电，下次开机时，设备将继续把未擦除的键值对移至其他页面，并继续擦除当前页面。

损坏状态

页头部包含无效数据，无法进一步解析该页面中的数据，因此之前写入该页面的所有条目均无法访问。相应的 flash 扇区并不会被立即擦除，而是与其他处于未初始化状态的扇区一起等待后续使用。这一状态可能对调试有用。

flash 扇区映射至逻辑页面并没有特定的顺序，NVS 库会检查存储在 flash 扇区的页面序列号，并根据序列号组织页面。

+--------++--------++--------++--------+|Page1||Page2||Page3||Page4||Full+--->|Full+--->|Active||Empty|<-状态|#11 | | #12 | | #14 | | | <- 序列号+---+----++----+---++----+---++---+----+||||||||||||+---v------++-----v----++------v---++------v---+|Sector3||Sector0||Sector2||Sector1|<-物理扇区+----------++----------++----------++----------+

页面结构

当前，我们假设 flash 扇区大小为 4096 字节，并且 ESP32 flash 加密硬件在 32 字节块上运行。未来有可能引入一些编译时可配置项（可通过 menuconfig 进行配置），以适配具有不同扇区大小的 flash 芯片。但目前尚不清楚 SPI flash 驱动和 SPI flash cache 之类的系统组件是否支持其他扇区大小。

页面由头部、条目状态位图和条目三部分组成。为了实现与 ESP32 flash 加密功能兼容，条目大小设置为 32 字节。如果键值为整数型，条目则保存一个键值对；如果键值为字符串或 BLOB 类型，则条目仅保存一个键值对的部分内容（更多信息详见条目结构描述）。

页面结构如下图所示，括号内数字表示该部分的大小（以字节为单位）。

+-----------+--------------+-------------+-------------------------+|State(4)|Seq.no.(4)|version(1)|Unused(19)|CRC32(4)|页头部(32)+-----------+--------------+-------------+-------------------------+|Entrystatebitmap(32)|+------------------------------------------------------------------+|Entry0(32)|+------------------------------------------------------------------+|Entry1(32)|+------------------------------------------------------------------+////+------------------------------------------------------------------+|Entry125(32)|+------------------------------------------------------------------+

头部和条目状态位图写入 flash 时不加密。如果启用了 ESP32 flash 加密功能，则条目写入 flash 时将会加密。

通过将 0 写入某些位可以定义页面状态值，表示状态改变。因此，如果需要变更页面状态，并不一定要擦除页面，除非要将其变更为 擦除 状态。

头部中的 version 字段反映了所用的 NVS 格式版本。为实现向后兼容，版本升级从 0xff 开始依次递减（例如，version-1 为 0xff，version-2 为 0xfe，以此类推）。

头部中 CRC32 值是由不包含状态值的条目计算所得（4 到 28 字节）。当前未使用的条目用 0xff 字节填充。

条目结构和条目状态位图的详细信息见下文描述。

条目和条目状态位图

每个条目可处于以下三种状态之一，每个状态在条目状态位图中用两位表示。位图中的最后四位 (256 - 2 * 126) 未使用。

空 (2'b11)

条目还未写入任何内容，处于未初始化状态（全部字节为 0xff ）。

写入（2'b10）

一个键值对（或跨多个条目的键值对的部分内容）已写入条目中。

擦除（2'b00）

条目中的键值对已丢弃，条目内容不再解析。

条目结构

如果键值类型为基础类型，即 1 - 8 个字节长度的整数型，条目将保存一个键值对；如果键值类型为字符串或 BLOB 类型，条目将保存整个键值对的部分内容。另外，如果键值为字符串类型且跨多个条目，则键值所跨的所有条目均保存在同一页面。BLOB 则可以切分为多个块，实现跨多个页面。BLOB 索引是一个附加的固定长度元数据条目，用于追踪 BLOB 块。目前条目仍支持早期 BLOB 格式（可读取可修改），但这些 BLOB 一经修改，即以新格式储存至条目。

+--------+----------+----------+----------------+-----------+---------------+----------+|NS(1)|Type(1)|Span(1)|ChunkIndex(1)|CRC32(4)|Key(16)|Data(8)|+--------+----------+----------+----------------+-----------+---------------+----------+Primitive+--------------------------------++-------->|Data(8)||Types+--------------------------------++->Fixedlength--||+---------+--------------+---------------+-------+|+-------->|Size(4)|ChunkCount(1)|ChunkStart(1)|Rsv(2)|Dataformat---+BLOBIndex+---------+--------------+---------------+-------+||+----------+---------+-----------++->Variablelength-->|Size(2)|Rsv(2)|CRC32(4)|(Strings,BLOBData)+----------+---------+-----------+

条目结构中各个字段含义如下：

命名空间 (NS, NameSpace)

该条目的命名空间索引，详细信息参见命名空间实现章节。

类型 (Type)

一个字节表示的值的数据类型， nvs_flash/include/nvs_handle.hpp 下的 ItemType 枚举了可能的类型。

跨度 (Span)

该键值对所用的条目数量。如果键值为整数型，条目数量即为 1。如果键值为字符串或 BLOB，则条目数量取决于值的长度。

块索引 (ChunkIndex)

用于存储 BLOB 类型数据块的索引。如果键值为其他数据类型，则此处索引应写入 0xff 。

CRC32

对条目下所有字节进行校验后，所得的校验和（CRC32 字段不计算在内）。

键 (Key)

即以零结尾的 ASCII 字符串，字符串最长为 15 字节，不包含最后一个字节的零终止符。

数据 (Data)

如果键值类型为整数型，则数据字段仅包含键值。如果键值小于八个字节，使用 0xff 填充未使用的部分（右侧）。

如果键值类型为 BLOB 索引条目，则该字段的八个字节将保存以下数据块信息：

块大小

整个 BLOB 数据的大小（以字节为单位）。该字段仅用于 BLOB 索引类型条目。

ChunkCount

存储过程中 BLOB 分成的数据块总量。该字段仅用于 BLOB 索引类型条目。

ChunkStart

BLOB 第一个数据块的块索引，后续数据块索引依次递增，步长为 1。该字段仅用于 BLOB 索引类型条目。

如果键值类型为字符串或 BLOB 数据块，数据字段的这八个字节将保存该键值的一些附加信息，如下所示：

数据大小

实际数据的大小（以字节为单位）。如果键值类型为字符串，此字段也应将零终止符包含在内。此字段仅用于字符串和 BLOB 类型条目。

CRC32

数据所有字节的校验和，该字段仅用于字符串和 BLOB 类型条目。

可变长度值（字符串和 BLOB）写入后续条目，每个条目 32 字节。第一个条目的 Span 字段将指明使用了多少条目。

空间占用

NVS 将每条记录存储为一个或多个 32 字节的条目，这些条目位于 4096 字节的数据页中。每个数据页包含 126 个可用条目。一个值需要占用多少个条目，以及存储该值所需的空闲条目数，取决于其数据类型：

整数和浮点数只占用一个独立条目；只要任意位置存在一个空闲条目即可存储。

字符串占用一个元数据条目，随后占用 ceil(payload_size / entry_size) 个数据条目（有效载荷包含字符串结尾的空字符）。这些条目必须在同一个数据页内连续分配。

blob 类型占用一个 BLOB_INDEX 元数据条目以及一个或多个数据块。每个数据块由一个元数据条目和若干数据条目组成，并存储在不同的数据页中。因此，存储一个 blob 共需要 1 + k + ceil(blob_size / entry_size) 个条目，其中 k 表示数据被拆分后的页数。

在写入新的键值对或更新现有键值对之前，NVS 会查找一个具有足够空闲条目（或可通过空间回收获得足够可用条目）的数据页。空间回收算法为应对突然断电而设计，每次调用仅对一个候选页进行空间整理。因此，可连续分配的最大条目数始终是在单个数据页内决定的。这会带来两个影响：

字符串的实际最大长度受限于单个数据页中空闲条目与已删除条目数量之和的最大值。

blob 会根据空间回收后各数据页中可用条目的数量拆分为多个数据块，并持续拆分直至整个值存储完成。这使得 NVS 即使在某个数据页仅剩 2 个空闲条目时也能继续利用该页进行存储，但每个数据块都需要额外占用一个元数据条目。在极端情况下，元数据的开销甚至可能超过有效负载大小的 100%。

由于上述按页分配的特性，实际可存储的数据大小通常低于 记录大小限制 中给出的理论最大值，并且随着分区逐渐填满和碎片不断增加，可存储的数据大小会进一步减小。碎片对 flash 寿命的影响请参阅 键值对日志 中关于磨损均衡的说明。

备注

由于在现场已部署的设备上调整 NVS 分区大小较为困难，应将其初始大小设得足够大，以容纳当前需求以及键或其数据的潜在增长。还建议运行足够数量的测试，以真实反映写入和更新 NVS 键的频率。在测试软件更新之前（例如，通过 OTA），先在已被上一版本软件碎片化的数据分区上运行这些测试。

命名空间

如上所述，每个键值对属于一个命名空间。命名空间标识符（字符串）也作为键值对的键，存储在索引为 0 的命名空间中。与这些键对应的值就是这些命名空间的索引。

+-------------------------------------------+|NS=0Type=uint8_tKey="wifi"Value=1|Entrydescribingnamespace"wifi"+-------------------------------------------+|NS=1Type=uint32_tKey="channel"Value=6|Key"channel"innamespace"wifi"+-------------------------------------------+|NS=0Type=uint8_tKey="pwm"Value=2|Entrydescribingnamespace"pwm"+-------------------------------------------+|NS=2Type=uint16_tKey="channel"Value=20|Key"channel"innamespace"pwm"+-------------------------------------------+

条目哈希列表

为了减少对 flash 执行的读操作次数，Page 类对象均设有一个列表，包含一对数据：条目索引和条目哈希值。该列表可大大提高检索速度，而无需迭代所有条目并逐个从 flash 中读取。 Page::findItem 首先从哈希列表中检索条目哈希值，如果条目存在，则在页面内给出条目索引。由于哈希冲突，在哈希列表中检索条目哈希值可能会得到不同的条目，对 flash 中条目再次迭代可解决这一冲突。

哈希列表中每个节点均包含一个 24 位哈希值和 8 位条目索引。哈希值根据条目命名空间、键名和块索引由 CRC32 计算所得，计算结果保留 24 位。为减少将 32 位条目存储在链表中的开销，链表采用了数组的双向链表。每个数组占用 128 个字节，包含 29 个条目、两个链表指针和一个 32 位计数字段。因此，每页额外需要的 RAM 最少为 128 字节，最多为 640 字节。

只读 NVS

NVS 支持两种级别的只读模式：

在分区表层面，可在分区表 CSV 文件中将分区标记为 readonly 。

在应用层面，可通过 nvs_open_from_partition() 函数并传入 NVS_READONLY 标志，以只读模式打开 NVS 分区。

NVS 正常运行所需的默认最小空间为 12 KiB ( 0x3000 )，即至少需要 3 页，且其中至少有一页处于空状态。但如果 NVS 分区在分区表 CSV 文件中被标记为 readonly ，并以只读模式打开，那么分区大小可以只有 4 KiB（ 0x1000 ）。

备注

目前，如果 NVS 使用块设备层作为存储后端时，则不会反映只读标志。

底层存储

在构建时，可以配置 NVS 访问其底层存储的模式。menuconfig 选项 CONFIG_NVS_BDL_STACK 提供了两种模式。

ESP 分区 API（默认） ：NVS 使用 esp_partition 访问存储。这是默认运行模式，其中 NVS 使用由分区表定义的 SPI flash 分区。在此模式下：

初始化函数 ( nvs_flash_init() , nvs_flash_init_partition() ) 会查找该分区，并使用 esp_partition API 访问它。

应用程序可以提供自定义的 esp_partition_t 指针并调用 nvs_flash_init_partition_ptr() 。这使应用程序能够克服基于分区表的分区所带来的限制，例如使用分区表中未定义的分区。

该模式提供最佳性能，因为 NVS 与底层存储之间没有额外的抽象层。

块设备层 (BDL) ：NVS 通过 esp_blockdev 访问存储。此选项使 NVS 能在实现 esp_blockdev 接口的块设备上运行。在此模式下：

初始化函数（ nvs_flash_init() ， nvs_flash_init_partition() ）会通过 esp_partition 透明地创建块设备，管理其生命周期，并在内部使用 esp_blockdev。对于应用而言，此模式与默认的运行模式类似。

应用程序可以提供自定义块设备句柄，并调用 nvs_flash_init_partition_bdl() 将其注册到 NVS。应用程序负责管理该块设备句柄的生命周期。

由于 BDL 抽象了底层存储，与直接使用 esp_partition API 相比，会有额外开销。仅当基于 esp_partition 的存储无法满足应用需求时，才选择此模式。

备注

如果在 NVS 中使用自定义块设备，则必须满足以下要求：

read_size 和 write_size 必须为 1 字节（NVS 要求按字节粒度进行访问）。

erase_size 必须是 4096 的约数（NVS 页大小固定为 4096 字节）。

disk_size 必须是 4096 字节的整数倍。

必须将 default_val_after_erase 标志位设为 1（即擦除后的存储器读出的值为 0xFF ）。

操作（ read 、 write 、 erase ）必须实现。

API 参考

Header File

components/nvs_flash/include/nvs_flash.h

This header file can be included with:

#include"nvs_flash.h"

This header file is a part of the API provided by the nvs_flash component. To declare that your component depends on nvs_flash , add the following to your CMakeLists.txt:

REQUIRES nvs_flash

or

PRIV_REQUIRES nvs_flash

Functions

esp_err_t nvs_flash_init ( void )

Initialize the default NVS partition.

This API initialises the default NVS partition. The default NVS partition is the one that is labeled "nvs" in the partition table.

When "NVS_ENCRYPTION" is enabled in the menuconfig, this API enables the NVS encryption for the default NVS partition as follows

Read security configurations from the first NVS key partition listed in the partition table. (NVS key partition is any "data" type partition which has the subtype value set to "nvs_keys")

If the NVS key partition obtained in the previous step is empty, generate and store new keys in that NVS key partition.

Internally call "nvs_flash_secure_init()" with the security configurations obtained/generated in the previous steps.

Post initialization NVS read/write APIs remain the same irrespective of NVS encryption.

返回 :

ESP_OK if storage was successfully initialized.

ESP_ERR_NVS_NO_FREE_PAGES if the NVS storage contains no empty pages (which may happen if NVS partition was truncated)

ESP_ERR_NOT_FOUND if no partition with label "nvs" is found in the partition table

ESP_ERR_NO_MEM in case memory could not be allocated for the internal structures

one of the error codes from the underlying flash storage driver

error codes from nvs_flash_read_security_cfg API (when "NVS_ENCRYPTION" is enabled).

error codes from nvs_flash_generate_keys API (when "NVS_ENCRYPTION" is enabled).

error codes from nvs_flash_secure_init_partition API (when "NVS_ENCRYPTION" is enabled) .

esp_err_t nvs_flash_init_partition ( const char * partition_label )

Initialize NVS flash storage for the specified partition.

参数 :

partition_label -- [in] Label of the partition. Must be no longer than 16 characters.

返回 :

ESP_OK if storage was successfully initialized.

ESP_ERR_NVS_NO_FREE_PAGES if the NVS storage contains no empty pages (which may happen if NVS partition was truncated)

ESP_ERR_NOT_FOUND if specified partition is not found in the partition table

ESP_ERR_NO_MEM in case memory could not be allocated for the internal structures

one of the error codes from the underlying flash storage driver

esp_err_t nvs_flash_init_partition_ptr ( const esp_partition_t * partition )

Initialize NVS flash storage on the partition specified by esp_partition pointer.

This API initialises the NVS storage on an esp_partition. The storage is identified by the label of the respective partition. Note: this API is only available when the block device support is disabled in the menuconfig.

参数 :

partition -- [in] pointer to a partition obtained by the ESP partition API.

返回 :

ESP_OK if storage was successfully initialized

ESP_ERR_NVS_NO_FREE_PAGES if the NVS storage contains no empty pages (which may happen if NVS partition was truncated)

ESP_ERR_INVALID_ARG in case partition is NULL

ESP_ERR_NO_MEM in case memory could not be allocated for the internal structures

one of the error codes from the underlying flash storage driver

esp_err_t nvs_flash_init_partition_bdl ( const char * partition_label , esp_blockdev_handle_t bdl )

Initialize NVS flash storage on the specified block device handle.

This API initialises the NVS storage on a bdl device and identifies it with the given label. Caller of this API is responsible for creating and managing the lifetime of the block device handle. NVS component will stop using the handle when nvs_flash_deinit_partition() is called for the last partition label using this block device handle.

Note: to use this API, the block device support must be enabled in the menuconfig option NVS_BDL_STACK

参数 :

partition_label -- [in] label of the partition to initialize

bdl -- [in] block device handle for the partition

返回 :

ESP_OK if storage was successfully initialized

ESP_ERR_NVS_NO_FREE_PAGES if the NVS storage contains no empty pages (which may happen if NVS partition was truncated)

ESP_ERR_INVALID_ARG in case partition_label or bdl is NULL

ESP_ERR_NO_MEM in case memory could not be allocated for the internal structures

ESP_ERR_NOT_SUPPORTED if the bdl handle does not fulfill the NVS compliance requirements

one of the error codes from the underlying flash storage driver

esp_err_t nvs_flash_deinit ( void )

Deinitialize NVS storage for the default NVS partition.

Default NVS partition is the partition with "nvs" label in the partition table.

备注

Prefer closing all open handles with nvs_close() before deinitializing. Any handles still open for this partition are closed and freed here; using them afterwards is invalid (nvs_close() on such a handle is a no-op).

返回 :

ESP_OK on success (storage was deinitialized)

ESP_ERR_NVS_NOT_INITIALIZED if the storage was not initialized prior to this call

esp_err_t nvs_flash_deinit_partition ( const char * partition_label )

Deinitialize NVS storage for the given NVS partition.

备注

Prefer closing all open handles with nvs_close() before deinitializing. Any handles still open for this partition are closed and freed here; using them afterwards is invalid (nvs_close() on such a handle is a no-op).

参数 :

partition_label -- [in] Label of the partition

返回 :

ESP_OK on success

ESP_ERR_NVS_NOT_INITIALIZED if the storage for given partition was not initialized prior to this call

esp_err_t nvs_flash_erase ( void )

Erase the default NVS partition.

Erases all contents of the default NVS partition (one with label "nvs").

备注

If the partition is initialized, this function first de-initializes it. Afterwards, the partition has to be initialized again to be used.

返回 :

ESP_OK on success

ESP_ERR_NOT_FOUND if there is no NVS partition labeled "nvs" in the partition table

different error in case de-initialization fails (shouldn't happen)

esp_err_t nvs_flash_erase_partition ( const char * part_name )

Erase specified NVS partition.

Erase all content of a specified NVS partition

备注

If the partition is initialized, this function first de-initializes it. Afterwards, the partition has to be initialized again to be used.

参数 :

part_name -- [in] Name (label) of the partition which should be erased

返回 :

ESP_OK on success

ESP_ERR_NOT_FOUND if there is no NVS partition with the specified name in the partition table

different error in case de-initialization fails (shouldn't happen)

esp_err_t nvs_flash_erase_partition_ptr ( const esp_partition_t * partition )

Erase custom partition.

Erase all content of specified custom partition.

备注

If the partition is initialized, this function first de-initializes it. Afterwards, the partition has to be initialized again to be used.

参数 :

partition -- [in] pointer to a partition obtained by the ESP partition API.

返回 :

ESP_OK on success

ESP_ERR_NOT_FOUND if there is no partition with the specified parameters in the partition table

ESP_ERR_INVALID_ARG in case partition is NULL

one of the error codes from the underlying flash storage driver

esp_err_t nvs_flash_secure_init ( nvs_sec_cfg_t * cfg )

Initialize the default NVS partition.

This API initialises the default NVS partition. The default NVS partition is the one that is labeled "nvs" in the partition table.

参数 :

cfg -- [in] Security configuration (keys) to be used for NVS encryption/decryption. If cfg is NULL, no encryption is used.

返回 :

ESP_OK if storage has been initialized successfully.

ESP_ERR_NVS_NO_FREE_PAGES if the NVS storage contains no empty pages (which may happen if NVS partition was truncated)

ESP_ERR_NOT_FOUND if no partition with label "nvs" is found in the partition table

ESP_ERR_NO_MEM in case memory could not be allocated for the internal structures

one of the error codes from the underlying flash storage driver

esp_err_t nvs_flash_secure_init_partition ( const char * partition_label , nvs_sec_cfg_t * cfg )

Initialize NVS flash storage for the specified partition.

参数 :

partition_label -- [in] Label of the partition. Note that internally, a reference to passed value is kept and it should be accessible for future operations

cfg -- [in] Security configuration (keys) to be used for NVS encryption/decryption. If cfg is null, no encryption/decryption is used.

返回 :

ESP_OK if storage has been initialized successfully.

ESP_ERR_NVS_NO_FREE_PAGES if the NVS storage contains no empty pages (which may happen if NVS partition was truncated)

ESP_ERR_NOT_FOUND if specified partition is not found in the partition table

ESP_ERR_NO_MEM in case memory could not be allocated for the internal structures

one of the error codes from the underlying flash storage driver

esp_err_t nvs_flash_generate_keys ( const esp_partition_t * partition , nvs_sec_cfg_t * cfg )

Generate and store NVS keys in the provided esp partition.

参数 :

partition -- [in] Pointer to partition structure obtained using esp_partition_find_first or esp_partition_get. Must be non-NULL.

cfg -- [out] Pointer to nvs security configuration structure. Pointer must be non-NULL. Generated keys will be populated in this structure.

返回 :

ESP_OK, if cfg was read successfully;

ESP_ERR_INVALID_ARG, if partition or cfg is NULL;

or error codes from esp_partition_write/erase APIs.

esp_err_t nvs_flash_read_security_cfg ( const esp_partition_t * partition , nvs_sec_cfg_t * cfg )

Read NVS security configuration from a partition.

备注

Provided partition is assumed to be marked 'encrypted'.

参数 :

partition -- [in] Pointer to partition structure obtained using esp_partition_find_first or esp_partition_get. Must be non-NULL.

cfg -- [out] Pointer to nvs security configuration structure. Pointer must be non-NULL.

返回 :

ESP_OK, if cfg was read successfully;

ESP_ERR_INVALID_ARG, if partition or cfg is NULL

ESP_ERR_NVS_KEYS_NOT_INITIALIZED, if the partition is not yet written with keys.

ESP_ERR_NVS_CORRUPT_KEY_PART, if the partition containing keys is found to be corrupt

or error codes from esp_partition_read API.

esp_err_t nvs_flash_register_security_scheme ( nvs_sec_scheme_t * scheme_cfg )

Registers the given security scheme for NVS encryption The scheme registered with sec_scheme_id by this API be used as the default security scheme for the "nvs" partition. Users will have to call this API explicitly in their application.

参数 :

scheme_cfg -- [in] Pointer to the security scheme configuration structure that the user (or the nvs_key_provider) wants to register.

返回 :

ESP_OK, if security scheme registration succeeds;

ESP_ERR_INVALID_ARG, if scheme_cfg is NULL;

ESP_FAIL, if security scheme registration fails

void nvs_flash_deregister_security_scheme ( void )

Deregister the security scheme previously registered using nvs_flash_register_security_scheme.

nvs_sec_scheme_t * nvs_flash_get_default_security_scheme ( void )

Fetch the configuration structure for the default active security scheme for NVS encryption.

返回 :

Pointer to the default active security scheme configuration (NULL if no scheme is registered yet i.e. active)

esp_err_t nvs_flash_generate_keys_v2 ( nvs_sec_scheme_t * scheme_cfg , nvs_sec_cfg_t * cfg )

Generate (and store) the NVS keys using the specified key-protection scheme.

参数 :

scheme_cfg -- [in] Security scheme specific configuration

cfg -- [out] Security configuration (encryption keys)

返回 :

ESP_OK, if cfg was populated successfully with generated encryption keys;

ESP_ERR_INVALID_ARG, if scheme_cfg or cfg is NULL;

ESP_FAIL, if the key generation process fails

esp_err_t nvs_flash_read_security_cfg_v2 ( nvs_sec_scheme_t * scheme_cfg , nvs_sec_cfg_t * cfg )

Read NVS security configuration set by the specified security scheme.

参数 :

scheme_cfg -- [in] Security scheme specific configuration

cfg -- [out] Security configuration (encryption keys)

返回 :

ESP_OK, if cfg was read successfully;

ESP_ERR_INVALID_ARG, if scheme_cfg or cfg is NULL;

ESP_FAIL, if the key reading process fails

Structures

struct nvs_sec_cfg_t

Key for encryption and decryption.

Public Members

uint8_t eky [ NVS_KEY_SIZE ]

XTS encryption and decryption key

uint8_t tky [ NVS_KEY_SIZE ]

XTS tweak key

struct nvs_sec_scheme_t

NVS encryption: Security scheme configuration structure.

Public Members

int scheme_id

Security Scheme ID (E.g. HMAC)

void * scheme_data

Scheme-specific data (E.g. eFuse block for HMAC-based key generation)

nvs_flash_generate_keys_t nvs_flash_key_gen

Callback for the nvs_flash_key_gen implementation

nvs_flash_read_cfg_t nvs_flash_read_cfg

Callback for the nvs_flash_read_keys implementation

Macros

NVS_KEY_SIZE

Type Definitions

typedef esp_err_t ( * nvs_flash_generate_keys_t ) ( const void * scheme_data , nvs_sec_cfg_t * cfg )

Callback function prototype for generating the NVS encryption keys.

typedef esp_err_t ( * nvs_flash_read_cfg_t ) ( const void * scheme_data , nvs_sec_cfg_t * cfg )

Callback function prototype for reading the NVS encryption keys.

Header File

components/nvs_flash/include/nvs.h

This header file can be included with:

#include"nvs.h"

This header file is a part of the API provided by the nvs_flash component. To declare that your component depends on nvs_flash , add the following to your CMakeLists.txt:

REQUIRES nvs_flash

or

PRIV_REQUIRES nvs_flash

Functions

esp_err_t nvs_set_i8 ( nvs_handle_t handle , const char * key , int8_t value )

set int8_t value for given key

Set value for the key, given its name. Note that the actual storage will not be updated until nvs_commit is called. Regardless whether key-value pair is created or updated, function always requires at least one nvs available entry. See nvs_get_stats . After create type of operation, the number of available entries is decreased by one. After update type of operation, the number of available entries remains the same.

参数 :

handle -- [in] Handle obtained from nvs_open function. Handles that were opened read only cannot be used.

key -- [in] Key name. Maximum length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

value -- [in] The value to set.

返回 :

ESP_OK if value was set successfully

ESP_FAIL if there is an internal error; most likely due to corrupted NVS partition (only if NVS assertion checks are disabled)

ESP_ERR_NVS_INVALID_HANDLE if handle has been closed or is NULL

ESP_ERR_NVS_READ_ONLY if storage handle was opened as read only

ESP_ERR_NVS_KEY_TOO_LONG if the key name is longer than (NVS_KEY_NAME_MAX_SIZE-1) characters

ESP_ERR_NVS_NOT_ENOUGH_SPACE if there is not enough space in the underlying storage to save the value

ESP_ERR_NVS_REMOVE_FAILED if the value wasn't updated because flash write operation has failed. The value was written however, and update will be finished after re-initialization of nvs, provided that flash operation doesn't fail again.

esp_err_t nvs_set_u8 ( nvs_handle_t handle , const char * key , uint8_t value )

set uint8_t value for given key

This function is the same as nvs_set_i8 except for the data type.

esp_err_t nvs_set_i16 ( nvs_handle_t handle , const char * key , int16_t value )

set int16_t value for given key

This function is the same as nvs_set_i8 except for the data type.

esp_err_t nvs_set_u16 ( nvs_handle_t handle , const char * key , uint16_t value )

set uint16_t value for given key

This function is the same as nvs_set_i8 except for the data type.

esp_err_t nvs_set_i32 ( nvs_handle_t handle , const char * key , int32_t value )

set int32_t value for given key

This function is the same as nvs_set_i8 except for the data type.

esp_err_t nvs_set_u32 ( nvs_handle_t handle , const char * key , uint32_t value )

set uint32_t value for given key

This function is the same as nvs_set_i8 except for the data type.

esp_err_t nvs_set_i64 ( nvs_handle_t handle , const char * key , int64_t value )

set int64_t value for given key

This function is the same as nvs_set_i8 except for the data type.

esp_err_t nvs_set_u64 ( nvs_handle_t handle , const char * key , uint64_t value )

set uint64_t value for given key

This function is the same as nvs_set_i8 except for the data type.

esp_err_t nvs_set_float ( nvs_handle_t handle , const char * key , float value )

set float value for given key

This function is the same as nvs_set_i8 except for the data type. The value must be a valid IEEE 754 float (NaN is rejected).

返回 :

ESP_ERR_INVALID_ARG if value is NaN

For other return values, see nvs_set_i8

esp_err_t nvs_set_double ( nvs_handle_t handle , const char * key , double value )

set double value for given key

This function is the same as nvs_set_i8 except for the data type. The value must be a valid IEEE 754 double (NaN is rejected).

返回 :

ESP_ERR_INVALID_ARG if value is NaN

For other return values, see nvs_set_i8

esp_err_t nvs_set_str ( nvs_handle_t handle , const char * key , const char * value )

set string for given key

Sets string value for the key. The whole string (including the null terminator) must fit as a contiguous run of entries on a single NVS page. The operation consumes 1 overhead (metadata) entry plus ceil ((strlen(value) + 1) / 32) data entries.

On update, the new value is written first and the previous value is erased afterwards, so free space for the new value is required regardless of the size of the old one. Entries occupied by the previous value become available only for subsequent operations (and only after page reclaim).

Note that storage of long string values can fail due to fragmentation of nvs pages even if available_entries returned by nvs_get_stats suggests enough overall space available. See the NVS documentation section "Space Consumption" for details. Note that the underlying storage will not be updated until nvs_commit is called.

参数 :

handle -- [in] Handle obtained from nvs_open function. Handles that were opened read only cannot be used.

key -- [in] Key name. Maximum length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

value -- [in] The value to set. For strings, the maximum length (including null character) is 4000 bytes, if there is one complete page free for writing. This decreases, however, if the free space is fragmented.

返回 :

ESP_OK if value was set successfully

ESP_FAIL if there is an internal error; most likely due to corrupted NVS partition (only if NVS assertion checks are disabled)

ESP_ERR_NVS_INVALID_HANDLE if handle has been closed or is NULL

ESP_ERR_NVS_READ_ONLY if storage handle was opened as read only

ESP_ERR_NVS_KEY_TOO_LONG if the key name is longer than (NVS_KEY_NAME_MAX_SIZE-1) characters

ESP_ERR_NVS_NOT_ENOUGH_SPACE if there is not enough space in the underlying storage to save the value

ESP_ERR_NVS_REMOVE_FAILED if the value wasn't updated because flash write operation has failed. The value was written however, and update will be finished after re-initialization of nvs, provided that flash operation doesn't fail again.

ESP_ERR_NVS_VALUE_TOO_LONG if the string value is too long

esp_err_t nvs_get_i8 ( nvs_handle_t handle , const char * key , int8_t * out_value )

get int8_t value for given key

These functions retrieve value for the key, given its name. If key does not exist, or the requested variable type doesn't match the type which was used when setting a value, an error is returned.

In case of any error, out_value is not modified.

out_value has to be a pointer to an already allocated variable of the given type.

// Example of using nvs_get_i32:int32_tmax_buffer_size=4096;// default valueesp_err_terr=nvs_get_i32(my_handle,"max_buffer_size",&max_buffer_size);assert(err==ESP_OK||err==ESP_ERR_NVS_NOT_FOUND);// if ESP_ERR_NVS_NOT_FOUND was returned, max_buffer_size will still// have its default value.

参数 :

handle -- [in] Handle obtained from nvs_open function.

key -- [in] Key name. Maximum length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

out_value -- Pointer to the output value. May be NULL for nvs_get_str and nvs_get_blob, in this case required length will be returned in length argument.

返回 :

ESP_OK if the value was retrieved successfully

ESP_FAIL if there is an internal error; most likely due to corrupted NVS partition (only if NVS assertion checks are disabled)

ESP_ERR_NVS_NOT_FOUND if the requested key doesn't exist

ESP_ERR_NVS_INVALID_HANDLE if handle has been closed or is NULL

ESP_ERR_NVS_TYPE_MISMATCH if the type of the stored value doesn't match the requested type

esp_err_t nvs_get_u8 ( nvs_handle_t handle , const char * key , uint8_t * out_value )

get uint8_t value for given key

This function is the same as nvs_get_i8 except for the data type.

esp_err_t nvs_get_i16 ( nvs_handle_t handle , const char * key , int16_t * out_value )

get int16_t value for given key

This function is the same as nvs_get_i8 except for the data type.

esp_err_t nvs_get_u16 ( nvs_handle_t handle , const char * key , uint16_t * out_value )

get uint16_t value for given key

This function is the same as nvs_get_i8 except for the data type.

esp_err_t nvs_get_i32 ( nvs_handle_t handle , const char * key , int32_t * out_value )

get int32_t value for given key

This function is the same as nvs_get_i8 except for the data type.

esp_err_t nvs_get_u32 ( nvs_handle_t handle , const char * key , uint32_t * out_value )

get uint32_t value for given key

This function is the same as nvs_get_i8 except for the data type.

esp_err_t nvs_get_i64 ( nvs_handle_t handle , const char * key , int64_t * out_value )

get int64_t value for given key

This function is the same as nvs_get_i8 except for the data type.

esp_err_t nvs_get_u64 ( nvs_handle_t handle , const char * key , uint64_t * out_value )

get uint64_t value for given key

This function is the same as nvs_get_i8 except for the data type.

esp_err_t nvs_get_float ( nvs_handle_t handle , const char * key , float * out_value )

get float value for given key

This function is the same as nvs_get_i8 except for the data type.

esp_err_t nvs_get_double ( nvs_handle_t handle , const char * key , double * out_value )

get double value for given key

This function is the same as nvs_get_i8 except for the data type.

esp_err_t nvs_get_str ( nvs_handle_t handle , const char * key , char * out_value , size_t * length )

get string value for given key

These functions retrieve the data of an entry, given its key. If key does not exist, or the requested variable type doesn't match the type which was used when setting a value, an error is returned.

In case of any error, out_value is not modified.

All functions expect out_value to be a pointer to an already allocated variable of the given type.

nvs_get_str and nvs_get_blob functions support WinAPI-style length queries. To get the size necessary to store the value, call nvs_get_str or nvs_get_blob with zero out_value and non-zero pointer to length. Variable pointed to by length argument will be set to the required length. For nvs_get_str, this length includes the zero terminator. When calling nvs_get_str and nvs_get_blob with non-zero out_value, length has to be non-zero and has to point to the length available in out_value. It is suggested that nvs_get/set_str is used for zero-terminated C strings, and nvs_get/set_blob used for arbitrary data structures.

// Example (without error checking) of using nvs_get_str to get a string into dynamic array:size_trequired_size;nvs_get_str(my_handle,"server_name",NULL,&required_size);char*server_name=malloc(required_size);nvs_get_str(my_handle,"server_name",server_name,&required_size);// Example (without error checking) of using nvs_get_blob to get a binary dataintoastaticarray:uint8_tmac_addr[6];size_tsize=sizeof(mac_addr);nvs_get_blob(my_handle,"dst_mac_addr",mac_addr,&size);

参数 :

handle -- [in] Handle obtained from nvs_open function.

key -- [in] Key name. Maximum length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

out_value -- [out] Pointer to the output value. May be NULL for nvs_get_str and nvs_get_blob, in this case required length will be returned in length argument.

length -- [inout] A non-zero pointer to the variable holding the length of out_value. In case out_value a zero, will be set to the length required to hold the value. In case out_value is not zero, will be set to the actual length of the value written. For nvs_get_str this includes zero terminator.

返回 :

ESP_OK if the value was retrieved successfully

ESP_FAIL if there is an internal error; most likely due to corrupted NVS partition (only if NVS assertion checks are disabled)

ESP_ERR_NVS_NOT_FOUND if the requested key doesn't exist

ESP_ERR_NVS_INVALID_HANDLE if handle has been closed or is NULL

ESP_ERR_NVS_TYPE_MISMATCH if the type of the stored value doesn't match the requested type

ESP_ERR_NVS_INVALID_LENGTH if length is not sufficient to store data

esp_err_t nvs_get_blob ( nvs_handle_t handle , const char * key , void * out_value , size_t * length )

get blob value for given key

This function behaves the same as nvs_get_str , except for the data type.

esp_err_t nvs_open ( const char * namespace_name , nvs_open_mode_t open_mode , nvs_handle_t * out_handle )

Open non-volatile storage with a given namespace from the default NVS partition.

Multiple internal ESP-IDF and third party application modules can store their key-value pairs in the NVS module. In order to reduce possible conflicts on key names, each module can use its own namespace. The default NVS partition is the one that is labelled "nvs" in the partition table.

参数 :

namespace_name -- [in] Namespace name. Maximum length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

open_mode -- [in] NVS_READONLY opens a read only handle NVS_READWRITE opens a read/write handle. erase and set operations are allowed. previous data is marked as deleted only and new data is written to a new location. NVS_READWRITE_PURGE opens a read/write handle. Update and erase operations are allowed. previous data is purged from flash memory to ensure that it cannot be recovered. New data is written to a new location.

out_handle -- [out] If successful (return code is zero), handle will be returned in this argument.

返回 :

ESP_OK if storage handle was opened successfully

ESP_FAIL if there is an internal error; most likely due to corrupted NVS partition (only if NVS assertion checks are disabled)

ESP_ERR_NVS_NOT_INITIALIZED if the storage driver is not initialized

ESP_ERR_NVS_PART_NOT_FOUND if the partition with label "nvs" is not found

ESP_ERR_NVS_NOT_FOUND if namespace doesn't exist yet and mode is NVS_READONLY

ESP_ERR_NVS_KEY_TOO_LONG if the namespace name is longer than (NVS_KEY_NAME_MAX_SIZE-1) characters

ESP_ERR_NO_MEM in case memory could not be allocated for the internal structures

ESP_ERR_NVS_NOT_ENOUGH_SPACE if there is no space for a new entry or there are too many different namespaces (maximum allowed different namespaces: 254)

ESP_ERR_NOT_ALLOWED if the NVS partition is read-only and mode is NVS_READWRITE

ESP_ERR_INVALID_ARG if out_handle is equal to NULL

other error codes from the underlying storage driver

esp_err_t nvs_open_from_partition ( const char * part_name , const char * namespace_name , nvs_open_mode_t open_mode , nvs_handle_t * out_handle )

Open non-volatile storage with a given namespace from specified partition.

The behaviour is same as nvs_open() API. However this API can operate on a specified NVS partition instead of default NVS partition. Note that the specified partition must be registered with NVS using nvs_flash_init_partition() API.

参数 :

part_name -- [in] Label (name) of the partition of interest for object read/write/erase

namespace_name -- [in] Namespace name. Maximum length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

open_mode -- [in] NVS_READONLY opens a read only handle NVS_READWRITE opens a read/write handle. erase and set operations are allowed. previous data is marked as deleted only and new data is written to a new location. NVS_READWRITE_PURGE opens a read/write handle. Update and erase operations are allowed. previous data is purged from flash memory to ensure that it cannot be recovered. New data is written to a new location.

out_handle -- [out] If successful (return code is zero), handle will be returned in this argument.

返回 :

ESP_OK if storage handle was opened successfully

ESP_FAIL if there is an internal error; most likely due to corrupted NVS partition (only if NVS assertion checks are disabled)

ESP_ERR_NVS_NOT_INITIALIZED if the storage driver is not initialized

ESP_ERR_NVS_PART_NOT_FOUND if the partition with specified name is not found

ESP_ERR_NVS_NOT_FOUND if namespace doesn't exist yet and mode is NVS_READONLY

ESP_ERR_NVS_KEY_TOO_LONG if the namespace name is longer than (NVS_KEY_NAME_MAX_SIZE-1) characters

ESP_ERR_NO_MEM in case memory could not be allocated for the internal structures

ESP_ERR_NVS_NOT_ENOUGH_SPACE if there is no space for a new entry or there are too many different namespaces (maximum allowed different namespaces: 254)

ESP_ERR_NOT_ALLOWED if the NVS partition is read-only and mode is NVS_READWRITE

ESP_ERR_INVALID_ARG if out_handle is equal to NULL

other error codes from the underlying storage driver

esp_err_t nvs_set_blob ( nvs_handle_t handle , const char * key , const void * value , size_t length )

set variable length binary value for given key

Sets variable length binary value for the key. A blob is stored as one BLOB_INDEX entry plus one or more data chunks (each chunk is a BLOB_DATA header entry followed by its payload entries, on a separate page). Storing a blob therefore needs 1 + k + ceil(length / 32) entries, where k is the number of chunks/pages used. The overhead is exactly 2 entries only when the blob fits in a single chunk; fragmentation increases k . See nvs_get_stats and the NVS documentation section "Space Consumption".

On update, the new value is written first and the previous value is erased afterwards, so free space for the new value is required regardless of the size of the old one. Entries occupied by the previous value become available only for subsequent operations (and only after page reclaim).

Note that storage of large blobs can fail due to fragmentation of nvs pages even if available_entries returned by nvs_get_stats suggests enough overall space available. Note that the underlying storage will not be updated until nvs_commit is called.

参数 :

handle -- [in] Handle obtained from nvs_open function. Handles that were opened read only cannot be used.

key -- [in] Key name. Maximum length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

value -- [in] The value to set.

length -- [in] length of binary value to set, in bytes; Maximum length is 508000 bytes or (97.6% of the partition size - 4000) bytes whichever is lower.

返回 :

ESP_OK if value was set successfully

ESP_FAIL if there is an internal error; most likely due to corrupted NVS partition (only if NVS assertion checks are disabled)

ESP_ERR_NVS_INVALID_HANDLE if handle has been closed or is NULL

ESP_ERR_NVS_READ_ONLY if storage handle was opened as read only

ESP_ERR_NVS_KEY_TOO_LONG if the key name is longer than (NVS_KEY_NAME_MAX_SIZE-1) characters

ESP_ERR_NVS_NOT_ENOUGH_SPACE if there is not enough space in the underlying storage to save the value

ESP_ERR_NVS_REMOVE_FAILED if the value wasn't updated because flash write operation has failed. The value was written however, and update will be finished after re-initialization of nvs, provided that flash operation doesn't fail again.

ESP_ERR_NVS_VALUE_TOO_LONG if the value is too long

esp_err_t nvs_find_key ( nvs_handle_t handle , const char * key , nvs_type_t * out_type )

Lookup key-value pair with given key name.

Note that function may indicate both existence of the key as well as the data type of NVS entry if it is found.

参数 :

handle -- [in] Storage handle obtained with nvs_open.

key -- [in] Key name. Maximum length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

out_type -- [out] Pointer to the output variable populated with data type of NVS entry in case key was found. May be NULL, respective data type is then not provided.

返回 :

ESP_OK if NVS entry for key provided was found

ESP_ERR_NVS_NOT_FOUND if the requested key doesn't exist

ESP_ERR_NVS_INVALID_HANDLE if handle has been closed or is NULL

ESP_FAIL if there is an internal error; most likely due to corrupted NVS partition (only if NVS assertion checks are disabled)

other error codes from the underlying storage driver

esp_err_t nvs_erase_key ( nvs_handle_t handle , const char * key )

Erase key-value pair with given key name.

Note that actual storage may not be updated until nvs_commit function is called.

参数 :

handle -- [in] Storage handle obtained with nvs_open. Handles that were opened read only cannot be used.

key -- [in] Key name. Maximum length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

返回 :

ESP_OK if erase operation was successful

ESP_FAIL if there is an internal error; most likely due to corrupted NVS partition (only if NVS assertion checks are disabled)

ESP_ERR_NVS_INVALID_HANDLE if handle has been closed or is NULL

ESP_ERR_NVS_READ_ONLY if handle was opened as read only

ESP_ERR_NVS_NOT_FOUND if the requested key doesn't exist

other error codes from the underlying storage driver

esp_err_t nvs_erase_all ( nvs_handle_t handle )

Erase all key-value pairs in a namespace.

Note that actual storage may not be updated until nvs_commit function is called.

参数 :

handle -- [in] Storage handle obtained with nvs_open. Handles that were opened read only cannot be used.

返回 :

ESP_OK if erase operation was successful

ESP_FAIL if there is an internal error; most likely due to corrupted NVS partition (only if NVS assertion checks are disabled)

ESP_ERR_NVS_INVALID_HANDLE if handle has been closed or is NULL

ESP_ERR_NVS_READ_ONLY if handle was opened as read only

other error codes from the underlying storage driver

esp_err_t nvs_purge_all ( nvs_handle_t handle )

Purge data of all erased key-value pairs in a namespace.

Note that actual storage may not be updated until nvs_commit function is called.

参数 :

handle -- [in] Storage handle obtained with nvs_open. Handles that were opened read only cannot be used.

返回 :

ESP_OK if erase operation was successful

ESP_FAIL if there is an internal error; most likely due to corrupted NVS partition (only if NVS assertion checks are disabled)

ESP_ERR_NVS_INVALID_HANDLE if handle has been closed or is NULL

ESP_ERR_NVS_READ_ONLY if handle was opened as read only

other error codes from the underlying storage driver

esp_err_t nvs_commit ( nvs_handle_t handle )

Write any pending changes to non-volatile storage.

After setting any values, nvs_commit() must be called to ensure changes are written to non-volatile storage. Individual implementations may write to storage at other times, but this is not guaranteed.

参数 :

handle -- [in] Storage handle obtained with nvs_open. Handles that were opened read only cannot be used.

返回 :

ESP_OK if the changes have been written successfully

ESP_ERR_NVS_INVALID_HANDLE if handle has been closed or is NULL

other error codes from the underlying storage driver

void nvs_close ( nvs_handle_t handle )

Close the storage handle and free any allocated resources.

This function should be called for each handle opened with nvs_open once the handle is not in use any more. Closing the handle may not automatically write the changes to nonvolatile storage. This has to be done explicitly using nvs_commit function. Once this function is called on a handle, the handle should no longer be used.

参数 :

handle -- [in] Storage handle to close

esp_err_t nvs_get_stats ( const char * part_name , nvs_stats_t * nvs_stats )

Fill structure nvs_stats_t . It provides info about memory used by NVS.

This function calculates the number of used entries, free entries, available entries, total entries and number of namespaces in partition.

// Example of nvs_get_stats() to get overview of actual statistics of data entries :nvs_stats_tnvs_stats;nvs_get_stats(NULL,&nvs_stats);printf("Count: UsedEntries = (%lu), FreeEntries = (%lu), AvailableEntries = (%lu), AllEntries = (%lu)\n",nvs_stats.used_entries,nvs_stats.free_entries,nvs_stats.available_entries,nvs_stats.total_entries);

参数 :

part_name -- [in] Partition name NVS in the partition table. If pass a NULL than will use NVS_DEFAULT_PART_NAME ("nvs").

nvs_stats -- [out] Returns filled structure nvs_states_t. It provides info about used memory the partition.

返回 :

ESP_OK if the changes have been written successfully. Return param nvs_stats will be filled.

ESP_ERR_NVS_NOT_INITIALIZED if the storage driver is not initialized, or if the partition with label part_name is not found / not initialized. Return param nvs_stats will be filled with 0.

ESP_ERR_INVALID_ARG if nvs_stats is equal to NULL.

ESP_ERR_NVS_INVALID_STATE if there is a page with the status of INVALID. Return param nvs_stats will be filled not with correct values because not all pages will be counted. Counting will be interrupted at the first INVALID page.

esp_err_t nvs_get_used_entry_count ( nvs_handle_t handle , size_t * used_entries )

Calculate all entries in a namespace.

An entry represents the smallest storage unit in NVS. Strings and blobs may occupy more than one entry. Note that to find out the total number of entries occupied by the namespace, add one to the returned value used_entries (if err is equal to ESP_OK). Because the name space entry takes one entry.

// Example of nvs_get_used_entry_count() to get amount of all key-value pairs in one namespace:nvs_handle_thandle;nvs_open("namespace1",NVS_READWRITE,&handle);...size_tused_entries;size_ttotal_entries_namespace;if(nvs_get_used_entry_count(handle,&used_entries)==ESP_OK){// the total number of entries occupied by the namespacetotal_entries_namespace=used_entries+1;}

参数 :

handle -- [in] Handle obtained from nvs_open function.

used_entries -- [out] Returns amount of used entries from a namespace.

返回 :

ESP_OK if the changes have been written successfully. Return param used_entries will be filled valid value.

ESP_ERR_NVS_NOT_INITIALIZED if the storage driver is not initialized. Return param used_entries will be filled 0.

ESP_ERR_NVS_INVALID_HANDLE if handle has been closed or is NULL. Return param used_entries will be filled 0.

ESP_ERR_INVALID_ARG if used_entries is equal to NULL.

Other error codes from the underlying storage driver. Return param used_entries will be filled 0.

esp_err_t nvs_entry_find ( const char * part_name , const char * namespace_name , nvs_type_t type , nvs_iterator_t * output_iterator )

Create an iterator to enumerate NVS entries based on one or more parameters.

// Example of listing all the key-value pairs of any type under specified partition and namespacenvs_iterator_tit=NULL;esp_err_tres=nvs_entry_find(<nvs_partition_name>,<namespace>,NVS_TYPE_ANY,&it);while(res==ESP_OK){nvs_entry_info_tinfo;nvs_entry_info(it,&info);// Can omit error check if parameters are guaranteed to be non-NULLprintf("key '%s', type '%d' \n",info.key,info.type);res=nvs_entry_next(&it);}nvs_release_iterator(it);

参数 :

part_name -- [in] Partition name

namespace_name -- [in] Set this value if looking for entries with a specific namespace. Pass NULL otherwise.

type -- [in] One of nvs_type_t values.

output_iterator -- [out] Set to a valid iterator to enumerate all the entries found. Set to NULL if no entry for specified criteria was found. If any other error except ESP_ERR_INVALID_ARG occurs, output_iterator is NULL, too. If ESP_ERR_INVALID_ARG occurs, output_iterator is not changed. If a valid iterator is obtained through this function, it has to be released using nvs_release_iterator when not used any more, unless ESP_ERR_INVALID_ARG is returned.

返回 :

ESP_OK if no internal error or programming error occurred.

ESP_ERR_NVS_NOT_FOUND if no element of specified criteria has been found.

ESP_ERR_NO_MEM if memory has been exhausted during allocation of internal structures.

ESP_ERR_INVALID_ARG if any of the parameters is NULL. Note: don't release output_iterator in case ESP_ERR_INVALID_ARG has been returned

esp_err_t nvs_entry_find_in_handle ( nvs_handle_t handle , nvs_type_t type , nvs_iterator_t * output_iterator )

Create an iterator to enumerate NVS entries based on a handle and type.

// Example of listing all the key-value pairs of any type under specified handle (which defines a partition and namespace)nvs_iterator_tit=NULL;esp_err_tres=nvs_entry_find_in_handle(<nvs_handle>,NVS_TYPE_ANY,&it);while(res==ESP_OK){nvs_entry_info_tinfo;nvs_entry_info(it,&info);// Can omit error check if parameters are guaranteed to be non-NULLprintf("key '%s', type '%d' \n",info.key,info.type);res=nvs_entry_next(&it);}nvs_release_iterator(it);

参数 :

handle -- [in] Handle obtained from nvs_open function.

type -- [in] One of nvs_type_t values.

output_iterator -- [out] Set to a valid iterator to enumerate all the entries found. Set to NULL if no entry for specified criteria was found. If any other error except ESP_ERR_INVALID_ARG occurs, output_iterator is NULL, too. If ESP_ERR_INVALID_ARG occurs, output_iterator is not changed. If a valid iterator is obtained through this function, it has to be released using nvs_release_iterator when not used any more, unless ESP_ERR_INVALID_ARG is returned.

返回 :

ESP_OK if no internal error or programming error occurred.

ESP_ERR_NVS_NOT_FOUND if no element of specified criteria has been found.

ESP_ERR_NO_MEM if memory has been exhausted during allocation of internal structures.

ESP_ERR_NVS_INVALID_HANDLE if unknown handle was specified.

ESP_ERR_INVALID_ARG if output_iterator parameter is NULL. Note: don't release output_iterator in case ESP_ERR_INVALID_ARG has been returned

esp_err_t nvs_entry_next ( nvs_iterator_t * iterator )

Advances the iterator to next item matching the iterator criteria.

Note that any copies of the iterator will be invalid after this call.

参数 :

iterator -- [inout] Iterator obtained from nvs_entry_find or nvs_entry_find_in_handle function. Must be non-NULL. If any error except ESP_ERR_INVALID_ARG occurs, iterator is set to NULL. If ESP_ERR_INVALID_ARG occurs, iterator is not changed.

返回 :

ESP_OK if no internal error or programming error occurred.

ESP_ERR_NVS_NOT_FOUND if no next element matching the iterator criteria.

ESP_ERR_INVALID_ARG if iterator is NULL.

Possibly other errors in the future for internal programming or flash errors.

esp_err_t nvs_entry_info ( const nvs_iterator_t iterator , nvs_entry_info_t * out_info )

Fills nvs_entry_info_t structure with information about entry pointed to by the iterator.

参数 :

iterator -- [in] Iterator obtained from nvs_entry_find or nvs_entry_find_in_handle function. Must be non-NULL.

out_info -- [out] Structure to which entry information is copied.

返回 :

ESP_OK if all parameters are valid; current iterator data has been written to out_info

ESP_ERR_INVALID_ARG if one of the parameters is NULL.

void nvs_release_iterator ( nvs_iterator_t iterator )

Release iterator.

参数 :

iterator -- [in] Release iterator obtained from nvs_entry_find or nvs_entry_find_in_handle or nvs_entry_next function. NULL argument is allowed.

Structures

struct nvs_entry_info_t

information about entry obtained from nvs_entry_info function

Public Members

char namespace_name [ NVS_NS_NAME_MAX_SIZE ]

Namespace to which key-value belong

char key [ NVS_KEY_NAME_MAX_SIZE ]

Key of stored key-value pair

nvs_type_t type

Type of stored key-value pair

struct nvs_stats_t

备注

Info about storage space NVS.

Public Members

size_t used_entries

Number of used entries.

size_t free_entries

Number of free entries. It includes also reserved entries.

size_t available_entries

Number of entries available for data storage.

size_t total_entries

Number of all entries.

size_t namespace_count

Number of namespaces.

Macros

ESP_ERR_NVS_BASE

Starting number of error codes

ESP_ERR_NVS_NOT_INITIALIZED

The storage driver is not initialized

ESP_ERR_NVS_NOT_FOUND

A requested entry couldn't be found or namespace doesn’t exist yet and mode is NVS_READONLY

ESP_ERR_NVS_TYPE_MISMATCH

The type of set or get operation doesn't match the type of value stored in NVS

ESP_ERR_NVS_READ_ONLY

Storage handle was opened as read only

ESP_ERR_NVS_NOT_ENOUGH_SPACE

There is not enough space in the underlying storage to save the value

ESP_ERR_NVS_INVALID_NAME

Namespace name doesn’t satisfy constraints

ESP_ERR_NVS_INVALID_HANDLE

Handle has been closed or is NULL

ESP_ERR_NVS_REMOVE_FAILED

The value wasn’t updated because flash write operation has failed. The value was written however, and update will be finished after re-initialization of nvs, provided that flash operation doesn’t fail again.

ESP_ERR_NVS_KEY_TOO_LONG

Key name is too long

ESP_ERR_NVS_PAGE_FULL

Internal error; never returned by nvs API functions

ESP_ERR_NVS_INVALID_STATE

NVS is in an inconsistent state due to a previous error. Call nvs_flash_init and nvs_open again, then retry.

ESP_ERR_NVS_INVALID_LENGTH

String or blob length is not sufficient to store data

ESP_ERR_NVS_NO_FREE_PAGES

NVS partition doesn't contain any empty pages. This may happen if NVS partition was truncated. Erase the whole partition and call nvs_flash_init again.

ESP_ERR_NVS_VALUE_TOO_LONG

Value doesn't fit into the entry or string or blob length is longer than supported by the implementation

ESP_ERR_NVS_PART_NOT_FOUND

Partition with specified name is not found in the partition table

ESP_ERR_NVS_NEW_VERSION_FOUND

NVS partition contains data in new format and cannot be recognized by this version of code

ESP_ERR_NVS_XTS_ENCR_FAILED

XTS encryption failed while writing NVS entry

ESP_ERR_NVS_XTS_DECR_FAILED

XTS decryption failed while reading NVS entry

ESP_ERR_NVS_XTS_CFG_FAILED

XTS configuration setting failed

ESP_ERR_NVS_XTS_CFG_NOT_FOUND

XTS configuration not found

ESP_ERR_NVS_ENCR_NOT_SUPPORTED

NVS encryption is not supported in this version

ESP_ERR_NVS_KEYS_NOT_INITIALIZED

NVS key partition is uninitialized

ESP_ERR_NVS_CORRUPT_KEY_PART

NVS key partition is corrupt

ESP_ERR_NVS_WRONG_ENCRYPTION

NVS partition is marked as encrypted with generic flash encryption. This is forbidden since the NVS encryption works differently.

ESP_ERR_NVS_CONTENT_DIFFERS

Internal error; never returned by nvs API functions. NVS key is different in comparison

NVS_DEFAULT_PART_NAME

Default partition name of the NVS partition in the partition table

NVS_PART_NAME_MAX_SIZE

maximum length of partition name (excluding null terminator)

NVS_KEY_NAME_MAX_SIZE

Maximum length of NVS key name (including null terminator)

NVS_NS_NAME_MAX_SIZE

Maximum length of NVS namespace name (including null terminator)

NVS_GUARD_SYSVIEW_MACRO_EXPANSION_PUSH ( )

NVS_GUARD_SYSVIEW_MACRO_EXPANSION_POP ( )

Type Definitions

typedef uint32_t nvs_handle_t

Opaque pointer type representing non-volatile storage handle

typedef nvs_handle_t nvs_handle

typedef nvs_open_mode_t nvs_open_mode

typedef struct nvs_opaque_iterator_t * nvs_iterator_t

Opaque pointer type representing iterator to nvs entries

Enumerations

enum nvs_open_mode_t

Mode of opening the non-volatile storage.

Values:

enumerator NVS_READONLY

Read only

enumerator NVS_READWRITE

Read and write

enumerator NVS_READWRITE_PURGE

Read and write

enum nvs_type_t

Types of variables.

Values:

enumerator NVS_TYPE_U8

Type uint8_t

enumerator NVS_TYPE_I8

Type int8_t

enumerator NVS_TYPE_U16

Type uint16_t

enumerator NVS_TYPE_I16

Type int16_t

enumerator NVS_TYPE_U32

Type uint32_t

enumerator NVS_TYPE_I32

Type int32_t

enumerator NVS_TYPE_U64

Type uint64_t

enumerator NVS_TYPE_I64

Type int64_t

enumerator NVS_TYPE_FLOAT

Type float (IEEE 754 single precision)

enumerator NVS_TYPE_DOUBLE

Type double (IEEE 754 double precision)

enumerator NVS_TYPE_STR

Type string

enumerator NVS_TYPE_BLOB

Type blob

enumerator NVS_TYPE_ANY

Must be last

Header File

components/nvs_flash/include/nvs_handle.hpp

This header file can be included with:

#include"nvs_handle.hpp"

This header file is a part of the API provided by the nvs_flash component. To declare that your component depends on nvs_flash , add the following to your CMakeLists.txt:

REQUIRES nvs_flash

or

PRIV_REQUIRES nvs_flash

Classes

class NVSHandle

A handle allowing nvs-entry related operations on the NVS.

备注

The scope of this handle may vary depending on the implementation, but normally would be the namespace of a particular partition. Outside that scope, nvs entries can't be accessed/altered.

Public Functions

template < typename T >

esp_err_t set_item ( const char * key , T value )

set value for given key

Sets value for key. Note that physical storage will not be updated until nvs_commit function is called.

参数 :

key -- [in] Key name. Maximal length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

value -- [in] The value to set. Allowed types are the ones declared in ItemType as well as enums. For strings, the maximum length (including null character) is 4000 bytes, if there is one complete page free for writing. This decreases, however, if the free space is fragmented. Note that enums lose their type information when stored in NVS. Ensure that the correct enum type is used during retrieval with get_item.

返回 :

ESP_OK if value was set successfully

ESP_ERR_NVS_INVALID_HANDLE if the handle has been closed or is NULL

ESP_ERR_NVS_READ_ONLY if storage handle was opened as read only

ESP_ERR_NVS_KEY_TOO_LONG if the key name is longer than (NVS_KEY_NAME_MAX_SIZE-1) characters

ESP_ERR_NVS_NOT_ENOUGH_SPACE if there is not enough space in the underlying storage to save the value

ESP_ERR_NVS_REMOVE_FAILED if the value wasn't updated because flash write operation has failed. The value was written however, and update will be finished after re-initialization of nvs, provided that flash operation doesn't fail again.

ESP_ERR_NVS_VALUE_TOO_LONG if the value is too long

ESP_FAIL if there is an internal error; most likely due to corrupted NVS partition (only if NVS assertion checks are disabled)

other error codes from the underlying storage driver

virtual esp_err_t set_string ( const char * key , const char * value ) = 0

set string for given key

参数 :

key -- [in] Key name. Maximal length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

value -- [in] The string to set. Maximum length (including null character) is 4000 bytes, if there is one complete page free for writing.

返回 :

ESP_OK if value was set successfully

ESP_ERR_NVS_INVALID_HANDLE if handle has been closed or is invalid

ESP_ERR_NVS_READ_ONLY if storage handle was opened as read only

ESP_ERR_NVS_KEY_TOO_LONG if key name exceeds the maximum length

ESP_ERR_NVS_NOT_ENOUGH_SPACE if there is not enough space in the underlying storage to save the value

ESP_ERR_NVS_REMOVE_FAILED if the value wasn't updated because flash write operation has failed

ESP_ERR_NVS_VALUE_TOO_LONG if the string value is too long

other error codes from the underlying storage driver

template < typename T >

esp_err_t get_item ( const char * key , T & value )

get value for given key

These functions retrieve value for the key, given its name. If key does not exist, or the requested variable type doesn't match the type which was used when setting a value, an error is returned.

In case of any error, out_value is not modified.

参数 :

key -- [in] Key name. Maximal length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

value -- The output value. All integral types which are declared in ItemType as well as enums are allowed. Note however that enums lost their type information when stored in NVS. Ensure that the correct enum type is used during retrieval with get_item.

返回 :

ESP_OK if the value was retrieved successfully

ESP_ERR_NVS_INVALID_HANDLE if the handle has been closed or is NULL

ESP_ERR_NVS_NOT_FOUND if the requested key doesn't exist

ESP_ERR_NVS_TYPE_MISMATCH if the type of the stored value doesn't match the requested type

ESP_FAIL if there is an internal error; most likely due to corrupted NVS partition (only if NVS assertion checks are disabled)

other error codes from the underlying storage driver

virtual esp_err_t set_blob ( const char * key , const void * blob , size_t len ) = 0

set variable length binary value for given key

This family of functions set value for the key, given its name. Note that actual storage will not be updated until nvs_commit function is called.

备注

compare to nvs_set_blob() in nvs.h

参数 :

key -- [in] Key name. Maximal length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

blob -- [in] The blob value to set.

len -- [in] length of binary value to set, in bytes; Maximum length is 508000 bytes or (97.6% of the partition size - 4000) bytes whichever is lower.

返回 :

ESP_OK if value was set successfully

ESP_ERR_NVS_INVALID_HANDLE if the handle has been closed or is NULL

ESP_ERR_NVS_READ_ONLY if storage handle was opened as read only

ESP_ERR_NVS_KEY_TOO_LONG if the key name is longer than (NVS_KEY_NAME_MAX_SIZE-1) characters

ESP_ERR_NVS_NOT_ENOUGH_SPACE if there is not enough space in the underlying storage to save the value

ESP_ERR_NVS_REMOVE_FAILED if the value wasn't updated because flash write operation has failed. The value was written however, and update will be finished after re-initialization of nvs, provided that flash operation doesn't fail again.

ESP_ERR_NVS_VALUE_TOO_LONG if the value is too long

ESP_FAIL if there is an internal error; most likely due to corrupted NVS partition (only if NVS assertion checks are disabled)

other error codes from the underlying storage driver

virtual esp_err_t get_string ( const char * key , char * out_str , size_t len ) = 0

get string value for given key

Retrieves the string data of an entry, given its key. If key does not exist, or the requested variable type doesn't match the type which was used when setting a value, an error is returned.

In case of any error, out_str is not modified.

参数 :

key -- [in] Key name. Maximum length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

out_str -- [out] Pointer to the output string buffer.

len -- [in] The length of the output buffer pointed to by out_str. Use get_item_size to query the size of the item beforehand.

返回 :

ESP_OK if the value was retrieved successfully

ESP_ERR_NVS_INVALID_HANDLE if the handle has been closed or is NULL

ESP_ERR_NVS_NOT_FOUND if the requested key doesn't exist

ESP_ERR_NVS_TYPE_MISMATCH if the type of the stored value doesn't match the requested type

ESP_ERR_NVS_INVALID_LENGTH if length is not sufficient to store data

ESP_FAIL if there is an internal error; most likely due to corrupted NVS partition (only if NVS assertion checks are disabled)

other error codes from the underlying storage driver

virtual esp_err_t get_blob ( const char * key , void * out_blob , size_t len ) = 0

get blob value for given key

Retrieves the binary data of an entry, given its key. If key does not exist, or the requested variable type doesn't match the type which was used when setting a value, an error is returned.

In case of any error, out_blob is not modified.

参数 :

key -- [in] Key name. Maximum length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

out_blob -- [out] Pointer to the output blob buffer.

len -- [in] The length of the output buffer pointed to by out_blob. Use get_item_size to query the size of the item beforehand.

返回 :

ESP_OK if the value was retrieved successfully

ESP_ERR_NVS_INVALID_HANDLE if handle has been closed or is invalid

ESP_ERR_NVS_NOT_FOUND if the requested key doesn't exist

ESP_ERR_NVS_TYPE_MISMATCH if the stored value type does not match the requested type

ESP_ERR_NVS_INVALID_LENGTH if length is not sufficient to store data

other error codes from the underlying storage driver

virtual esp_err_t get_item_size ( ItemType datatype , const char * key , size_t & size ) = 0

Look up the size of an entry's data.

参数 :

datatype -- [in] Data type to search for.

key -- [in] Key name. Maximum length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

size -- [out] Size of the item, if it exists. For strings, this size includes the zero terminator.

返回 :

- ESP_OK if the item with specified type and key exists. Its size will be returned via size .

ESP_ERR_NVS_INVALID_HANDLE if the handle has been closed or is NULL

ESP_ERR_NVS_NOT_FOUND if an item with the requested key and type doesn't exist

ESP_ERR_NVS_TYPE_MISMATCH if an item with the requested key exists but has a different type

other error codes from the underlying storage driver

virtual esp_err_t find_key ( const char * key , nvs_type_t & nvstype ) = 0

Checks whether key exists and optionally returns also data type of associated entry.

参数 :

key -- [in] Key name. Maximum length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

nvstype -- [out] Nvs data type of entry, if it exists.

返回 :

ESP_OK if NVS entry for key provided was found. Data type will be returned via nvstype.

ESP_ERR_NVS_INVALID_HANDLE if handle has been closed or is invalid

ESP_ERR_NVS_NOT_FOUND if the requested key doesn't exist

ESP_FAIL if there is an internal error; most likely due to corrupted NVS partition (only if NVS assertion checks are disabled)

other error codes from the underlying storage driver

virtual esp_err_t erase_item ( const char * key ) = 0

Erases an entry.

参数 :

key -- [in] Key name. Maximum length is (NVS_KEY_NAME_MAX_SIZE-1) characters. Shouldn't be empty.

返回 :

ESP_OK if erase operation was successful

ESP_ERR_NVS_INVALID_HANDLE if the handle has been closed or is NULL

ESP_ERR_NVS_READ_ONLY if storage handle was opened as read only

ESP_ERR_NVS_NOT_FOUND if the requested key doesn't exist

ESP_FAIL if there is an internal error; most likely due to corrupted NVS partition (only if NVS assertion checks are disabled)

other error codes from the underlying storage driver

virtual esp_err_t erase_all ( ) = 0

Erases all entries in the scope of this handle.

The scope may vary, depending on the implementation (typically the opened namespace).

备注

If you want to erase the whole NVS flash partition, use nvs_flash_erase() / nvs_flash_erase_partition() instead.

返回 :

ESP_OK if erase operation was successful

ESP_ERR_NVS_INVALID_HANDLE if the handle has been closed or is NULL

ESP_ERR_NVS_READ_ONLY if storage handle was opened as read only

other error codes from the underlying storage driver

virtual esp_err_t purge_all ( ) = 0

Purges all erased entries in the scope of this handle.

The scope may vary, depending on the implementation.

返回 :

ESP_OK if purge operation was successful

ESP_ERR_NVS_INVALID_HANDLE if the handle has been closed or is NULL

ESP_ERR_NVS_READ_ONLY if storage handle was opened as read only

other error codes from the underlying storage driver

virtual esp_err_t commit ( ) = 0

Commits all changes done through this handle so far.

Currently, NVS writes to storage right after the set and get functions, but this is not guaranteed.

返回 :

ESP_OK if commit was successful

ESP_ERR_NVS_INVALID_HANDLE if the handle has been closed or is NULL

virtual esp_err_t get_used_entry_count ( size_t & usedEntries ) = 0

Calculate all entries in the scope of the handle.

参数 :

usedEntries -- [out] Returns amount of used entries from a namespace on success.

返回 :

ESP_OK if the used entry count has been calculated successfully. Return param usedEntries will be filled with a valid value.

ESP_ERR_NVS_INVALID_HANDLE if the handle has been closed or is NULL. Return param usedEntries will be filled with 0.

ESP_ERR_NVS_NOT_INITIALIZED if the storage driver is not initialized. Return param usedEntries will be filled with 0.

Other error codes from the underlying storage driver. Return param usedEntries will be filled with 0.

此文档对您有帮助吗？

反馈已收到，谢谢！

如果您有其他意见，欢迎填写 乐鑫文档反馈表 。

我们重视您的反馈。

您可以填写 乐鑫文档反馈表 告诉我们如何改进该文档。
