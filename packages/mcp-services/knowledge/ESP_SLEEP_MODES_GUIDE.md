Source: https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32/api-reference/system/sleep_modes.html

API 参考

系统 API

睡眠模式

在 GitHub 上编辑

睡眠模式

[English]

概述

ESP32 具有 Light-sleep 和 Deep-sleep 两种睡眠节能模式。根据应用所使用的功能，还有一些细分的子睡眠模式。关于这些睡眠模式和其子模式，参见 睡眠节能模式 。另外，还可以配置一些断电选项来进一步减少功耗，请参见 断电选项 。

睡眠模式有多种唤醒源。这些唤醒源也可以组合在一起，此时任何一个唤醒源都可以触发唤醒。 唤醒源 详细描述了这些唤醒源，以及配置 API。

断电选项和唤醒源的配置不是必要的，并且可以在进入睡眠模式前的任意时候进行。

最后，应用通过调用开始睡眠的 API 来使芯片进入其中一种睡眠模式，更多详情请参见 进入睡眠模式 。当唤醒条件满足，芯片就会从睡眠中被唤醒。关于如何获取唤醒原因，请参见 检查睡眠唤醒原因 。关于醒来后如何处理唤醒源，请参见 禁用睡眠模式唤醒源 。

睡眠节能模式

在 Light-sleep 模式下，数字外设、CPU、以及大部分 RAM 都使用时钟门控，同时其供电电压降低。退出该模式后，数字外设、CPU 和 RAM 恢复运行，并且内部状态将被保留。

在 Deep-sleep 模式下，CPU、大部分 RAM、以及所有由时钟 APB_CLK 驱动的数字外设都会被断电。芯片上继续处于供电状态的部分仅包括：

RTC 控制器

ULP 协处理器

RTC 高速内存

RTC 低速内存

睡眠模式下的 Wi-Fi 和 Bluetooth 功能

在 Light-sleep 和 Deep-sleep 模式下，无线外设会被断电。因此，在进入这两种睡眠模式前，应用程序必须调用恰当的函数（ nimble_port_stop() 、 nimble_port_deinit() 、 esp_bluedroid_disable() 、 esp_bluedroid_deinit() 、 esp_bt_controller_disable() 、 esp_bt_controller_deinit() 或 esp_wifi_stop() ）来禁用 Wi-Fi 和 Bluetooth。在 Light-sleep 或 Deep-sleep 模式下，即使不调用这些函数也无法连接 Wi-Fi 和 Bluetooth。

如需保持 Wi-Fi 和 Bluetooth 连接，请启用 Wi-Fi 和 Bluetooth Modem-sleep 模式和自动 Light-sleep 模式（请参阅 电源管理 API ）。在这两种模式下，Wi-Fi 和 Bluetooth 驱动程序发出请求时，系统将自动从睡眠中被唤醒，从而保持连接。

唤醒源

通过 API esp_sleep_enable_X_wakeup 可启用唤醒源。唤醒源在芯片被唤醒后并不会被禁用，若你不再需要某些唤醒源，可通过 API esp_sleep_disable_wakeup_source() 将其禁用，详见 禁用睡眠模式唤醒源 。

以下是 ESP32 所支持的唤醒源。

定时器

RTC 控制器中内嵌定时器，可用于在预定义的时间到达后唤醒芯片。时间精度为微秒，但其实际分辨率依赖于为 RTC_SLOW_CLK 所选择的时钟源。

关于 RTC 时钟选项的更多细节，请参考 ESP32 技术参考手册 > ULP 协处理器 [ PDF ]。

在这种唤醒模式下，无需为睡眠模式中的 RTC 外设或内存供电。

调用 esp_sleep_enable_timer_wakeup() 函数可启用使用定时器唤醒睡眠模式。

触摸传感器

RTC IO 模块中包含这样一个逻辑——当发生触摸传感器中断时，触发唤醒。要启用此唤醒源，用户需要在芯片进入睡眠模式前配置触摸传感器中断功能。

ESP32 修订版 0 和 1 仅在 RTC 外设没有被强制供电时支持该唤醒源（即 ESP_PD_DOMAIN_RTC_PERIPH 应被设置为 ESP_PD_OPTION_AUTO）。

可调用 esp_sleep_enable_touchpad_wakeup() 函数来启用该唤醒源。

外部唤醒 ( ext0 )

RTC IO 模块中包含这样一个逻辑——当某个 RTC GPIO 被设置为预定义的逻辑值时，触发唤醒。RTC IO 是 RTC 外设电源域的一部分，因此如果该唤醒源被请求，RTC 外设将在 Deep-sleep 模式期间保持供电。

在此模式下，RTC IO 模块被使能，因此也可以使用内部上拉或下拉电阻。配置时，应用程序需要在调用函数 esp_deep_sleep_start() 前先调用函数 rtc_gpio_pullup_en() 和 rtc_gpio_pulldown_en() 。

在 ESP32 修订版 0 和 1 中，此唤醒源与 ULP 和触摸传感器唤醒源都不兼容。

可调用 esp_sleep_enable_ext0_wakeup() 函数来启用此唤醒源。

警告

从睡眠模式中唤醒后，用于唤醒的 IO pad 将被配置为 RTC IO。因此，在将该 pad 用作数字 GPIO 之前，请调用 rtc_gpio_deinit() 函数对其进行重新配置。

外部唤醒 ( ext1 )

RTC 控制器中包含使用多个 RTC GPIO 触发唤醒的逻辑。从以下两个逻辑函数中任选其一，均可触发 ext1 唤醒：

当任意一个所选管脚为高电平时唤醒 (ESP_EXT1_WAKEUP_ANY_HIGH)

当所有所选管脚为低电平时唤醒 (ESP_EXT1_WAKEUP_ALL_LOW)

此唤醒源由 RTC 控制器实现。即使在 RTC 外设断电的情况下仍支持唤醒。虽然睡眠期间 RTC IO 所在的 RTC 外设电源域将会断电，但是 ESP-IDF 会自动在系统进入睡眠前锁定唤醒管脚的状态并在退出睡眠时解除锁定，所以仍然可为唤醒管脚配置内部上拉或下拉电阻:

esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_PERIPH,ESP_PD_OPTION_ON);gpio_pullup_dis(gpio_num);gpio_pulldown_en(gpio_num);

如果我们关闭 RTC_PERIPH 域，我们将使用 HOLD 功能在睡眠期间维持管脚上的上拉和下拉电阻。所选管脚的 HOLD 功能会在系统真正进入睡眠前被开启，这有助于进一步减小睡眠时的功耗:

rtc_gpio_pullup_dis(gpio_num);rtc_gpio_pulldown_en(gpio_num);

如果某些芯片缺少 RTC_PERIPH 域，我们只能使用 HOLD 功能来在睡眠期间维持管脚上的上拉和下拉电阻:

gpio_pullup_dis(gpio_num);gpio_pulldown_en(gpio_num);

可调用 esp_sleep_enable_ext1_wakeup_io() 函数可用于增加 ext1 唤醒 IO 并设置相应的唤醒电平。

可调用 esp_sleep_disable_ext1_wakeup_io() 函数可用于移除 ext1 唤醒 IO。

备注

由于硬件限制，当我们将多个 IO 用于 EXT1 唤醒，此时不允许将这些 IO 的唤醒模式配置成不同的电平，在 esp_sleep_enable_ext1_wakeup_io() 已有相应的内部检查机制。

警告

使用 EXT1 唤醒源时，用于唤醒的 IO pad 将被配置为 RTC IO。因此，在将该 pad 用作数字 GPIO 之前，请调用 rtc_gpio_deinit() 函数对其进行重新配置。

RTC 外设在默认情况下配置为断电，此时，唤醒 IO 在进入睡眠状态前将被设置为保持状态。因此，从 Light-sleep 状态唤醒芯片后，请调用 rtc_gpio_hold_dis 来禁用保持功能，以便对管脚进行重新配置。对于 Deep-sleep 唤醒，此问题已经在应用启动阶段解决。

ULP 协处理器唤醒

当芯片处于睡眠模式时，ULP 协处理器仍然运行，可用于轮询传感器、监视 ADC 或 GPIO 状态，并在检测到特殊事件时唤醒芯片。ULP 协处理器是 RTC 外设电源域的一部分，运行存储在 RTC 低速内存中的程序。如果这一唤醒源被请求，RTC 低速内存将会在睡眠期间保持供电状态。RTC 外设会在 ULP 协处理器开始运行程序前自动上电；一旦程序停止运行，RTC 外设会再次自动断电。

ESP32 修订版 0 和 1 仅在 RTC 外设没有被强制供电时支持该唤醒（即 ESP_PD_DOMAIN_RTC_PERIPH 应被设置为 ESP_PD_OPTION_AUTO）。

可调用 esp_sleep_enable_ulp_wakeup() 函数来启用此唤醒源。

Light-sleep 模式下的 GPIO 唤醒

除了上述 EXT0 和 EXT1 唤醒源之外，还有一种从外部唤醒 Light-sleep 模式的方法——使用函数 gpio_wakeup_enable() 。启用该唤醒源后，可将每个管脚单独配置为在高电平或低电平时唤醒。EXT0 和 EXT1 唤醒源只能用于 RTC IO，但此唤醒源既可以用于 RTC IO，可也用于数字 IO。

可调用 esp_sleep_enable_gpio_wakeup() 函数来启用此唤醒源。

警告

在进入 Light-sleep 模式前，请查看将要驱动的 GPIO 管脚的电源域。如果有管脚属于 VDD_SDIO 电源域，必须将此电源域配置为在睡眠期间保持供电。

例如，在 ESP32-WROOM-32 开发板上，GPIO16 和 GPIO17 连接到 VDD_SDIO 电源域。如果这两个管脚被配置为在睡眠期间保持高电平，则需将对应电源域配置为保持供电。为此，可以使用函数 esp_sleep_pd_config() :

esp_sleep_pd_config(ESP_PD_DOMAIN_VDDSDIO,ESP_PD_OPTION_ON);

Deep-sleep 模式下的 GPIO 唤醒

除了 Light-sleep 模式下的 GPIO 唤醒之外，ESP32 还支持 Deep-sleep 模式下的 GPIO 唤醒。

该唤醒源由 esp_sleep_enable_gpio_wakeup_on_hp_periph_powerdown() 函数实现，用户可以配置一个或多个 GPIO 管脚以及唤醒电平（高电平或低电平）。只有由 VDD3P3_RTC 电源域供电的 GPIO 管脚才能用作 Deep-sleep GPIO 唤醒源。具体支持的管脚请参考 datasheet > IO 管脚。

备注

该 API 同样适用于外设电源域掉电时的 Light-sleep 模式（参见 CONFIG_PM_POWER_DOWN_PERIPHERAL_IN_LIGHT_SLEEP ）。在这种情况下，应使用此 API 而不是 esp_sleep_enable_gpio_wakeup() ，因为 GPIO 模块在睡眠期间会被断电。

完整示例请参考 system/deep_sleep 。

UART 唤醒（仅适用于 Light-sleep 模式）

当 ESP32 从外部设备接收 UART 输入时，通常需要在输入数据可用时唤醒芯片。UART 外设支持多种唤醒模式，可以将芯片从 Light-sleep 模式中唤醒。唤醒模式及其参数可以通过调用 uart_wakeup_setup() 函数进行配置。

UART 唤醒支持以下模式：

模式 0 (UART_WK_MODE_ACTIVE_THRESH) - 边沿阈值唤醒

当所有时钟都关闭时，此时可以通过使 RXD 翻转若干周期，当上升沿个数大于等于设定阈值时唤醒芯片。阈值可以通过 uart_wakeup_cfg_t 结构体中的 rx_edge_threshold 字段进行配置。

可调用 esp_sleep_enable_uart_wakeup() 函数来启用此唤醒源。

使用 UART 唤醒模式 0 之后，需要通过在 Active 模式下向 UART 传输数据或是复位整个 UART 模块，否则下一次唤醒所需的上升沿个数将减少。

禁用睡眠模式唤醒源

调用 API esp_sleep_disable_wakeup_source() 可以禁用给定唤醒源的触发器，从而禁用该唤醒源。此外，如果将参数设置为 ESP_SLEEP_WAKEUP_ALL ，该函数可用于禁用所有触发器。

断电选项

应用程序可以使用 API esp_sleep_pd_config() 强制 RTC 外设和 RTC 内存进入特定断电模式。在 Deep-sleep 模式下，你还可以通过隔离一些 IO 来进一步降低功耗。

RTC 外设和内存断电

默认情况下，调用函数 esp_deep_sleep_start() 和 esp_light_sleep_start() 后，所有唤醒源不需要的 RTC 电源域都会被断电。可调用函数 esp_sleep_pd_config() 来修改这一设置。

注意：在 ESP32 修订版 1 中，RTC 高速内存在 Deep-sleep 期间将总是保持使能，以保证复位后可运行 Deep-sleep stub。如果应用程序在 Deep-sleep 模式后无需复位，你也可以对其进行修改。

如果程序中的某些值被放入 RTC 低速内存中（例如使用 RTC_DATA_ATTR 属性），RTC 低速内存将默认保持供电。如果有需要，也可以使用函数 esp_sleep_pd_config() 对其进行修改。

SPI Flash 进入 deep power-down 模式

为降低 Light-sleep 期间 SPI Flash 的功耗，ESP-IDF 优先推荐**采用 **Deep Power-Down（DPD） ：通过启用配置项 CONFIG_ESP_SLEEP_SET_FLASH_DPD ，令 SPI Flash 在供电保持开启的前提下进入器件内部的深度休眠指令状态。多数 SPI Flash 在 DPD 下电流可降至极低水平（常低于 1 µA），同时可避免反复上下电带来的唤醒延迟。

在几乎所有应用场景中，相较彻底切断 SPI Flash 供电，DPD 在安全性与功耗之间通常是更好的折中。

备注

两种方式互斥： Light-sleep 下的 SPI Flash 断电**（:menuitem:`CONFIG_ESP_SLEEP_POWER_DOWN_FLASH` 或通过 ``esp_sleep_pd_config`` 将 ``ESP_PD_DOMAIN_VDDSDIO`` 置为关闭）与 **DPD 不可同时使用 ， 在 menuconfig 中仅能在禁用 CONFIG_ESP_SLEEP_POWER_DOWN_FLASH 后再启用 CONFIG_ESP_SLEEP_SET_FLASH_DPD 。

警告

使用该功能前需要查阅使用芯片所搭载的 SPI Flash 的技术手册是否支持 deep power-down 模式。

SPI Flash 断电

默认情况下，调用函数 esp_light_sleep_start() 后，SPI Flash 不会 断电，因为在 sleep 过程中断电 SPI Flash 存在风险。具体而言，SPI Flash 断电需要时间，但是在此期间，系统有可能被唤醒，导致 SPI Flash 重新被上电。此时，断电尚未完成又重新上电的硬件行为有可能导致 SPI Flash 无法正常工作。

理论上讲，在 SPI Flash 完全断电后可以仅唤醒系统，然而现实情况是 SPI Flash 断电所需的时间很难预测。如果用户为 SPI Flash 供电电路添加了滤波电容，断电所需时间可能会更长。此外，即使可以预知 SPI Flash 彻底断电所需的时间，有时也不能通过设置足够长的睡眠时间来确保 SPI Flash 断电的安全（比如，突发的异步唤醒源会使得实际的睡眠时间不可控）。

警告

如果在 SPI Flash 的供电电路上添加了滤波电容，那么应当尽一切可能避免 SPI Flash 断电。

因为这些不可控的因素，ESP-IDF 很难保证 SPI Flash 断电的绝对安全。因此 ESP-IDF 不推荐用户断电 SPI Flash。对于一些功耗敏感型应用，可以通过设置 Kconfig 配置项 CONFIG_ESP_SLEEP_FLASH_LEAKAGE_WORKAROUND 来减少 Light-sleep 期间 SPI Flash 的功耗。这种方式在几乎所有场景下都要比断电 SPI Flash 更好，兼顾了安全性和功耗。

值得一提的是，PSRAM 也有一个类似的 Kconfig 配置项 CONFIG_ESP_SLEEP_PSRAM_LEAKAGE_WORKAROUND 。

考虑到有些用户能够充分评估断电 SPI Flash 的风险，并希望通过断电 SPI Flash 来获得更低的功耗，因此 ESP-IDF 提供了两种断电 SPI Flash 的机制：

设置 Kconfig 配置项 CONFIG_ESP_SLEEP_POWER_DOWN_FLASH 将使 ESP-IDF 以一个严格的条件来断电 SPI Flash。严格的条件具体指的是，RTC timer 是唯一的唤醒源 且 睡眠时间比 SPI Flash 彻底断电所需时间更长。

调用函数 esp_sleep_pd_config(ESP_PD_DOMAIN_VDDSDIO, ESP_PD_OPTION_OFF) 将使 ESP-IDF 以一个宽松的条件来断电 SPI Flash。宽松的条件具体指的是 RTC timer 唤醒源未被使能 或 睡眠时间比 SPI Flash 彻底断电所需时间更长。

备注

Light-sleep 模式下，ESP-IDF 没有提供保证 SPI Flash 一定会被断电的机制。

不管用户的配置如何，函数 esp_deep_sleep_start() 都会强制断电 SPI Flash

SPI Flash 休眠策略选择建议

在休眠场景下，SPI Flash 的处理方式直接影响系统的安全性、功耗。不同应用场景对这些因素的侧重不同，因此需要选择合适的 SPI Flash 休眠策略。

SPI Flash 不掉电

不同 SPI Flash 的待机功耗不一致，在 ESP 系列芯片中，SPI Flash 的待机功耗通常低于 30 µA，在以下场景中，建议保持 SPI Flash 不掉电：

系统对稳定性要求极高，无法接受 SPI Flash 掉电带来的任何潜在风险。

休眠时间较短或不可预测，例如存在异步唤醒源（GPIO、UART 等）。

SPI Flash 供电电路中存在较大的滤波电容，导致 SPI Flash 实际断电时间难以估计。

在上述情况下，保持 SPI Flash 供电是最保守、也是最安全的选择，但需要注意其待机功耗相对较高 (约 10-30 µA)。

SPI Flash 进入 deep power-down（DPD）模式

若待机功耗仍偏高，应优先采用 Deep Power-Down（DPD） ，通过 CONFIG_ESP_SLEEP_SET_FLASH_DPD 降低休眠电流；功耗数据、时序及启用方式参见前文 SPI Flash 进入 deep power-down 模式 。

DPD 模式适用于以下场景：

需要显著降低休眠期间 SPI Flash 的功耗，但又希望避免 SPI Flash 重新上电的风险。

休眠时间较短或不可预测，例如存在异步唤醒源（GPIO、UART 等）。

使用的 SPI Flash 芯片明确支持 Deep Power-Down 模式。

SPI Flash 掉电

可以参考 SPI Flash 断电 实现在休眠中掉电 SPI Flash。在以下条件满足或经过充分评估后，可以考虑该策略：

应用对极低功耗有严格要求。

唤醒源可控，通常仅启用 RTC timer 唤醒源。

能够确保实际睡眠时间大于 SPI Flash 彻底断电所需时间。对于 ESP 系列芯片，SPI Flash 彻底断电所需时间可能大于 300ms。如果 SPI Flash 供电电路中存在并联电容，可能需要更长的睡眠时间。

如果休眠时间过短，SPI Flash 上电和下电过程所消耗的功耗可能会超过保持供电时的功耗。

对 SPI Flash 供电及 IO 状态有充分控制，休眠时避免因为管脚上拉导致 SPI Flash 漏电。

由于 SPI Flash 的断电过程受硬件设计、IO 阻抗特性、供电以及环境因素影响较大，ESP-IDF 无法保证在 Light-sleep 模式下 SPI Flash 一定能够安全断电，因此该方式仅适用于风险可控且经过充分验证的场景。

配置 IO（仅适用于 Deep-sleep）

一些 ESP32 IO 在默认情况下启用内部上拉或下拉电阻。如果这些管脚在 Deep-sleep 模式下中受外部电路驱动，电流流经这些上下拉电阻时，可能会增加电流消耗。

想要隔离这些管脚以避免额外的电流消耗，请调用 rtc_gpio_isolate() 函数。

例如，在 ESP32-WROVER 模组上，GPIO12 在外部上拉，但其在 ESP32 芯片中也有内部下拉。这意味着在 Deep-sleep 模式中，电流会流经这些外部和内部电阻，使电流消耗超出可能的最小值。

在函数 esp_deep_sleep_start() 前增加以下代码即可避免额外电流消耗:

rtc_gpio_isolate(GPIO_NUM_12);

进入睡眠模式

应用程序通过 API esp_light_sleep_start() 或 esp_deep_sleep_start() 进入 Light-sleep 或 Deep-sleep 模式。此时，系统将按照被请求的唤醒源和断电选项配置有关的 RTC 控制器参数。

允许在未配置唤醒源的情况下进入睡眠模式。在此情况下，芯片将一直处于睡眠模式，直到从外部被复位。

备注

睡眠流程会禁用 cache，因此请求睡眠的任务其任务栈必须位于内部内存（DRAM 或 RTC fast memory）。如果任务栈位于 PSRAM 的任务请求 Light-sleep 或 Deep-sleep，将被拒绝并返回错误。

UART 输出处理

进入睡眠前，睡眠流程会对**控制台 UART**（用于调试输出的 UART，由 CONFIG_ESP_CONSOLE_UART_NUM 选定）进行准备，以避免 APB 时钟变化或掉电导致输出乱码或未定义行为。所采用的策略可配置，会影响数据完整性、进入睡眠的时间以及功耗。

默认行为（自动模式）

若不调用 esp_sleep_set_console_uart_handling_mode() ，则采用以下默认策略：

Deep-sleep ：始终等到控制台 UART FIFO 中的数据全部发完后再进入睡眠，确保所有调试输出被发送且不丢数据。

Light-sleep ：行为取决于 UART 所在电源域是否掉电：

若 UART 保持供电（例如 HP 外设域未掉电）：在当前帧发完后挂起 UART 输出；唤醒后恢复发送，睡眠前 UART TX FIFO 中剩余数据会继续发出。

若 UART 电源域掉电：睡眠流程会等到控制台 UART TX FIFO 中的数据全部发完后再进入睡眠；其他 UART 中的数据会被丢弃以更快进入睡眠。

配置控制台 UART 处理方式

可通过调用 esp_sleep_set_console_uart_handling_mode() 覆盖默认行为，并选择下列模式之一（参见 esp_sleep_uart_handling_mode_t ）：

ESP_SLEEP_AUTO_FLUSH_SUSPEND_UART （默认）：根据睡眠类型和电源域自动选择冲刷或挂起，如上所述。

ESP_SLEEP_ALWAYS_FLUSH_UART ：进入睡眠前始终等待控制台 UART TX FIFO 中的数据全部发送完毕。适用于必须保证所有调试输出可见的场景；进入睡眠时间会更长，芯片处于 Active 状态的时间变长进而增加功耗。

ESP_SLEEP_ALWAYS_SUSPEND_UART ：等待当前 UART 帧发完后挂起 UART。若 Light-sleep 期间 UART 保持供电，唤醒后会继续发送；若 UART 电源域掉电，未发送的数据将丢失。

ESP_SLEEP_ALWAYS_DISCARD_UART ：丢弃控制台 UART FIFO 中所有未发送数据并立即进入睡眠。适用于追求最快进入睡眠和最低功耗、且可接受丢弃调试输出的场景。

ESP_SLEEP_NO_HANDLING ：进入睡眠前不对控制台 UART 做任何处理。仅在确认 UART 状态安全时使用（例如无待发数据或已禁用控制台 UART）。

备注

睡眠流程在临界区中执行，当使用会冲刷控制台 UART 的模式（如 ESP_SLEEP_ALWAYS_FLUSH_UART ，或 HP 外设域掉电时的 Light-sleep/Deep-sleep 默认行为）时，请将 CONFIG_ESP_INT_WDT_TIMEOUT_MS 配置为**大于** SOC_UART_FIFO_LEN ×（当前波特率下发送一个字符所需时间）。否则若 TX FIFO 中积压数据过多，冲刷时间可能超过中断看门狗超时，会在进入睡眠过程中触发看门狗复位。

示例：在每次睡眠前确保所有调试输出已发出：:

fflush(stdout);esp_sleep_set_console_uart_handling_mode(ESP_SLEEP_ALWAYS_FLUSH_UART);esp_light_sleep_start();

示例：尽量缩短进入睡眠时间并允许丢弃控制台输出：:

esp_sleep_set_console_uart_handling_mode(ESP_SLEEP_ALWAYS_DISCARD_UART);esp_deep_sleep_start();

检查睡眠唤醒原因

esp_sleep_get_wakeup_cause() 函数可用于检测是何种唤醒源在睡眠期间被触发。

对于触摸传感器唤醒源，可以调用函数 esp_sleep_get_touchpad_wakeup_status() 来确认触发唤醒的触摸管脚。

对于 ext1 唤醒源，可以调用函数 esp_sleep_get_ext1_wakeup_status() 来确认触发唤醒的 GPIO 管脚。

应用程序示例

protocols/sntp 演示如何实现 Deep-sleep 模式的基本功能，周期性唤醒 ESP 模块，以从 NTP 服务器获取时间。

wifi/power_save 演示如何通过 Wi-Fi Modem-sleep 模式和自动 Light-sleep 模式保持 Wi-Fi 连接。

bluetooth/nimble/power_save 演示如何通过 Bluetooth Modem-sleep 模式和自动 Light-sleep 模式保持 Bluetooth 连接。

system/deep_sleep 演示如何使用 Deep-sleep 唤醒触发器和 ULP 协处理器编程。

system/light_sleep 演示如何使用 ESP32 的唤醒源，如定时器，GPIO 等，触发 Light-sleep 唤醒。

peripherals/touch_sensor/touch_sens_sleep 演示如何使用触摸传感器唤醒 Light-sleep 或 Deep-sleep。

API 参考

Header File

components/esp_hw_support/include/esp_sleep.h

This header file can be included with:

#include"esp_sleep.h"

Functions

esp_err_t esp_sleep_disable_wakeup_source ( esp_sleep_source_t source )

Disable wakeup source.

This function is used to deactivate wake up trigger for source defined as parameter of the function.

See docs/sleep-modes.rst for details.

备注

This function does not modify wake up configuration in RTC. It will be performed in esp_deep_sleep_start/esp_light_sleep_start function.

参数 :

source -- - number of source to disable of type esp_sleep_source_t

返回 :

ESP_OK on success

ESP_ERR_INVALID_STATE if trigger was not active

esp_err_t esp_sleep_enable_ulp_wakeup ( void )

Enable wakeup by ULP coprocessor.

备注

On ESP32, ULP wakeup source cannot be used when RTC_PERIPH power domain is forced, to be powered on (ESP_PD_OPTION_ON) or when ext0 wakeup source is used.

返回 :

ESP_OK on success

ESP_ERR_NOT_SUPPORTED if additional current by touch (CONFIG_RTC_EXT_CRYST_ADDIT_CURRENT) is enabled.

ESP_ERR_INVALID_STATE if ULP co-processor is not enabled or if wakeup triggers conflict

esp_err_t esp_sleep_enable_timer_wakeup ( uint64_t time_in_us )

Enable wakeup by timer.

备注

The valid time_in_us value depends on the bit width of the lp_timer/rtc_timer counter and the current slow clock source selection (Refer RTC clock source configuration in menuconfig). Valid values should be positive values less than RTC slow clock period * (2 ^ RTC timer bitwidth).

参数 :

time_in_us -- time before wakeup, in microseconds

返回 :

ESP_OK on success

ESP_ERR_INVALID_ARG if value is out of range.

esp_err_t esp_sleep_enable_touchpad_wakeup ( void )

Enable wakeup by touch sensor.

备注

On ESP32, touch wakeup source can not be used when RTC_PERIPH power domain is forced to be powered on (ESP_PD_OPTION_ON) or when ext0 wakeup source is used.

备注

The FSM mode of the touch button should be configured as the timer trigger mode.

返回 :

ESP_OK on success

ESP_ERR_NOT_SUPPORTED if additional current by touch (CONFIG_RTC_EXT_CRYST_ADDIT_CURRENT) is enabled.

ESP_ERR_INVALID_STATE if wakeup triggers conflict

int esp_sleep_get_touchpad_wakeup_status ( void )

Get the touch pad which caused wakeup.

If wakeup was caused by another source, this function will return TOUCH_PAD_MAX;

返回 :

touch pad which caused wakeup

bool esp_sleep_is_valid_wakeup_gpio ( gpio_num_t gpio_num )

Returns true if a GPIO number is valid for use as wakeup source.

备注

For SoCs with RTC IO capability, this can be any valid RTC IO input pin.

参数 :

gpio_num -- Number of the GPIO to test for wakeup source capability

返回 :

True if this GPIO number will be accepted as a sleep wakeup source.

esp_err_t esp_sleep_enable_ext0_wakeup ( gpio_num_t gpio_num , int level )

Enable wakeup using a pin.

This function uses external wakeup feature of RTC_IO peripheral. It will work only if RTC peripherals are kept on during sleep.

This feature can monitor any pin which is an RTC IO. Once the pin transitions into the state given by level argument, the chip will be woken up.

备注

This function does not modify pin configuration. The pin is configured in esp_deep_sleep_start/esp_light_sleep_start, immediately before entering sleep mode.

备注

ESP32: ext0 wakeup source can not be used together with touch or ULP wakeup sources.

参数 :

gpio_num -- GPIO number used as wakeup source. Only GPIOs with the RTC functionality can be used. For different SoCs, the related GPIOs are:

ESP32: 0, 2, 4, 12-15, 25-27, 32-39;

ESP32-S2: 0-21;

ESP32-S3: 0-21.

level -- input level which will trigger wakeup (0=low, 1=high)

返回 :

ESP_OK on success

ESP_ERR_INVALID_ARG if the selected GPIO is not an RTC GPIO, or the mode is invalid

ESP_ERR_INVALID_STATE if wakeup triggers conflict

esp_err_t esp_sleep_enable_ext1_wakeup ( uint64_t io_mask , esp_sleep_ext1_wakeup_mode_t level_mode )

Enable wakeup using multiple pins.

This function uses external wakeup feature of RTC controller. It will work even if RTC peripherals are shut down during sleep.

This feature can monitor any number of pins which are in RTC IOs. Once selected pins go into the state given by level_mode argument, the chip will be woken up.

备注

This function does not modify pin configuration. The pins are configured in esp_deep_sleep_start/esp_light_sleep_start, immediately before entering sleep mode.

备注

Internal pullups and pulldowns don't work when RTC peripherals are shut down. In this case, external resistors need to be added. Alternatively, RTC peripherals (and pullups/pulldowns) may be kept enabled using esp_sleep_pd_config function. If we turn off the RTC_PERIPH domain or certain chips lack the RTC_PERIPH domain, we will use the HOLD feature to maintain the pull-up and pull-down on the pins during sleep. HOLD feature will be acted on the pin internally before the system entering sleep, and this can further reduce power consumption.

备注

Call this func will reset the previous ext1 configuration.

备注

This function will be deprecated in release/v6.0. Please switch to use esp_sleep_enable_ext1_wakeup_io and esp_sleep_disable_ext1_wakeup_io

备注

On ESP32-H2, although GPIO7 is an RTC GPIO, it is not led out for external wakeup.

参数 :

io_mask -- Bit mask of GPIO numbers which will cause wakeup. Only GPIOs which have RTC functionality can be used in this bit map. For different SoCs, the related GPIOs are:

ESP32: 0, 2, 4, 12-15, 25-27, 32-39

ESP32-S2: 0-21

ESP32-S3: 0-21

ESP32-C6: 0-7

ESP32-H2: 7-14

level_mode -- Select logic function used to determine wakeup condition:

When target chip is ESP32:

ESP_EXT1_WAKEUP_ALL_LOW: wake up when all selected GPIOs are low

ESP_EXT1_WAKEUP_ANY_HIGH: wake up when any of the selected GPIOs is high

When target chip is ESP32-S2, ESP32-S3, ESP32-C6 or ESP32-H2:

ESP_EXT1_WAKEUP_ANY_LOW: wake up when any of the selected GPIOs is low

ESP_EXT1_WAKEUP_ANY_HIGH: wake up when any of the selected GPIOs is high

返回 :

ESP_OK on success

ESP_ERR_INVALID_ARG if io_mask is zero, or mode is invalid

esp_err_t esp_sleep_enable_ext1_wakeup_io ( uint64_t io_mask , esp_sleep_ext1_wakeup_mode_t level_mode )

Enable ext1 wakeup pins with IO masks.

This will append selected IOs to the wakeup IOs, it will not reset previously enabled IOs. To reset specific previously enabled IOs, call esp_sleep_disable_ext1_wakeup_io with the io_mask. To reset all the enabled IOs, call esp_sleep_disable_ext1_wakeup_io(0).

This function uses external wakeup feature of RTC controller. It will work even if RTC peripherals are shut down during sleep.

This feature can monitor any number of pins which are in RTC IOs. Once selected pins go into the state given by level_mode argument, the chip will be woken up.

备注

This function does not modify pin configuration. The pins are configured in esp_deep_sleep_start/esp_light_sleep_start, immediately before entering sleep mode.

备注

Internal pullups and pulldowns don't work when RTC peripherals are shut down. In this case, external resistors need to be added. Alternatively, RTC peripherals (and pullups/pulldowns) may be kept enabled using esp_sleep_pd_config function. If we turn off the RTC_PERIPH domain or certain chips lack the RTC_PERIPH domain, we will use the HOLD feature to maintain the pull-up and pull-down on the pins during sleep. HOLD feature will be acted on the pin internally before the system entering sleep, and this can further reduce power consumption.

备注

On ESP32-H2, although GPIO7 is an RTC GPIO, it is not led out for external wakeup.

参数 :

io_mask -- Bit mask of GPIO numbers which will cause wakeup. Only GPIOs which have RTC functionality can be used in this bit map. For different SoCs, the related GPIOs are:

ESP32: 0, 2, 4, 12-15, 25-27, 32-39

ESP32-S2: 0-21

ESP32-S3: 0-21

ESP32-C6: 0-7

ESP32-H2: 7-14

level_mode -- Select logic function used to determine wakeup condition:

When target chip is ESP32:

ESP_EXT1_WAKEUP_ALL_LOW: wake up when all selected GPIOs are low

ESP_EXT1_WAKEUP_ANY_HIGH: wake up when any of the selected GPIOs is high

When target chip is ESP32-S2, ESP32-S3, ESP32-C6 or ESP32-H2:

ESP_EXT1_WAKEUP_ANY_LOW: wake up when any of the selected GPIOs is low

ESP_EXT1_WAKEUP_ANY_HIGH: wake up when any of the selected GPIOs is high

返回 :

ESP_OK on success

ESP_ERR_INVALID_ARG if any of the selected GPIOs is not an RTC GPIO, or mode is invalid

ESP_ERR_NOT_ALLOWED when wakeup level will become different between ext1 IOs if !SOC_PM_SUPPORT_EXT1_WAKEUP_MODE_PER_PIN

esp_err_t esp_sleep_disable_ext1_wakeup_io ( uint64_t io_mask )

Disable ext1 wakeup pins with IO masks. This will remove selected IOs from the wakeup IOs.

备注

On ESP32-H2, although GPIO7 is an RTC GPIO, it is not led out for external wakeup.

参数 :

io_mask -- Bit mask of GPIO numbers which will cause wakeup. Only GPIOs which have RTC functionality can be used in this bit map. If value is zero, this func will remove all previous ext1 configuration. For different SoCs, the related GPIOs are:

ESP32: 0, 2, 4, 12-15, 25-27, 32-39

ESP32-S2: 0-21

ESP32-S3: 0-21

ESP32-C6: 0-7

ESP32-H2: 7-14

返回 :

ESP_OK on success

ESP_ERR_INVALID_ARG if any of the selected GPIOs is not an RTC GPIO.

esp_err_t esp_sleep_enable_gpio_wakeup_on_hp_periph_powerdown ( uint64_t gpio_pin_mask , esp_sleep_gpio_wake_up_mode_t mode )

Enable wakeup using specific gpio pins.

This function enables an IO pin to wake up the chip from peripheral powerdowned sleep. (including deepsleep and peripheral powerdowned lightsleep).

备注

1.This function does not modify pin configuration. The pins are configured inside esp_sleep_start , immediately before entering sleep mode. 2.This function is also applicable to waking up the lightsleep when the peripheral power domain is powered off, see PM_POWER_DOWN_PERIPHERAL_IN_LIGHT_SLEEP in menuconfig.

备注

You don't need to worry about pull-up or pull-down resistors before using this function because the ESP_SLEEP_GPIO_ENABLE_INTERNAL_RESISTORS option is enabled by default. It will automatically set pull-up or pull-down resistors internally in esp_deep_sleep_start based on the wakeup mode. However, when using external pull-up or pull-down resistors, please be sure to disable the ESP_SLEEP_GPIO_ENABLE_INTERNAL_RESISTORS option, as the combination of internal and external resistors may cause interference. BTW, when you use low level to wake up the chip, we strongly recommend you to add external resistors (pull-up).

备注

The wakeup signal must be held (level mode) or have a pulse width (edge mode) of at least 3 RTC slow-clock cycles to be reliably sampled by the wakeup logic. The duration of one slow-clock cycle depends on CONFIG_RTC_CLK_SRC (e.g. RC_SLOW @ ~136 kHz ~= 7.4 us/cycle, XTAL32K @ 32.768 kHz ~= 30.5 us/cycle).

参数 :

gpio_pin_mask -- Bit mask of GPIO numbers which will cause wakeup. Only GPIOs which have RTC functionality (pads that powered by VDD3P3_RTC) can be used in this bit map.

mode -- Wakeup condition, see esp_sleep_gpio_wake_up_mode_t.

返回 :

ESP_OK on success

ESP_ERR_INVALID_ARG if the mask contains any invalid wakeup pin or wakeup mode is invalid

esp_err_t esp_sleep_enable_gpio_wakeup ( void )

Enable wakeup from light sleep using GPIOs.

Each GPIO supports wakeup function, which can be triggered on either low level or high level. This method can be used with any IO (RTC or digital), whereas external RTC wakeup is limited to RTC GPIOs. It can only be used to wakeup from light sleep though.

To enable wakeup, first call gpio_wakeup_enable, specifying gpio number and wakeup level, for each GPIO which is used for wakeup. Then call this function to enable wakeup feature.

备注

1. On ESP32, GPIO wakeup source can not be used together with touch or ULP wakeup sources.

If PM_POWER_DOWN_PERIPHERAL_IN_LIGHT_SLEEP is enabled (if target supported), this API is unavailable since the GPIO module is powered down during sleep. You can use esp_sleep_enable_gpio_wakeup_on_hp_periph_powerdown instead, or use EXT1 wakeup source by esp_sleep_enable_ext1_wakeup_io to achieve the same function. (Only GPIOs which have RTC functionality can be used)

返回 :

ESP_OK on success

ESP_ERR_INVALID_STATE if wakeup triggers conflict

esp_err_t esp_sleep_enable_uart_wakeup ( int uart_num )

Enable wakeup from light sleep using UART.

Use uart_wakeup_setup function to configure UART wakeup mode and parameters.

Wakeup from light sleep takes some time, so not every character sent to the UART can be received by the application.

备注

1. ESP32 does not support wakeup from UART2.

Wakeup mode 0(Active threshold) don't need source clock, but other modes need.

If PM_POWER_DOWN_PERIPHERAL_IN_LIGHT_SLEEP is enabled (if target supported), this API is unavailable since the UART module is powered down during sleep.

参数 :

uart_num -- UART port to wake up from

返回 :

ESP_OK on success

ESP_ERR_INVALID_ARG if wakeup from given UART is not supported

esp_err_t esp_sleep_enable_bt_wakeup ( void )

Enable wakeup by bluetooth.

返回 :

ESP_OK on success

ESP_ERR_NOT_SUPPORTED if wakeup from bluetooth is not supported

esp_err_t esp_sleep_disable_bt_wakeup ( void )

Disable wakeup by bluetooth.

返回 :

ESP_OK on success

ESP_ERR_NOT_SUPPORTED if wakeup from bluetooth is not supported

esp_err_t esp_sleep_enable_usb_wakeup ( void )

Enable wakeup by High-Speed USB-OTG.

返回 :

ESP_OK on success

ESP_ERR_NOT_SUPPORTED if wakeup from USB is not supported

esp_err_t esp_sleep_disable_usb_wakeup ( void )

Disable wakeup by High-Speed USB-OTG.

返回 :

ESP_OK on success

ESP_ERR_NOT_SUPPORTED if wakeup from USB is not supported

esp_err_t esp_sleep_enable_wifi_wakeup ( void )

Enable wakeup by WiFi MAC.

返回 :

ESP_OK on success

esp_err_t esp_sleep_disable_wifi_wakeup ( void )

Disable wakeup by WiFi MAC.

返回 :

ESP_OK on success

esp_err_t esp_sleep_enable_wifi_beacon_wakeup ( void )

Enable beacon wakeup by WiFi MAC, it will wake up the system into modem state.

返回 :

ESP_OK on success

esp_err_t esp_sleep_disable_wifi_beacon_wakeup ( void )

Disable beacon wakeup by WiFi MAC.

返回 :

ESP_OK on success

uint64_t esp_sleep_get_ext1_wakeup_status ( void )

Get the bit mask of GPIOs which caused wakeup (ext1)

If wakeup was caused by another source, this function will return 0.

返回 :

bit mask, if GPIOn caused wakeup, BIT(n) will be set

uint64_t esp_sleep_get_gpio_wakeup_status ( void )

Get the bit mask of RTC IO which caused wakeup (GPIO wakeup source).

If wakeup was caused by another source, this function will return 0. Each bit corresponds to an RTC IO. Use esp_sleep_wakeup_io_bit2num() to convert a bit index to GPIO number.

返回 :

bit mask of RTC IO that caused wakeup

gpio_num_t esp_sleep_wakeup_io_bit2num ( uint32_t bit )

Convert RTC IO status bit index to GPIO number.

Used to interpret the bit mask returned by esp_sleep_get_gpio_wakeup_status().

参数 :

bit -- RTC IO bit index (0 to SOC_RTCIO_PIN_COUNT-1).

返回 :

GPIO number, or GPIO_NUM_NC if bit is invalid or has no corresponding GPIO.

esp_err_t esp_sleep_pd_config ( esp_sleep_pd_domain_t domain , esp_sleep_pd_option_t option )

Configure power domain options for sleep mode.

This function provides power domain management for sleep mode, allowing users to control which power domains remain active during sleep to maintain required functionality. The function supports:

Automatic power management (ESP_PD_OPTION_AUTO): Power domains are controlled automatically based on system requirements and other peripheral usage.

Manual power control (ESP_PD_OPTION_ON/ESP_PD_OPTION_OFF): User can force specific power domains to stay on or off during sleep.

The management strategy uses reference counting when in manual mode, allowing multiple subsystems to request and release power domain resources safely without interfering with each other. Power domains will only change state when all users have released their requirements.

参数 :

domain -- power domain to configure

option -- power down option (ESP_PD_OPTION_OFF, ESP_PD_OPTION_ON, or ESP_PD_OPTION_AUTO)

返回 :

ESP_OK on success

ESP_ERR_INVALID_ARG if either of the arguments is out of range

esp_err_t esp_deep_sleep_try_to_start ( void )

Enter deep sleep with the configured wakeup options.

The reason for the rejection can be such as a short sleep time.

备注

In general, the function does not return, but if the sleep is rejected, then it returns from it.

返回 :

No return - If the sleep is not rejected.

ESP_ERR_NOT_ALLOWED Since the sleep process disables the cache, the task requesting to enter sleep must have its stack located in internal RAM. Tasks with their stacks in PSRAM are not allowed to request sleep.

ESP_ERR_INVALID_STATE VBAT power does not meet the requirements for entering deepsleep

ESP_ERR_SLEEP_REJECT sleep request is rejected(wakeup source set before the sleep request)

void esp_deep_sleep_start ( void )

Enter deep sleep with the configured wakeup options.

备注

The function does not do a return (no rejection). Even if wakeup source set before the sleep request it goes to deep sleep anyway.

esp_err_t esp_light_sleep_start ( void )

Enter light sleep with the configured wakeup options.

返回 :

ESP_OK on success (returned after wakeup)

ESP_ERR_NOT_ALLOWED Since the sleep process disables the cache, the task requesting to enter sleep must have its stack located in internal RAM. Tasks with their stacks in PSRAM are not allowed to request sleep.

ESP_ERR_SLEEP_REJECT sleep request is rejected(wakeup source set before the sleep request)

ESP_ERR_SLEEP_TOO_SHORT_SLEEP_DURATION after deducting the sleep flow overhead, the final sleep duration is too short to cover the minimum sleep duration of the chip, when rtc timer wakeup source enabled

esp_err_t esp_deep_sleep_try ( uint64_t time_in_us )

Enter deep-sleep mode.

The device will automatically wake up after the deep-sleep time Upon waking up, the device calls deep sleep wake stub, and then proceeds to load application.

Call to this function is equivalent to a call to esp_deep_sleep_enable_timer_wakeup followed by a call to esp_deep_sleep_start.

The reason for the rejection can be such as a short sleep time.

备注

In general, the function does not return, but if the sleep is rejected, then it returns from it.

参数 :

time_in_us -- deep-sleep time, unit: microsecond

返回 :

No return - If the sleep is not rejected.

ESP_ERR_SLEEP_REJECT sleep request is rejected(wakeup source set before the sleep request)

void esp_deep_sleep ( uint64_t time_in_us )

Enter deep-sleep mode.

The device will automatically wake up after the deep-sleep time Upon waking up, the device calls deep sleep wake stub, and then proceeds to load application.

Call to this function is equivalent to a call to esp_deep_sleep_enable_timer_wakeup followed by a call to esp_deep_sleep_start.

备注

The function does not do a return (no rejection).. Even if wakeup source set before the sleep request it goes to deep sleep anyway.

参数 :

time_in_us -- deep-sleep time, unit: microsecond

esp_err_t esp_deep_sleep_register_hook ( esp_deep_sleep_cb_t new_dslp_cb )

Register a callback to be called from the deep sleep prepare.

警告

deepsleep callbacks should without parameters, and MUST NOT, UNDER ANY CIRCUMSTANCES, CALL A FUNCTION THAT MIGHT BLOCK.

参数 :

new_dslp_cb -- Callback to be called

返回 :

ESP_OK: Callback registered to the deepsleep misc_modules_sleep_prepare

ESP_ERR_NO_MEM: No more hook space for register the callback

void esp_deep_sleep_deregister_hook ( esp_deep_sleep_cb_t old_dslp_cb )

Unregister an deepsleep callback.

参数 :

old_dslp_cb -- Callback to be unregistered

esp_sleep_wakeup_cause_t esp_sleep_get_wakeup_cause ( void )

Get the wakeup source which caused wakeup from sleep.

备注

!!! This API will only return one wakeup source. If multiple wakeup sources wake up at the same time, the wakeup source information may be lost.

返回 :

cause of wake up from last sleep (deep sleep or light sleep)

uint32_t esp_sleep_get_wakeup_causes ( void )

Get all wakeup sources bitmap which caused wakeup from sleep.

返回 :

The bitmap of the wakeup sources of the last wakeup from sleep. (deep sleep or light sleep)

void esp_wake_deep_sleep ( void )

Default stub to run on wake from deep sleep.

Allows for executing code immediately on wake from sleep, before the software bootloader or ESP-IDF app has started up.

This function is weak-linked, so you can implement your own version to run code immediately when the chip wakes from sleep.

See docs/deep-sleep-stub.rst for details.

void esp_set_deep_sleep_wake_stub ( esp_deep_sleep_wake_stub_fn_t new_stub )

Install a new stub at runtime to run on wake from deep sleep.

If implementing esp_wake_deep_sleep() then it is not necessary to call this function.

However, it is possible to call this function to substitute a different deep sleep stub. Any function used as a deep sleep stub must be marked RTC_IRAM_ATTR, and must obey the same rules given for esp_wake_deep_sleep().

void esp_set_deep_sleep_wake_stub_default_entry ( void )

Set wake stub entry to default esp_wake_stub_entry

esp_deep_sleep_wake_stub_fn_t esp_get_deep_sleep_wake_stub ( void )

Get current wake from deep sleep stub.

返回 :

Return current wake from deep sleep stub, or NULL if no stub is installed.

void esp_default_wake_deep_sleep ( void )

The default esp-idf-provided esp_wake_deep_sleep() stub.

See docs/deep-sleep-stub.rst for details.

void esp_deep_sleep_disable_rom_logging ( void )

Disable logging from the ROM code after deep sleep.

Using LSB of RTC_STORE4.

esp_err_t esp_sleep_set_console_uart_handling_mode ( esp_sleep_uart_handling_mode_t handling_mode )

Configure how the console UART is handled when entering sleep.

This function configures the handling behavior for the console UART (CONFIG_ESP_CONSOLE_UART_NUM) during sleep modes. The console UART is typically used for debug output, so its handling mode affects whether debug messages are preserved or discarded before sleep.

备注

When CONFIG_ESP_SLEEP_CACHE_SAFE_ASSERTION is enabled, the console UART will always be flushed regardless of the configured mode to ensure debug output is visible even when cache is disabled.

参数 :

handling_mode -- Handling method, one of the following strategies:

ESP_SLEEP_AUTO_FLUSH_SUSPEND_UART (default): Automatically selects the appropriate strategy based on sleep type and power domain:

Deep sleep: Always flush to avoid data loss

Light sleep: Suspend if UART remains powered, flush if UART power domain is powered down

ESP_SLEEP_ALWAYS_FLUSH_UART: Wait for all data in TX FIFO to be fully transmitted before entering sleep. Ensures all debug output is visible but increases sleep entry time and power consumption.

ESP_SLEEP_ALWAYS_SUSPEND_UART: Wait for current UART frame to complete, then suspend the UART state machine. If UART remains powered during light sleep, transmission resumes after wake. If UART power domain is powered down, unsent data will be lost.

ESP_SLEEP_ALWAYS_DISCARD_UART: Discard all unsent data in UART FIFO and enter sleep immediately. Fastest sleep entry and lowest power, but all unsent debug output is lost.

ESP_SLEEP_NO_HANDLING: Do not perform any handling on the console UART before sleep. Can be used to disable the default UART handling behavior.

返回 :

ESP_OK on success

ESP_ERR_INVALID_ARG if handling_mode is not valid

ESP_ERR_NOT_SUPPORTED if no console UART is configured (CONFIG_ESP_CONSOLE_UART_NUM == -1)

void esp_sleep_enable_lowpower_analog_mode ( bool enable )

If analog-related peripherals(ADC, TOUCH) is not used in monitor mode, analog low power mode can be enabled by this API to reduce power consumption in monitor state.

参数 :

enable -- Enable or disable lowpower analog mode

void esp_sleep_config_gpio_isolate ( void )

Configure to isolate all GPIO pins in sleep state.

void esp_sleep_enable_gpio_switch ( bool enable )

Enable or disable GPIO pins status switching between slept status and waked status.

参数 :

enable -- decide whether to switch status or not

Macros

WAKEUP_MODE_2_INT_TYPE ( mode )

ESP_PD_DOMAIN_RTC8M

Type Definitions

typedef void ( * esp_deep_sleep_cb_t ) ( void )

typedef esp_sleep_source_t esp_sleep_wakeup_cause_t

typedef void ( * esp_deep_sleep_wake_stub_fn_t ) ( void )

Function type for stub to run on wake from sleep.

Enumerations

enum esp_sleep_ext1_wakeup_mode_t

Logic function used for EXT1 wakeup mode.

Values:

enumerator ESP_EXT1_WAKEUP_ALL_LOW

Wake the chip when all selected GPIOs go low.

enumerator ESP_EXT1_WAKEUP_ANY_HIGH

Wake the chip when any of the selected GPIOs go high.

enum esp_sleep_gpio_wake_up_mode_t

Values:

enumerator ESP_GPIO_WAKEUP_GPIO_LOW

enumerator ESP_GPIO_WAKEUP_GPIO_HIGH

enum esp_sleep_pd_domain_t

Power domains which can be powered down in sleep mode.

Values:

enumerator ESP_PD_DOMAIN_RTC_PERIPH

RTC IO, sensors and ULP co-processor.

enumerator ESP_PD_DOMAIN_RTC_SLOW_MEM

RTC slow memory.

enumerator ESP_PD_DOMAIN_RTC_FAST_MEM

RTC fast memory.

enumerator ESP_PD_DOMAIN_XTAL

XTAL oscillator.

enumerator ESP_PD_DOMAIN_RC_FAST

Internal Fast oscillator.

enumerator ESP_PD_DOMAIN_VDDSDIO

VDD_SDIO.

enumerator ESP_PD_DOMAIN_MODEM

MODEM, includes WiFi, Bluetooth and IEEE802.15.4.

enumerator ESP_PD_DOMAIN_MAX

Number of domains.

enum esp_sleep_pd_option_t

Power down options.

Values:

enumerator ESP_PD_OPTION_OFF

Power down the power domain in sleep mode.

enumerator ESP_PD_OPTION_ON

Keep power domain enabled during sleep mode.

enumerator ESP_PD_OPTION_AUTO

Keep power domain enabled in sleep mode, if it is needed by one of the wakeup options. Otherwise power it down.

enum esp_sleep_source_t

Sleep wakeup cause.

Values:

enumerator ESP_SLEEP_WAKEUP_UNDEFINED

In case of deep sleep, reset was not caused by exit from deep sleep.

enumerator ESP_SLEEP_WAKEUP_ALL

Not a wakeup cause, used to disable all wakeup sources with esp_sleep_disable_wakeup_source.

enumerator ESP_SLEEP_WAKEUP_EXT0

Wakeup caused by external signal using RTC_IO.

enumerator ESP_SLEEP_WAKEUP_EXT1

Wakeup caused by external signal using RTC_CNTL.

enumerator ESP_SLEEP_WAKEUP_TIMER

Wakeup caused by timer.

enumerator ESP_SLEEP_WAKEUP_TOUCHPAD

Wakeup caused by touchpad.

enumerator ESP_SLEEP_WAKEUP_ULP

Wakeup caused by ULP program.

enumerator ESP_SLEEP_WAKEUP_GPIO

Wakeup caused by GPIO (light sleep only on ESP32, S2 and S3)

enumerator ESP_SLEEP_WAKEUP_UART0

Wakeup caused by UART0 (light sleep only)

enumerator ESP_SLEEP_WAKEUP_UART

enumerator ESP_SLEEP_WAKEUP_UART1

Wakeup caused by UART1 (light sleep only)

enumerator ESP_SLEEP_WAKEUP_WIFI

Wakeup caused by WIFI (light sleep only)

enumerator ESP_SLEEP_WAKEUP_COCPU

Wakeup caused by COCPU int.

enumerator ESP_SLEEP_WAKEUP_COCPU_TRAP_TRIG

Wakeup caused by COCPU crash.

enumerator ESP_SLEEP_WAKEUP_BT

Wakeup caused by BT (light sleep only)

enumerator ESP_SLEEP_WAKEUP_VAD

Wakeup caused by VAD.

enumerator ESP_SLEEP_WAKEUP_VBAT_UNDER_VOLT

Wakeup caused by VDD_BAT under voltage.

enumerator ESP_SLEEP_WAKEUP_USB

Wakeup caused by USB HS (light sleep only)

enum esp_sleep_mode_t

Sleep mode.

Values:

enumerator ESP_SLEEP_MODE_LIGHT_SLEEP

light sleep mode

enumerator ESP_SLEEP_MODE_DEEP_SLEEP

deep sleep mode

enum esp_sleep_uart_handling_mode_t

UART handling mode before entering sleep.

These modes define how UARTs are handled when the chip enters sleep mode. The behavior affects data integrity, power consumption, and sleep entry time.

Values:

enumerator ESP_SLEEP_AUTO_FLUSH_SUSPEND_UART

Automatically select flush or suspend based on sleep type and power domain configuration. For deep sleep, always flush. For light sleep, suspend if UART remains powered, flush/discard if UART power domain is powered down.

enumerator ESP_SLEEP_ALWAYS_FLUSH_UART

Always wait for all data in TX FIFO to be transmitted before sleep. Ensures data integrity but increases power consumption and sleep entry time.

enumerator ESP_SLEEP_ALWAYS_SUSPEND_UART

Suspend UART transmission after current frame completes. If UART remains powered during sleep, transmission resumes after wake. If UART power domain is powered down, unsent data will be lost.

enumerator ESP_SLEEP_ALWAYS_DISCARD_UART

Discard all data in TX/RX FIFOs and enter sleep immediately. Fastest sleep entry and lowest power, but all unsent data is lost.

enumerator ESP_SLEEP_NO_HANDLING

Do not perform any UART handling before sleep. UART state is not modified.

此文档对您有帮助吗？

反馈已收到，谢谢！

如果您有其他意见，欢迎填写 乐鑫文档反馈表 。

我们重视您的反馈。

您可以填写 乐鑫文档反馈表 告诉我们如何改进该文档。
