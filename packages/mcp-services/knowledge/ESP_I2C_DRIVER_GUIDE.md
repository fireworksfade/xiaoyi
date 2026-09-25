Source: https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32/api-reference/peripherals/i2c.html

API 参考

外设 API

I2C 接口

在 GitHub 上编辑

I2C 接口

[English]

简介

I2C 是一种串行同步半双工通信协议，总线上可以同时挂载多个主机和从机。I2C 使用两条双向开漏线：串行数据线 (SDA) 和串行时钟线 (SCL)，通过电阻上拉。

ESP32 有 2 个 I2C 控制器（也被称为端口），负责处理 I2C 总线上的通信。

单个 I2C 控制器既可以是主机也可以是从机。

通常，I2C 从机设备具有 7 位地址或 10 位地址。ESP32 支持 I2C 标准模式 (Sm) 和快速模式 (Fm)，可分别达到 100 kHz 和 400 kHz。

警告

主机模式的 SCL 时钟频率不应大于 400 kHz。

备注

SCL 的频率受上拉电阻及导线电容的影响。因此，强烈建议选择适当的上拉电阻，确保频率准确。推荐的上拉电阻值通常在 1 kΩ 到 10 kΩ 之间。

请注意，SCL 的频率越高，上拉电阻应该越小（但不能小于 1 kΩ）。较大的电阻会降低电流，增加时钟切换时间并降低频率。通常推荐 2 kΩ 到 5 kΩ 左右的电阻，也可根据电流需求进行一定调整。

备注

ESP32 的 I2C 控制器作为从机时不支持时钟拉伸（clock stretching）。因此除驱动配置外，应用层还需关注主从设备之间的速度匹配与同步：若主机处理速度过快、从机处理较慢，可能导致通信异常或数据丢失。建议使用应用层数据校验、gpio 信号同步等方式实现主从之间数据同步。使用前请根据使用场景确认 ESP32 的从机模式是否满足您的项目需求。

I2C 时钟配置

i2c_clock_source_t::I2C_CLK_SRC_DEFAULT ：默认的 I2C 时钟源。

i2c_clock_source_t::I2C_CLK_SRC_APB ：以 APB 时钟作为 I2C 时钟源。

功能概述

I2C 驱动程序提供以下服务：

资源分配 - 包括如何使用正确的配置来分配 I2C 总线，以及如何在完成工作后回收资源。

I2C 主机控制器 - 包括 I2C 主机控制器的行为，介绍了数据发送、数据接收和数据的双向传输。

I2C 从机控制器 - 包括 I2C 从机控制器的行为，涉及数据发送和数据接收。

电源管理 - 描述了不同时钟源对功耗的影响。

IRAM 安全 - 描述了如何在 cache 被禁用时正常运行 I2C 中断。

线程安全 - 列出了驱动程序中线程安全的 API。

Kconfig 选项 - 列出了支持的 Kconfig 选项，这些选项可以对驱动程序产生不同影响。

资源分配

若系统支持 I2C 主机总线，由驱动程序中的 i2c_master_bus_handle_t 来表示。资源池管理可用的端口，并在有请求时分配空闲端口。

安装 I2C 主机总线和设备

I2C 主机总线是基于总线-设备模型设计的，因此需要分别使用 i2c_master_bus_config_t 和 i2c_device_config_t 来分配 I2C 主机总线实例和 I2C 设备实例。

I2C 主机总线-设备模块

I2C 主机总线需要 i2c_master_bus_config_t 指定的配置：

i2c_master_bus_config_t::i2c_port 设置控制器使用的 I2C 端口。

i2c_master_bus_config_t::sda_io_num 设置串行数据总线 (SDA) 的 GPIO 编号。

i2c_master_bus_config_t::scl_io_num 设置串行时钟总线 (SCL) 的 GPIO 编号。

i2c_master_bus_config_t::clk_source 选择 I2C 总线的时钟源。可用时钟列表见 i2c_clock_source_t 。有关不同时钟源对功耗的影响，请参阅 电源管理 部分。

i2c_master_bus_config_t::glitch_ignore_cnt 设置主机总线的毛刺周期。如果线上的毛刺周期小于设置的值（通常设为 7），则可以被滤除。

i2c_master_bus_config_t::intr_priority 设置中断的优先级。如果设置为 0 ，则驱动程序将使用低或中优先级的中断（优先级可设为 1、2 或 3 中的一个），若未设置，则将使用 i2c_master_bus_config_t::intr_priority 指示的优先级。请使用数字形式（1、2、3），不要用位掩码形式（(1<<1)、(1<<2)、(1<<3)）。

i2c_master_bus_config_t::trans_queue_depth 设置内部传输队列的深度，但仅在异步传输中有效。

i2c_master_bus_config_t::enable_internal_pullup 启用内部上拉电阻。注意：该设置无法在高速频率下拉高总线，此时建议使用合适的外部上拉电阻。

i2c_master_bus_config_t::allow_pd 配置驱动程序是否允许系统在睡眠模式下关闭外设电源。在进入睡眠之前，系统将备份 I2C 寄存器上下文，当系统退出睡眠模式时，这些上下文将被恢复。关闭外设可以节省更多功耗，但代价是消耗更多内存来保存寄存器上下文。你需要在功耗和内存消耗之间做权衡。此配置选项依赖于特定的硬件功能，如果在不支持的芯片上启用它，你将看到类似 not able to power down in light sleep 的错误消息。

如果在 i2c_master_bus_config_t 中指定了配置，则可调用 i2c_new_master_bus() 来分配和初始化 I2C 主机总线。如果函数运行正确，则将返回一个 I2C 总线句柄。若没有可用的 I2C 端口，此函数将返回 ESP_ERR_NOT_FOUND 错误。

I2C 主机设备需要 i2c_device_config_t 指定的配置：

i2c_device_config_t::dev_addr_length 配置从机设备的地址位长度，可从枚举 I2C_ADDR_BIT_LEN_7 或 I2C_ADDR_BIT_LEN_10 （如果支持）中进行选择。

i2c_device_config_t::device_address 设置 I2C 设备原始地址，请直接将设备地址解析到此成员。对于使用 7 位地址的设备，请使用 7 位 地址，不要使用带读/写位的 8 位地址。

i2c_device_config_t::scl_speed_hz 设置此设备的 SCL 线频率。

i2c_device_config_t::scl_wait_us 设置 SCL 等待时间（以微秒为单位）。通常此值较大，因为从机延伸时间会很长（甚至可能延伸到 12 ms）。设置为 0 表示使用默认的寄存器值。

一旦填充好 i2c_device_config_t 结构体的必要参数，就可调用 i2c_master_bus_add_device() 来分配 I2C 设备实例，并将设备挂载到主机总线上。如果函数运行正确，则将返回一个 I2C 设备句柄。若未正确初始化 I2C 总线，此函数将返回 ESP_ERR_INVALID_ARG 错误。

#include"driver/i2c_master.h"i2c_master_bus_config_ti2c_mst_config={.clk_source=I2C_CLK_SRC_DEFAULT,.i2c_port=TEST_I2C_PORT,.scl_io_num=I2C_MASTER_SCL_IO,.sda_io_num=I2C_MASTER_SDA_IO,.glitch_ignore_cnt=7,.flags.enable_internal_pullup=true,};i2c_master_bus_handle_tbus_handle;ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_mst_config,&bus_handle));i2c_device_config_tdev_cfg={.dev_addr_length=I2C_ADDR_BIT_LEN_7,.device_address=0x58,.scl_speed_hz=100000,};i2c_master_dev_handle_tdev_handle;ESP_ERROR_CHECK(i2c_master_bus_add_device(bus_handle,&dev_cfg,&dev_handle));

通过端口获取 I2C 主控句柄

当在某个模块（例如音频模块）中已经初始化了 I2C 主控句柄，但在另一个模块（例如视频模块）中不方便获取该句柄。使用辅助函数 i2c_master_get_bus_handle() 可通过端口获取已初始化的句柄。但请确保句柄已经提前初始化，否则可能会报错。

// 源文件 1#include"driver/i2c_master.h"i2c_master_bus_handle_tbus_handle;i2c_master_bus_config_ti2c_mst_config={...// 与其他相同};ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_mst_config,&bus_handle));// 源文件 2#include"driver/i2c_master.h"i2c_master_bus_handle_thandle;ESP_ERROR_CHECK(i2c_master_get_bus_handle(0,&handle));

卸载 I2C 主机总线和设备

如果不再需要之前安装的 I2C 总线或设备，建议调用 i2c_master_bus_rm_device() 或 i2c_del_master_bus() 来回收资源，以释放底层硬件。

请注意在删除 I2C master 总线之前应当删除该总线上所有的设备。

安装 I2C 从机设备

I2C 从机设备需要 i2c_slave_config_t 指定的配置：

i2c_slave_config_t::i2c_port 设置控制器使用的 I2C 端口。

i2c_slave_config_t::sda_io_num 设置串行数据总线 (SDA) 的 GPIO 编号。

i2c_slave_config_t::scl_io_num 设置串行时钟总线 (SCL) 的 GPIO 编号。

i2c_slave_config_t::clk_source 选择 I2C 总线的时钟源。可用时钟列表见 i2c_clock_source_t 。有关不同时钟源对功耗的影响，请参阅 电源管理 。

i2c_slave_config_t::send_buf_depth 设置发送软件 buffer 的长度。

i2c_slave_config_t::slave_addr 设置从机地址。

i2c_slave_config_t::intr_priority 设置中断的优先级。如果设置为 0 ，则驱动程序将使用低或中优先级的中断（优先级可设为 1、2 或 3 中的一个），若未设置，则将使用 i2c_slave_config_t::intr_priority 指示的优先级。请使用数字形式（1、2、3），不要用位掩码形式（(1<<1)、(1<<2)、(1<<3)）。请注意，中断优先级一旦设置完成，在调用 i2c_del_slave_device() 之前都无法更改。

i2c_slave_config_t::addr_bit_len 如果需要从机设备具有 10 位地址，则将该成员变量设为 I2C_ADDR_BIT_LEN_10 。

i2c_slave_config_t::allow_pd 配置驱动程序是否允许系统在睡眠模式下关闭外设电源。在进入睡眠之前，系统将备份 I2C 寄存器上下文，当系统退出睡眠模式时，这些上下文将被恢复。关闭外设可以节省更多功耗，但代价是消耗更多内存来保存寄存器上下文。你需要在功耗和内存消耗之间做权衡。此配置选项依赖于特定的硬件功能，如果在不支持的芯片上启用它，你将看到类似 not able to power down in light sleep 的错误消息。

i2c_slave_config_t::enable_internal_pullup 置 true 使能内部上拉。尽管如此，强烈建议使用外部上拉电阻。

一旦填充好 i2c_slave_config_t 结构体的必要参数，就可调用 i2c_new_slave_device() 来分配和初始化 I2C 主机总线。如果函数运行正确，则将返回一个 I2C 总线句柄。若没有可用的 I2C 端口，此函数将返回 ESP_ERR_NOT_FOUND 错误。

i2c_slave_config_ti2c_slv_config={.i2c_port=I2C_SLAVE_NUM,.clk_source=I2C_CLK_SRC_DEFAULT,.scl_io_num=I2C_SLAVE_SCL_IO,.sda_io_num=I2C_SLAVE_SDA_IO,.slave_addr=ESP_SLAVE_ADDR,.send_buf_depth=100,.receive_buf_depth=100,};i2c_slave_dev_handle_tslave_handle;ESP_ERROR_CHECK(i2c_new_slave_device(&i2c_slv_config,&slave_handle));

卸载 I2C 从机设备

如果不再需要之前安装的 I2C 总线，建议调用 i2c_del_slave_device() 来回收资源，以释放底层硬件。

I2C 主机控制器

通过调用 i2c_new_master_bus() 安装好 I2C 主机控制器驱动程序后，ESP32 就可以与其他 I2C 设备进行通信了。I2C API 允许标准事务，如下图所示：

I2C 主机写入

在成功安装 I2C 主机总线之后，可以通过调用 i2c_master_transmit() 来向从机设备写入数据。下图解释了该函数的原理。

简单来说，驱动程序用一系列命令填充了一个命令链，并将该命令链传递给 I2C 控制器执行。

I2C 主机向从机设备写入数据

将数据写入从机设备的简单示例：

#define DATA_LENGTH 100i2c_master_bus_config_ti2c_mst_config={.clk_source=I2C_CLK_SRC_DEFAULT,.i2c_port=I2C_PORT_NUM_0,.scl_io_num=I2C_MASTER_SCL_IO,.sda_io_num=I2C_MASTER_SDA_IO,.glitch_ignore_cnt=7,};i2c_master_bus_handle_tbus_handle;ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_mst_config,&bus_handle));i2c_device_config_tdev_cfg={.dev_addr_length=I2C_ADDR_BIT_LEN_7,.device_address=0x58,.scl_speed_hz=100000,};i2c_master_dev_handle_tdev_handle;ESP_ERROR_CHECK(i2c_master_bus_add_device(bus_handle,&dev_cfg,&dev_handle));ESP_ERROR_CHECK(i2c_master_transmit(dev_handle,data_wr,DATA_LENGTH,-1));

I2C 主机写入操作还支持在单次传输事务中传输多个 buffer。如下所示：

uint8_tcontrol_phase_byte=0;size_tcontrol_phase_size=0;if(/*condition*/){control_phase_byte=1;control_phase_size=1;}uint8_t*cmd_buffer=NULL;size_tcmd_buffer_size=0;if(/*condition*/){uint8_tcmds[4]={BYTESHIFT(lcd_cmd,3),BYTESHIFT(lcd_cmd,2),BYTESHIFT(lcd_cmd,1),BYTESHIFT(lcd_cmd,0)};cmd_buffer=cmds;cmd_buffer_size=4;}uint8_t*lcd_buffer=NULL;size_tlcd_buffer_size=0;if(buffer){lcd_buffer=(uint8_t*)buffer;lcd_buffer_size=buffer_size;}i2c_master_transmit_multi_buffer_info_tlcd_i2c_buffer[3]={{.write_buffer=&control_phase_byte,.buffer_size=control_phase_size},{.write_buffer=cmd_buffer,.buffer_size=cmd_buffer_size},{.write_buffer=lcd_buffer,.buffer_size=lcd_buffer_size},};i2c_master_multi_buffer_transmit(handle,lcd_i2c_buffer,sizeof(lcd_i2c_buffer)/sizeof(i2c_master_transmit_multi_buffer_info_t),-1);

I2C 主机读取

在成功安装 I2C 主机总线后，可以通过调用 i2c_master_receive() 从从机设备读取数据。下图解释了该函数的原理。

I2C 主机从从机设备读取数据

从从机设备读取数据的简单示例：

#define DATA_LENGTH 100i2c_master_bus_config_ti2c_mst_config={.clk_source=I2C_CLK_SRC_DEFAULT,.i2c_port=I2C_PORT_NUM_0,.scl_io_num=I2C_MASTER_SCL_IO,.sda_io_num=I2C_MASTER_SDA_IO,.glitch_ignore_cnt=7,};i2c_master_bus_handle_tbus_handle;ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_mst_config,&bus_handle));i2c_device_config_tdev_cfg={.dev_addr_length=I2C_ADDR_BIT_LEN_7,.device_address=0x58,.scl_speed_hz=100000,};i2c_master_dev_handle_tdev_handle;ESP_ERROR_CHECK(i2c_master_bus_add_device(bus_handle,&dev_cfg,&dev_handle));i2c_master_receive(dev_handle,data_rd,DATA_LENGTH,-1);

I2C 主机写入后读取

从一些 I2C 设备中读取数据之前需要进行写入配置，可通过 i2c_master_transmit_receive() 接口进行配置。下图解释了该函数的原理。

I2C 主机向从机设备写入并从从机设备读取数据

请注意，在写入操作和读取操作之间没有插入 STOP 条件位，因此该功能适用于从 I2C 设备读取寄存器。以下是向从机设备写入数据并从从机设备读取数据的简单示例：

i2c_device_config_tdev_cfg={.dev_addr_length=I2C_ADDR_BIT_LEN_7,.device_address=0x58,.scl_speed_hz=100000,};i2c_master_dev_handle_tdev_handle;ESP_ERROR_CHECK(i2c_master_bus_add_device(bus_handle,&dev_cfg,&dev_handle));uint8_tbuf[20]={0x20};uint8_tbuffer[2];ESP_ERROR_CHECK(i2c_master_transmit_receive(dev_handle,buf,sizeof(buf),buffer,2,-1));

I2C 主机探测

I2C 驱动程序可以使用 i2c_master_probe() 来检测设备是否已经连接到 I2C 总线上。如果该函数返回 ESP_OK ，则表示该设备已经被检测到。

重要

在调用该函数时，必须将上拉电阻连接到 SCL 和 SDA 管脚。如果在正确解析 xfer_timeout_ms 时收到 ESP_ERR_TIMEOUT ，则应检查上拉电阻。若暂无合适的电阻，也可将 flags.enable_internal_pullup 设为 true。

I2C 主机探测

探测 I2C 设备的简单示例：

i2c_master_bus_config_ti2c_mst_config_1={.clk_source=I2C_CLK_SRC_DEFAULT,.i2c_port=TEST_I2C_PORT,.scl_io_num=I2C_MASTER_SCL_IO,.sda_io_num=I2C_MASTER_SDA_IO,.glitch_ignore_cnt=7,.flags.enable_internal_pullup=true,};i2c_master_bus_handle_tbus_handle;ESP_ERROR_CHECK(i2c_new_master_bus(&i2c_mst_config_1,&bus_handle));ESP_ERROR_CHECK(i2c_master_probe(bus_handle,0x22,-1));ESP_ERROR_CHECK(i2c_del_master_bus(bus_handle));

I2C 主机执行自定义事务

并非所有 I2C 设备都严格遵循标准的 I2C 协议，不同制造商可能会对协议进行自定义修改。例如，某些设备可能要求地址移位，还有一些设备要求对特定操作进行应答 (ACK) 检查等。为此，开发者可以调用 i2c_master_execute_defined_operations() 函数灵活自定义和执行 I2C 事务，根据设备的特定要求来定制事务顺序、地址和应答行为，确保能与非标准设备流畅通讯。

备注

若想在 i2c_operation_job_t 中定义设备地址，请将 i2c_device_config_t::device_address 设置为 I2C_DEVICE_ADDRESS_NOT_USED ，跳过驱动程序中的内部地址配置。

假设设备地址为 0x20 ，使用自定义事务进行地址配置时，会出现以下两种情况：

i2c_device_config_ti2c_device={.device_address=I2C_DEVICE_ADDRESS_NOT_USED,.scl_speed_hz=100*1000,.scl_wait_us=20000,};i2c_master_dev_handle_tdev_handle;i2c_master_bus_add_device(bus_handle,&i2c_device,&dev_handle);// 情况一：设备不要求地址移位uint8_taddress1=0x20;i2c_operation_job_ti2c_ops1[]={{.command=I2C_MASTER_CMD_START},{.command=I2C_MASTER_CMD_WRITE,.write={.ack_check=false,.data=(uint8_t*)&address1,.total_bytes=1}},{.command=I2C_MASTER_CMD_STOP},};// 情况二：设备要求地址左移一位，以包含读位或写位（符合官方协议）uint8_taddress2=(0x20<<1|0);// (0x20 << 1 | 1)i2c_operation_job_ti2c_ops2[]={{.command=I2C_MASTER_CMD_START},{.command=I2C_MASTER_CMD_WRITE,.write={.ack_check=false,.data=(uint8_t*)&address2,.total_bytes=1}},{.command=I2C_MASTER_CMD_STOP},};

某些设备不需要地址即可进行数据传输，如下所示：

uint8_tdata[8]={0x11,0x22,0x33,0x44,0x55,0x66,0x77,0x88};i2c_operation_job_ti2c_ops[]={{.command=I2C_MASTER_CMD_START},{.command=I2C_MASTER_CMD_WRITE,.write={.ack_check=false,.data=(uint8_t*)data,.total_bytes=8}},{.command=I2C_MASTER_CMD_STOP},};i2c_master_execute_defined_operations(dev_handle,i2c_ops,sizeof(i2c_ops)/sizeof(i2c_operation_job_t),-1);

读取操作的原理与写入操作相同。需要注意的是，在发送停止 (STOP) 命令之前，主机读取的最后一个字节必须是 NACK 。示例如下：

uint8_taddress=(0x20<<1|1);uint8_trcv_data[10]={};i2c_operation_job_ti2c_ops[]={{.command=I2C_MASTER_CMD_START},{.command=I2C_MASTER_CMD_WRITE,.write={.ack_check=false,.data=(uint8_t*)&address,.total_bytes=1}},{.command=I2C_MASTER_CMD_READ,.read={.ack_value=I2C_ACK_VAL,.data=(uint8_t*)rcv_data,.total_bytes=9}},{.command=I2C_MASTER_CMD_READ,.read={.ack_value=I2C_NACK_VAL,.data=(uint8_t*)(rcv_data+9),.total_bytes=1}},// 此处必须为 NACK{.command=I2C_MASTER_CMD_STOP},};i2c_master_execute_defined_operations(dev_handle,i2c_ops,sizeof(i2c_ops)/sizeof(i2c_operation_job_t),-1);

I2C 从机控制器

调用 i2c_new_slave_device() 函数安装 I2C 从机设备驱动程序后, ESP32 即可作为 I2C 从机设备与其他 I2C 主机设备进行通信。

与 I2C 主机设备相比，I2C 从机设备的行为更加被动。I2C 主机设备可以自主决定何时发送或接收数据，而 I2C 从机设备通常处于被动响应状态，数据的发送和接收主要依赖于主机设备的操作。因此，驱动程序中提供了两个回调函数，分别用于处理来自 I2C 主机设备的读取请求和写入请求。

I2C 从机写入

通过注册 i2c_slave_event_callbacks_t::on_request 回调函数，可以获取 I2C 从机写入事件。在触发请求事件的任务中可以调用 i2c_slave_write 函数来发送数据。

传输数据的简单示例：

// 准备回调函数staticbooli2c_slave_request_cb(i2c_slave_dev_handle_ti2c_slave,consti2c_slave_request_event_data_t*evt_data,void*arg){i2c_slave_event_tevt=I2C_SLAVE_EVT_TX;BaseType_txTaskWoken=0;xQueueSendFromISR(context->event_queue,&evt,&xTaskWoken);returnxTaskWoken;}// 在任务中注册回调函数i2c_slave_event_callbacks_tcbs={.on_request=i2c_slave_request_cb,};ESP_ERROR_CHECK(i2c_slave_register_event_callbacks(context.handle,&cbs,&context));// 等待请求事件并在任务中发送数据staticvoidi2c_slave_task(void*arg){uint8_tbuffer_size=64;uint32_twrite_len;uint8_t*data_buffer;while(true){i2c_slave_event_tevt;if(xQueueReceive(context->event_queue,&evt,10)==pdTRUE){ESP_ERROR_CHECK(i2c_slave_write(handle,data_buffer,buffer_size,&write_len,1000));}}vTaskDelete(NULL);}

I2C 从机读取

与写入事件一样，你也可以通过注册 i2c_slave_event_callbacks_t::on_receive 回调函数来获取 I2C 从机读取事件。在触发请求事件的任务中，你可以保存数据并执行后续操作。

以下是接收数据的简单示例：

// 准备回调函数staticbooli2c_slave_receive_cb(i2c_slave_dev_handle_ti2c_slave,consti2c_slave_rx_done_event_data_t*evt_data,void*arg){i2c_slave_event_tevt=I2C_SLAVE_EVT_RX;BaseType_txTaskWoken=0;// 通过 i2c_slave_rx_done_event_data_t 来获取数据及其长度xQueueSendFromISR(context->event_queue,&evt,&xTaskWoken);returnxTaskWoken;}// 在任务中注册回调函数i2c_slave_event_callbacks_tcbs={.on_receive=i2c_slave_receive_cb,};ESP_ERROR_CHECK(i2c_slave_register_event_callbacks(context.handle,&cbs,&context));

注册事件回调函数

I2C 主机回调

当 I2C 主机总线触发中断时，将生成特定事件并通知 CPU。如果需要在发生这些事件时调用某些函数，可通过 i2c_master_register_event_callbacks() 将这些函数挂接到中断服务程序 (ISR) 上。由于注册的回调函数是在中断上下文中被调用的，所以应确保这些函数不会阻塞（例如，确保仅从函数内部调用带有 ISR 后缀的 FreeRTOS API）。回调函数需要返回一个布尔值，告诉 ISR 是否唤醒了高优先级任务。

I2C 主机事件回调函数列表见 i2c_master_event_callbacks_t 。

虽然 I2C 是一种同步通信协议，但也支持通过注册上述回调函数来实现异步行为，此时 I2C API 将成为非阻塞接口。但请注意，在同一总线上只有一个设备可以采用异步操作。

重要

I2C 主机异步传输仍然是一个实验性功能（问题在于当异步传输量过大时，会导致内存异常。）

i2c_master_event_callbacks_t::on_recv_done 可设置用于主机“传输完成”事件的回调函数。该函数原型在 i2c_master_callback_t 中声明。

I2C 从机回调

当 I2C 从机总线触发中断时，将生成特定事件并通知 CPU。如果需要在发生这些事件时调用某些函数，可通过 i2c_slave_register_event_callbacks() 将这些函数挂接到中断服务程序 (ISR) 上。由于注册的回调函数是在中断上下文中被调用的，所以应确保这些函数不会导致延迟（例如，确保仅从函数中调用带有 ISR 后缀的 FreeRTOS API）。回调函数需要返回一个布尔值，告诉调用者是否唤醒了高优先级任务。

I2C 从机事件回调函数列表见 i2c_slave_event_callbacks_t 。

i2c_slave_event_callbacks_t::on_request 为请求事件设置回调函数。

i2c_slave_event_callbacks_t::on_receive 为 receive 事件设置回调函数。函数原型在 i2c_slave_received_callback_t 中声明。

电源管理

启用电源管理（即打开 CONFIG_PM_ENABLE ），系统会在进入 Light-sleep 模式前调整或暂停 I2C FIFO 的时钟源，这可能会导致 I2C 信号改变，传输或接收到无效数据。

但驱动程序可以通过获取 ESP_PM_APB_FREQ_MAX 类型的电源管理锁来防止系统改变 APB 频率。每当用户创建一个以 I2C_CLK_SRC_APB 为时钟源的 I2C 总线，驱动程序将在开始 I2C 操作时获取电源管理锁，并在结束 I2C 操作时自动释放锁。

IRAM 安全

默认情况下，若 cache 因写入或擦除 flash 等原因而被禁用时，将推迟 I2C 中断。此时事件回调函数将无法按时执行，会影响实时应用的系统响应。

Kconfig 选项 CONFIG_I2C_ISR_IRAM_SAFE 能够做到以下几点：

即使 cache 被禁用，I2C 中断依旧正常运行。

将 ISR 使用的所有函数放入 IRAM 中。

将驱动程序对象放入 DRAM 中（以防它被意外映射到 PSRAM 中）。

启用以上选项，即使 cache 被禁用，I2C 中断依旧正常运行，但会增加 IRAM 的消耗。

线程安全

工厂函数 i2c_new_master_bus() 和 i2c_new_slave_device() 由驱动程序保证线程安全，这意味着可以从不同的 RTOS 任务调用这些函数，而无需额外的锁保护。

I2C 主机操作函数也通过总线操作信号保证线程安全。

i2c_master_transmit() .

i2c_master_multi_buffer_transmit() .

i2c_master_transmit_receive() .

i2c_master_receive() .

i2c_master_probe() .

I2C 从机操作函数也通过总线操作信号保证线程安全。

i2c_slave_write() .

其他函数不保证线程安全。因此，应避免在没有互斥保护的不同任务中调用这些函数。

Kconfig 选项

CONFIG_I2C_ISR_IRAM_SAFE 将在 cache 被禁用时控制默认的 ISR 处理程序正常工作，详情请参阅 IRAM 安全 。

CONFIG_I2C_ENABLE_DEBUG_LOG 可启用调试日志，但会增加固件二进制文件大小。

应用示例

peripherals/i2c/i2c_basic 演示了初始化 I2C 主机驱动程序并从 MPU9250 传感器读取数据的基本步骤。

peripherals/i2c/i2c_eeprom 演示了如何使用 I2C 主机模式从连接的 EEPROM 读取和写入数据。

peripherals/i2c/i2c_tools 演示了如何使用 I2C 工具开发 I2C 相关的应用程序，提供了用于配置 I2C 总线、扫描设备、读取、设置和检查寄存器的命令行工具。

peripherals/i2c/i2c_slave_network_sensor 演示如何使用 I2C 从机开发 I2C 相关应用程序，提供 I2C 从机如何充当网络传感器，以及如何使用事件回调接收和发送数据。

peripherals/i2c/i2c_u8g2 演示了如何使用 I2C 主机模式与 U8G2 库对接，以控制 OLED 显示器。

API 参考

Header File

components/esp_driver_i2c/include/driver/i2c_master.h

This header file can be included with:

#include"driver/i2c_master.h"

This header file is a part of the API provided by the esp_driver_i2c component. To declare that your component depends on esp_driver_i2c , add the following to your CMakeLists.txt:

REQUIRES esp_driver_i2c

or

PRIV_REQUIRES esp_driver_i2c

Functions

esp_err_t i2c_new_master_bus ( const i2c_master_bus_config_t * bus_config , i2c_master_bus_handle_t * ret_bus_handle )

Allocate an I2C master bus.

参数 :

bus_config -- [in] I2C master bus configuration.

ret_bus_handle -- [out] I2C bus handle

返回 :

ESP_OK: I2C master bus initialized successfully.

ESP_ERR_INVALID_ARG: I2C bus initialization failed because of invalid argument.

ESP_ERR_NO_MEM: Create I2C bus failed because of out of memory.

ESP_ERR_NOT_FOUND: No more free bus.

esp_err_t i2c_master_bus_add_device ( i2c_master_bus_handle_t bus_handle , const i2c_device_config_t * dev_config , i2c_master_dev_handle_t * ret_handle )

Add I2C master BUS device.

参数 :

bus_handle -- [in] I2C bus handle.

dev_config -- [in] device config.

ret_handle -- [out] device handle.

返回 :

ESP_OK: Create I2C master device successfully.

ESP_ERR_INVALID_ARG: I2C bus initialization failed because of invalid argument.

ESP_ERR_NO_MEM: Create I2C bus failed because of out of memory.

esp_err_t i2c_del_master_bus ( i2c_master_bus_handle_t bus_handle )

Deinitialize the I2C master bus and delete the handle.

参数 :

bus_handle -- [in] I2C bus handle.

返回 :

ESP_OK: Delete I2C bus success, otherwise, failed.

Otherwise: Some module delete failed.

esp_err_t i2c_master_bus_rm_device ( i2c_master_dev_handle_t handle )

I2C master bus delete device.

参数 :

handle -- i2c device handle

返回 :

ESP_OK: If device is successfully deleted.

esp_err_t i2c_master_transmit ( i2c_master_dev_handle_t i2c_dev , const uint8_t * write_buffer , size_t write_size , int xfer_timeout_ms )

Perform a write transaction on the I2C bus. The transaction will be undergoing until it finishes or it reaches the timeout provided.

备注

If a callback was registered with i2c_master_register_event_callbacks , the transaction will be asynchronous, and thus, this function will return directly, without blocking. You will get finish information from callback. Besides, data buffer should always be completely prepared when callback is registered, otherwise, the data will get corrupt.

参数 :

i2c_dev -- [in] I2C master device handle that created by i2c_master_bus_add_device .

write_buffer -- [in] Data bytes to send on the I2C bus.

write_size -- [in] Size, in bytes, of the write buffer.

xfer_timeout_ms -- [in] Wait timeout, in ms. Note: -1 means wait forever.

返回 :

ESP_OK: I2C master transmit success.

ESP_ERR_INVALID_RESPONSE: I2C master transmit receives NACK.

ESP_ERR_INVALID_ARG: I2C master transmit parameter invalid.

ESP_ERR_TIMEOUT: Operation timeout(larger than xfer_timeout_ms) because the bus is busy or hardware crash.

esp_err_t i2c_master_multi_buffer_transmit ( i2c_master_dev_handle_t i2c_dev , i2c_master_transmit_multi_buffer_info_t * buffer_info_array , size_t array_size , int xfer_timeout_ms )

Transmit multiple buffers of data over an I2C bus.

This function transmits multiple buffers of data over an I2C bus using the specified I2C master device handle. It takes in an array of buffer information structures along with the size of the array and a transfer timeout value in milliseconds.

参数 :

i2c_dev -- I2C master device handle that created by i2c_master_bus_add_device .

buffer_info_array -- Pointer to buffer information array.

array_size -- size of buffer information array.

xfer_timeout_ms -- Wait timeout, in ms. Note: -1 means wait forever.

返回 :

ESP_OK: I2C master transmit success.

ESP_ERR_INVALID_RESPONSE: I2C master transmit receives NACK.

ESP_ERR_INVALID_ARG: I2C master transmit parameter invalid.

ESP_ERR_TIMEOUT: Operation timeout(larger than xfer_timeout_ms) because the bus is busy or hardware crash.

esp_err_t i2c_master_transmit_receive ( i2c_master_dev_handle_t i2c_dev , const uint8_t * write_buffer , size_t write_size , uint8_t * read_buffer , size_t read_size , int xfer_timeout_ms )

Perform a write-read transaction on the I2C bus. The transaction will be undergoing until it finishes or it reaches the timeout provided.

备注

If a callback was registered with i2c_master_register_event_callbacks , the transaction will be asynchronous, and thus, this function will return directly, without blocking. You will get finish information from callback. Besides, data buffer should always be completely prepared when callback is registered, otherwise, the data will get corrupt.

参数 :

i2c_dev -- [in] I2C master device handle that created by i2c_master_bus_add_device .

write_buffer -- [in] Data bytes to send on the I2C bus.

write_size -- [in] Size, in bytes, of the write buffer.

read_buffer -- [out] Data bytes received from i2c bus.

read_size -- [in] Size, in bytes, of the read buffer.

xfer_timeout_ms -- [in] Wait timeout, in ms. Note: -1 means wait forever.

返回 :

ESP_OK: I2C master transmit-receive success.

ESP_ERR_INVALID_RESPONSE: I2C master transmit-receive receives NACK.

ESP_ERR_INVALID_ARG: I2C master transmit parameter invalid.

ESP_ERR_TIMEOUT: Operation timeout(larger than xfer_timeout_ms) because the bus is busy or hardware crash.

esp_err_t i2c_master_receive ( i2c_master_dev_handle_t i2c_dev , uint8_t * read_buffer , size_t read_size , int xfer_timeout_ms )

Perform a read transaction on the I2C bus. The transaction will be undergoing until it finishes or it reaches the timeout provided.

备注

If a callback was registered with i2c_master_register_event_callbacks , the transaction will be asynchronous, and thus, this function will return directly, without blocking. You will get finish information from callback. Besides, data buffer should always be completely prepared when callback is registered, otherwise, the data will get corrupt.

参数 :

i2c_dev -- [in] I2C master device handle that created by i2c_master_bus_add_device .

read_buffer -- [out] Data bytes received from i2c bus.

read_size -- [in] Size, in bytes, of the read buffer.

xfer_timeout_ms -- [in] Wait timeout, in ms. Note: -1 means wait forever.

返回 :

ESP_OK: I2C master receive success

ESP_ERR_INVALID_ARG: I2C master receive parameter invalid.

ESP_ERR_TIMEOUT: Operation timeout(larger than xfer_timeout_ms) because the bus is busy or hardware crash.

esp_err_t i2c_master_probe ( i2c_master_bus_handle_t bus_handle , uint16_t address , int xfer_timeout_ms )

Probe I2C address, if address is correct and ACK is received, this function will return ESP_OK.

Attention

Pull-ups must be connected to the SCL and SDA pins when this function is called. If you get ESP_ERR_TIMEOUT while xfer_timeout_ms was parsed correctly, you should check the pull-up resistors. If you do not have proper resistors nearby. flags.enable_internal_pullup is also acceptable.

备注

The principle of this function is to sent device address with a write command. If the device on your I2C bus, there would be an ACK signal and function returns ESP_OK . If the device is not on your I2C bus, there would be a NACK signal and function returns ESP_ERR_NOT_FOUND . ESP_ERR_TIMEOUT is not an expected failure, which indicated that the i2c probe not works properly, usually caused by pull-up resistors not be connected properly. Suggestion check data on SDA/SCL line to see whether there is ACK/NACK signal is on line when i2c probe function fails.

备注

There are lots of I2C devices all over the world, we assume that not all I2C device support the behavior like device_address+nack/ack . So, if the on line data is strange and no ack/nack got respond. Please check the device datasheet.

参数 :

bus_handle -- [in] I2C master bus handle, created by i2c_new_master_bus .

address -- [in] I2C device address that you want to probe.

xfer_timeout_ms -- [in] Wait timeout, in ms. Note: -1 means wait forever (Not recommended in this function).

返回 :

ESP_OK: I2C device probed successfully.

ESP_ERR_NOT_FOUND: I2C probe failed, doesn't find the device with specific address you gave.

ESP_ERR_TIMEOUT: Operation timeout(larger than xfer_timeout_ms) because the bus is busy or hardware crash.

esp_err_t i2c_master_execute_defined_operations ( i2c_master_dev_handle_t i2c_dev , i2c_operation_job_t * i2c_operation , size_t operation_list_num , int xfer_timeout_ms )

Execute a series of pre-defined I2C operations.

This function processes a list of I2C operations, such as start, write, read, and stop, according to the user-defined i2c_operation_job_t array. It performs these operations sequentially on the specified I2C master device.

备注

The ack_value field in the READ operation must be set to I2C_NACK_VAL if the next operation is a STOP command.

参数 :

i2c_dev -- [in] Handle to the I2C master device.

i2c_operation -- [in] Pointer to an array of user-defined I2C operation jobs. Each job specifies a command and associated parameters.

operation_list_num -- [in] The number of operations in the i2c_operation array.

xfer_timeout_ms -- [in] Timeout for the transaction, in milliseconds.

返回 :

ESP_OK: Transaction completed successfully.

ESP_ERR_INVALID_RESPONSE: I2C master transaction receives NACK.

ESP_ERR_INVALID_ARG: One or more arguments are invalid.

ESP_ERR_TIMEOUT: Transaction timed out.

esp_err_t i2c_master_register_event_callbacks ( i2c_master_dev_handle_t i2c_dev , const i2c_master_event_callbacks_t * cbs , void * user_data )

Register I2C transaction callbacks for a master device.

备注

User can deregister a previously registered callback by calling this function and setting the callback member in the cbs structure to NULL.

备注

When CONFIG_I2C_ISR_IRAM_SAFE is enabled, the callback itself and functions called by it should be placed in IRAM. The variables used in the function should be in the SRAM as well. The user_data should also reside in SRAM.

备注

If the callback is used for helping asynchronous transaction. On the same bus, only one device can be used for performing asynchronous operation.

参数 :

i2c_dev -- [in] I2C master device handle that created by i2c_master_bus_add_device .

cbs -- [in] Group of callback functions

user_data -- [in] User data, which will be passed to callback functions directly

返回 :

ESP_OK: Set I2C transaction callbacks successfully

ESP_ERR_INVALID_ARG: Set I2C transaction callbacks failed because of invalid argument

ESP_FAIL: Set I2C transaction callbacks failed because of other error

esp_err_t i2c_master_bus_reset ( i2c_master_bus_handle_t bus_handle )

Reset the I2C master bus.

参数 :

bus_handle -- I2C bus handle.

返回 :

ESP_OK: Reset succeed.

ESP_ERR_INVALID_ARG: I2C master bus handle is not initialized.

Otherwise: Reset failed.

esp_err_t i2c_master_device_change_address ( i2c_master_dev_handle_t i2c_dev , uint16_t new_device_address , int timeout_ms )

Change the I2C device address at runtime.

This function updates the device address of an existing I2C device handle. It is useful for devices that support dynamic address assignment or when switching communication to a device with a different address on the same bus.

备注

This function does not send commands to the I2C device. It only updates the address used in subsequent transactions through the I2C handle.

Ensure that the new address is valid and does not conflict with other devices on the bus.

参数 :

i2c_dev -- [in] I2C device handle.

new_device_address -- [in] The new device address.

timeout_ms -- [in] Timeout for the address change operation, in milliseconds.

返回 :

ESP_OK: Address successfully changed.

ESP_ERR_INVALID_ARG: Invalid arguments (e.g., NULL handle or invalid address).

ESP_ERR_TIMEOUT: Operation timed out.

esp_err_t i2c_master_bus_wait_all_done ( i2c_master_bus_handle_t bus_handle , int timeout_ms )

Wait for all pending I2C transactions done.

参数 :

bus_handle -- [in] I2C bus handle

timeout_ms -- [in] Wait timeout, in ms. Specially, -1 means to wait forever.

返回 :

ESP_OK: Flush transactions successfully

ESP_ERR_INVALID_ARG: Flush transactions failed because of invalid argument

ESP_ERR_TIMEOUT: Flush transactions failed because of timeout

ESP_FAIL: Flush transactions failed because of other error

esp_err_t i2c_master_get_bus_handle ( i2c_port_num_t port_num , i2c_master_bus_handle_t * ret_handle )

Retrieves the I2C master bus handle for a specified I2C port number.

This function retrieves the I2C master bus handle for the given I2C port number. Please make sure the handle has already been initialized, and this function would simply returns the existing handle. Note that the returned handle still can't be used concurrently

参数 :

port_num -- I2C port number for which the handle is to be retrieved.

ret_handle -- Pointer to a variable where the retrieved handle will be stored.

返回 :

ESP_OK: Success. The handle is retrieved successfully.

ESP_ERR_INVALID_ARG: Invalid argument, such as invalid port number

ESP_ERR_INVALID_STATE: Invalid state, such as the I2C port is not initialized.

Structures

struct i2c_master_bus_config_t

I2C master bus specific configurations.

Public Members

i2c_port_num_t i2c_port

I2C port number, -1 for auto selecting, (not include LP I2C instance)

gpio_num_t sda_io_num

GPIO number of I2C SDA signal, pulled-up internally

gpio_num_t scl_io_num

GPIO number of I2C SCL signal, pulled-up internally

i2c_clock_source_t clk_source

Clock source of I2C master bus

uint8_t glitch_ignore_cnt

If the glitch period on the line is less than this value, it can be filtered out, typically value is 7 (unit: I2C module clock cycle)

int intr_priority

I2C interrupt priority, if set to 0, driver will select the default priority (1,2,3).

size_t trans_queue_depth

Depth of internal transfer queue, increase this value can support more transfers pending in the background, only valid in asynchronous transaction. (Typically max_device_num * per_transaction)

uint32_t enable_internal_pullup

Enable internal pullups. Note: This is not strong enough to pullup buses under high-speed frequency. Recommend proper external pull-up if possible

uint32_t allow_pd

If set, the driver will backup/restore the I2C registers before/after entering/exist sleep mode. By this approach, the system can power off I2C's power domain. This can save power, but at the expense of more RAM being consumed

struct i2c_master_bus_config_t flags

I2C master config flags

struct i2c_device_config_t

I2C device configuration.

Public Members

i2c_addr_bit_len_t dev_addr_length

Select the address length of the slave device.

uint16_t device_address

I2C device raw address. (The 7/10 bit address without read/write bit). Macro I2C_DEVICE_ADDRESS_NOT_USED (0xFFFF) stands for skip the address config inside driver.

uint32_t scl_speed_hz

I2C SCL line frequency.

uint32_t scl_wait_us

Timeout value. (unit: us). Please note this value should not be so small that it can handle stretch/disturbance properly. If 0 is set, that means use the default reg value

uint32_t disable_ack_check

Disable ACK check. If this is set false, that means ack check is enabled, the transaction will be stopped and API returns error when nack is detected.

struct i2c_device_config_t flags

I2C device config flags

struct i2c_operation_job_t

Structure representing an I2C operation job.

This structure is used to define individual I2C operations (write or read) within a sequence of I2C master transactions.

备注

The union contains either write or read operation parameters.

For write operations: use .write.data (const uint8_t *) to provide data to be written

For read operations: use .read.data (uint8_t *) to provide buffer for storing read data

Public Members

i2c_master_command_t command

I2C command indicating the type of operation (START, WRITE, READ, or STOP)

bool ack_check

Whether to enable ACK check during WRITE operation

const uint8_t * data

Pointer to the data to be written

size_t total_bytes

Total number of bytes to write

Total number of bytes to read

struct i2c_operation_job_t write

Structure for WRITE command.

Used when the command is set to I2C_MASTER_CMD_WRITE .

i2c_ack_value_t ack_value

ACK value to send after the read (ACK or NACK)

uint8_t * data

Pointer to the buffer for storing the data read from the bus

struct i2c_operation_job_t read

Structure for READ command.

Used when the command is set to I2C_MASTER_CMD_READ .

struct i2c_master_transmit_multi_buffer_info_t

I2C master transmit buffer information structure.

Public Members

const uint8_t * write_buffer

Pointer to buffer to be written.

size_t buffer_size

Size of data to be written.

struct i2c_master_event_callbacks_t

Group of I2C master callbacks, can be used to get status during transaction or doing other small things. But take care potential concurrency issues.

备注

The callbacks are all running under ISR context

备注

When CONFIG_I2C_ISR_IRAM_SAFE is enabled, the callback itself and functions called by it should be placed in IRAM. The variables used in the function should be in the SRAM as well.

Public Members

i2c_master_callback_t on_trans_done

I2C master transaction finish callback

Macros

I2C_DEVICE_ADDRESS_NOT_USED

Skip carry address bit in driver transmit and receive

Header File

components/esp_driver_i2c/include/driver/i2c_slave.h

This header file can be included with:

#include"driver/i2c_slave.h"

This header file is a part of the API provided by the esp_driver_i2c component. To declare that your component depends on esp_driver_i2c , add the following to your CMakeLists.txt:

REQUIRES esp_driver_i2c

or

PRIV_REQUIRES esp_driver_i2c

Functions

esp_err_t i2c_slave_write ( i2c_slave_dev_handle_t i2c_slave , const uint8_t * data , uint32_t len , uint32_t * write_len , int timeout_ms )

Write buffer to hardware fifo. If write length is larger than hardware fifo, then restore in software buffer.

参数 :

i2c_slave -- [in] I2C slave device handle that created by i2c_new_slave_device .

data -- [in] Buffer to write to slave fifo, can pickup by master.

len -- [in] In bytes, of data buffer.

write_len -- [out] In bytes, actually write length.

timeout_ms -- [in] Wait timeout, in ms. Note: -1 means wait forever.

返回 :

ESP_OK: I2C slave write success.

ESP_ERR_INVALID_ARG: I2C slave write parameter invalid.

ESP_ERR_TIMEOUT: Operation timeout(larger than xfer_timeout_ms) because the device is busy or hardware crash.

esp_err_t i2c_new_slave_device ( const i2c_slave_config_t * slave_config , i2c_slave_dev_handle_t * ret_handle )

Initialize an I2C slave device.

参数 :

slave_config -- [in] I2C slave device configurations

ret_handle -- [out] Return a generic I2C device handle

返回 :

ESP_OK: I2C slave device initialized successfully

ESP_ERR_INVALID_ARG: I2C device initialization failed because of invalid argument.

ESP_ERR_NO_MEM: Create I2C device failed because of out of memory.

esp_err_t i2c_slave_register_event_callbacks ( i2c_slave_dev_handle_t i2c_slave , const i2c_slave_event_callbacks_t * cbs , void * user_data )

Set I2C slave event callbacks for I2C slave channel.

备注

User can deregister a previously registered callback by calling this function and setting the callback member in the cbs structure to NULL.

备注

When CONFIG_I2C_ISR_IRAM_SAFE is enabled, the callback itself and functions called by it should be placed in IRAM. The variables used in the function should be in the SRAM as well. The user_data should also reside in SRAM.

参数 :

i2c_slave -- [in] I2C slave device handle that created by i2c_new_slave_device .

cbs -- [in] Group of callback functions

user_data -- [in] User data, which will be passed to callback functions directly

返回 :

ESP_OK: Set I2C transaction callbacks successfully

ESP_ERR_INVALID_ARG: Set I2C transaction callbacks failed because of invalid argument

ESP_FAIL: Set I2C transaction callbacks failed because of other error

esp_err_t i2c_del_slave_device ( i2c_slave_dev_handle_t i2c_slave )

Deinitialize the I2C slave device.

参数 :

i2c_slave -- [in] I2C slave device handle that created by i2c_new_slave_device .

返回 :

ESP_OK: Delete I2C device successfully.

ESP_ERR_INVALID_ARG: I2C device initialization failed because of invalid argument.

Structures

struct i2c_slave_config_t

I2C slave specific configurations.

Public Members

i2c_port_num_t i2c_port

I2C port number, -1 for auto selecting

gpio_num_t sda_io_num

SDA IO number used by I2C bus

gpio_num_t scl_io_num

SCL IO number used by I2C bus

i2c_clock_source_t clk_source

Clock source of I2C bus.

uint32_t send_buf_depth

Depth of internal transfer ringbuffer

uint32_t receive_buf_depth

Depth of receive internal software buffer

uint16_t slave_addr

I2C slave address

i2c_addr_bit_len_t addr_bit_len

I2C slave address in bit length

int intr_priority

I2C interrupt priority, if set to 0, driver will select the default priority (1,2,3).

uint32_t allow_pd

If set, the driver will backup/restore the I2C registers before/after entering/exist sleep mode. By this approach, the system can power off I2C's power domain. This can save power, but at the expense of more RAM being consumed

uint32_t enable_internal_pullup

Enable internal pullups. Note: This is not strong enough to pullup buses under high-speed frequency. Recommend proper external pull-up if possible

struct i2c_slave_config_t flags

I2C slave config flags

struct i2c_slave_event_callbacks_t

Group of I2C slave callbacks. Take care of potential concurrency issues.

备注

The callbacks are all running under ISR context

备注

When CONFIG_I2C_ISR_IRAM_SAFE is enabled, the callback itself and functions called by it should be placed in IRAM. The variables used in the function should be in the SRAM as well.

Public Members

i2c_slave_request_callback_t on_request

Callback for when a master requests data from the slave

i2c_slave_received_callback_t on_receive

Callback for when the slave receives data from the master

Header File

components/esp_driver_i2c/include/driver/i2c_types.h

This header file can be included with:

#include"driver/i2c_types.h"

This header file is a part of the API provided by the esp_driver_i2c component. To declare that your component depends on esp_driver_i2c , add the following to your CMakeLists.txt:

REQUIRES esp_driver_i2c

or

PRIV_REQUIRES esp_driver_i2c

Structures

struct i2c_master_event_data_t

Data type used in I2C event callback.

Public Members

i2c_master_event_t event

The I2C hardware event that I2C callback is called.

struct i2c_slave_rx_done_event_data_t

Event structure used in I2C slave.

Public Members

uint8_t * buffer

Pointer for buffer received in callback.

uint32_t length

Length for buffer received in callback.

struct i2c_slave_request_event_data_t

Event structure used in I2C slave request.

Type Definitions

typedef int i2c_port_num_t

I2C port number.

typedef struct i2c_master_bus_t * i2c_master_bus_handle_t

Type of I2C master bus handle.

typedef struct i2c_master_dev_t * i2c_master_dev_handle_t

Type of I2C master bus device handle.

typedef struct i2c_slave_dev_t * i2c_slave_dev_handle_t

Type of I2C slave device handle.

typedef bool ( * i2c_master_callback_t ) ( i2c_master_dev_handle_t i2c_dev , const i2c_master_event_data_t * evt_data , void * arg )

An callback for I2C transaction.

Param i2c_dev :

[in] Handle for I2C device.

Param evt_data :

[out] I2C capture event data, fed by driver

Param arg :

[in] User data, set in i2c_master_register_event_callbacks()

Return :

Whether a high priority task has been waken up by this function

typedef bool ( * i2c_slave_received_callback_t ) ( i2c_slave_dev_handle_t i2c_slave , const i2c_slave_rx_done_event_data_t * evt_data , void * arg )

Callback signature for I2C slave.

Param i2c_slave :

[in] Handle for I2C slave.

Param evt_data :

[out] I2C capture event data, fed by driver

Param arg :

[in] User data, set in i2c_slave_register_event_callbacks()

Return :

Whether a high priority task has been waken up by this function

typedef bool ( * i2c_slave_request_callback_t ) ( i2c_slave_dev_handle_t i2c_slave , const i2c_slave_request_event_data_t * evt_data , void * arg )

Callback signature for I2C slave request event. When this callback is triggered that means master want to read data from slave while there is no data in slave fifo. So user should write data to fifo via i2c_slave_write

Param i2c_slave :

[in] Handle for I2C slave.

Param evt_data :

[out] I2C receive event data, fed by driver

Param arg :

[in] User data, set in i2c_slave_register_event_callbacks()

Return :

Whether a high priority task has been waken up by this function

Enumerations

enum i2c_master_status_t

Enumeration for I2C fsm status.

Values:

enumerator I2C_STATUS_READ

read status for current master command, but just partial read, not all data is read is this status

enumerator I2C_STATUS_READ_ALL

read status for current master command, all data is read is this status

enumerator I2C_STATUS_WRITE

write status for current master command

enumerator I2C_STATUS_START

Start status for current master command

enumerator I2C_STATUS_STOP

stop status for current master command

enumerator I2C_STATUS_IDLE

idle status for current master command

enumerator I2C_STATUS_ACK_ERROR

ack error status for current master command

enumerator I2C_STATUS_DONE

I2C command done

enumerator I2C_STATUS_TIMEOUT

I2C bus status error, and operation timeout

enum i2c_master_event_t

Enumeration for I2C event.

Values:

enumerator I2C_EVENT_ALIVE

i2c bus in alive status.

enumerator I2C_EVENT_DONE

i2c bus transaction done

enumerator I2C_EVENT_NACK

i2c bus nack

enumerator I2C_EVENT_TIMEOUT

i2c bus timeout

enum i2c_master_command_t

Enum for I2C master commands.

These commands are used to define the I2C master operations. They correspond to hardware-level commands supported by the I2C peripheral.

Values:

enumerator I2C_MASTER_CMD_START

Start or Restart condition

enumerator I2C_MASTER_CMD_WRITE

Write operation

enumerator I2C_MASTER_CMD_READ

Read operation

enumerator I2C_MASTER_CMD_STOP

Stop condition

enum i2c_ack_value_t

Enum for I2C master ACK values.

These values define the acknowledgment (ACK) behavior during read operations.

Values:

enumerator I2C_ACK_VAL

Acknowledge (ACK) signal

enumerator I2C_NACK_VAL

Not Acknowledge (NACK) signal

Header File

components/esp_hal_i2c/include/hal/i2c_types.h

This header file can be included with:

#include"hal/i2c_types.h"

This header file is a part of the API provided by the esp_hal_i2c component. To declare that your component depends on esp_hal_i2c , add the following to your CMakeLists.txt:

REQUIRES esp_hal_i2c

or

PRIV_REQUIRES esp_hal_i2c

Structures

struct i2c_hal_clk_config_t

Data structure for calculating I2C bus timing.

Public Members

uint16_t clkm_div

I2C core clock divider

uint16_t scl_low

I2C scl low period

uint16_t scl_high

I2C scl high period

uint16_t scl_wait_high

I2C scl wait_high period

uint16_t sda_hold

I2C scl low period

uint16_t sda_sample

I2C sda sample time

uint16_t setup

I2C start and stop condition setup period

uint16_t hold

I2C start and stop condition hold period

uint16_t tout

I2C bus timeout period

Type Definitions

typedef soc_periph_i2c_clk_src_t i2c_clock_source_t

I2C group clock source.

Enumerations

enum i2c_port_t

I2C port number, can be I2C_NUM_0 ~ (I2C_NUM_MAX-1).

Values:

enumerator I2C_NUM_0

I2C port 0

enumerator I2C_NUM_1

I2C port 1

enumerator I2C_NUM_MAX

I2C port max

enum i2c_addr_bit_len_t

Enumeration for I2C device address bit length.

Values:

enumerator I2C_ADDR_BIT_LEN_7

i2c address bit length 7

enumerator I2C_ADDR_BIT_LEN_10

i2c address bit length 10

enum i2c_mode_t

Values:

enumerator I2C_MODE_SLAVE

I2C slave mode

enumerator I2C_MODE_MASTER

I2C master mode

enumerator I2C_MODE_MAX

enum i2c_rw_t

Values:

enumerator I2C_MASTER_WRITE

I2C write data

enumerator I2C_MASTER_READ

I2C read data

enum i2c_trans_mode_t

Values:

enumerator I2C_DATA_MODE_MSB_FIRST

I2C data msb first

enumerator I2C_DATA_MODE_LSB_FIRST

I2C data lsb first

enumerator I2C_DATA_MODE_MAX

enum i2c_addr_mode_t

Values:

enumerator I2C_ADDR_BIT_7

I2C 7bit address for slave mode

enumerator I2C_ADDR_BIT_10

I2C 10bit address for slave mode

enumerator I2C_ADDR_BIT_MAX

enum i2c_ack_type_t

Values:

enumerator I2C_MASTER_ACK

I2C ack for each byte read

enumerator I2C_MASTER_NACK

I2C nack for each byte read

enumerator I2C_MASTER_LAST_NACK

I2C nack for the last byte

enumerator I2C_MASTER_ACK_MAX

enum i2c_slave_stretch_cause_t

Enum for I2C slave stretch causes.

Values:

enumerator I2C_SLAVE_STRETCH_CAUSE_ADDRESS_MATCH

Stretching SCL low when the slave is read by the master and the address just matched

enumerator I2C_SLAVE_STRETCH_CAUSE_TX_EMPTY

Stretching SCL low when TX FIFO is empty in slave mode

enumerator I2C_SLAVE_STRETCH_CAUSE_RX_FULL

Stretching SCL low when RX FIFO is full in slave mode

enumerator I2C_SLAVE_STRETCH_CAUSE_SENDING_ACK

Stretching SCL low when slave sending ACK

enum i2c_slave_read_write_status_t

Values:

enumerator I2C_SLAVE_WRITE_BY_MASTER

enumerator I2C_SLAVE_READ_BY_MASTER

enum i2c_bus_mode_t

Enum for i2c working modes.

Values:

enumerator I2C_BUS_MODE_MASTER

I2C works under master mode

enumerator I2C_BUS_MODE_SLAVE

I2C works under slave mode

此文档对您有帮助吗？

反馈已收到，谢谢！

如果您有其他意见，欢迎填写 乐鑫文档反馈表 。

我们重视您的反馈。

您可以填写 乐鑫文档反馈表 告诉我们如何改进该文档。
