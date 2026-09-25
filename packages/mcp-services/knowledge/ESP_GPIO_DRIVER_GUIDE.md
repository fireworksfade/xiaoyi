Source: https://docs.espressif.com/projects/esp-idf/zh_CN/latest/esp32/api-reference/peripherals/gpio.html

API 参考

外设 API

GPIO & RTC GPIO

在 GitHub 上编辑

GPIO & RTC GPIO

[English]

GPIO 汇总

ESP32 芯片具有 34 个物理 GPIO 管脚（GPIO0 ~ GPIO19、GPIO21 ~ GPIO23、GPIO25 ~ GPIO27 和 GPIO32 ~ GPIO39）。每个管脚都可用作一个通用 IO，或连接一个内部的外设信号。通过 IO MUX、RTC IO MUX 和 GPIO 交换矩阵，可配置外设模块的输入信号来源于任何的 IO 管脚，并且外设模块的输出信号也可连接到任意 IO 管脚。这些模块共同组成了芯片的 IO 控制。更多详细信息，请参阅 ESP32 技术参考手册 > IO MUX 和 GPIO 矩阵（GPIO、IO_MUX） [ PDF ]。

下表提供了各管脚的详细信息，部分 GPIO 具有特殊的使用限制，具体可参考表中的注释列。

GPIO

模拟功能

RTC GPIO

注释

GPIO0

ADC2_CH1

RTC_GPIO11

GPIO1

TXD

GPIO2

ADC2_CH2

RTC_GPIO12

GPIO3

RXD

GPIO4

ADC2_CH0

RTC_GPIO10

GPIO5

GPIO6

SPI0/1

GPIO7

SPI0/1

GPIO8

SPI0/1

GPIO9

SPI0/1

GPIO10

SPI0/1

GPIO11

SPI0/1

GPIO12

ADC2_CH5

RTC_GPIO15

JTAG

GPIO13

ADC2_CH4

RTC_GPIO14

JTAG

GPIO14

ADC2_CH6

RTC_GPIO16

JTAG

GPIO15

ADC2_CH3

RTC_GPIO13

JTAG

GPIO16

SPI0/1

GPIO17

SPI0/1

GPIO18

GPIO19

GPIO21

GPIO22

GPIO23

GPIO25

ADC2_CH8, DAC0

RTC_GPIO6

GPIO26

ADC2_CH9, DAC1

RTC_GPIO7

GPIO27

ADC2_CH7

RTC_GPIO17

GPIO32

ADC1_CH4

RTC_GPIO9

GPIO33

ADC1_CH5

RTC_GPIO8

GPIO34

ADC1_CH6

RTC_GPIO4

GPI

GPIO35

ADC1_CH7

RTC_GPIO5

GPI

GPIO36

ADC1_CH0

RTC_GPIO0

GPI

GPIO37

ADC1_CH1

RTC_GPIO1

GPI

GPIO38

ADC1_CH2

RTC_GPIO2

GPI

GPIO39

ADC1_CH3

RTC_GPIO3

GPI

备注

Strapping 管脚：部分管脚被用作 Strapping 管脚。更多信息请参阅 ESP32 技术规格书 > 启动配置项 [ PDF ]。

SPI0/1：GPIO6-11 和 GPIO16-17 通常连接到模组内集成的 SPI flash 和 PSRAM，因此不能用于其他用途。

JTAG：GPIO12-15 通常用于在线调试。

GPI：GPIO34-39 只能设置为输入模式，不具备软件使能的上拉或下拉功能。

TXD & RXD 通常用于烧录和调试。

ADC2：使用 Wi-Fi 时不能使用 ADC2 管脚。因此，如果您在使用 Wi-Fi 时无法从 ADC2 GPIO 获取值，可以考虑使用 ADC1 GPIO 来解决该问题。更多详情请参考 ADC 连续转换模式下的硬件限制 以及 ADC 单次转换模式下的硬件限制 。

使用 ADC 或睡眠模式下使用 Wi-Fi 和蓝牙时，请不要使用 GPIO36 和 GPIO39 的中断。有关问题的详细描述，请参考 ESP32 ECO 和 Bug 解决方法 > 中的 GPIO-3.11 节。

当 GPIO 连接到 RTC 低功耗和模拟子系统时，ESP32 芯片还单独支持 RTC GPIO。可在以下情况时使用这些管脚功能：

当 GPIO 连接到 RTC 低功耗、模拟子系统、低功耗外设时，ESP32 芯片还单独支持 RTC GPIO。可在以下情况时使用这些管脚功能：

处于 Deep-sleep 模式时

超低功耗协处理器 (ULP-FSM) 运行时

使用 ADC/DAC 等模拟功能时

IO 管脚配置

IO 可以有两种使用方式：

作为简单的 GPIO 输入读取引脚上的电平，或作为简单的 GPIO 输出以输出所需的电平。

作为外设信号的输入/输出。

IDF 外设驱动内部会处理需要应用到引脚上的必要 IO 配置，以便它们可以用作外设信号的输入或输出。这意味着用户通常自己只需负责将 IO 配置为简单的输入或输出。 gpio_config() 是一个一体化的 API，可用于配置 I/O 模式、内部上拉/下拉电阻等管脚设置，包括那些被 USB PHY 复用的引脚。

在一些应用中，IO 管脚可以同时发挥双重作用。例如，输出 LEDC PWM 信号的 IO 也可以作为 GPIO 输入生成中断或 GPIO ETM 事件。这种双重用途的 IO 管脚在配置时需要特别注意。由于 gpio_config() 是一个会覆盖所有当前配置的 API ，因此必须先调用它将管脚模式设置为 gpio_mode_t::GPIO_MODE_INPUT ，然后才能调用 LEDC 驱动 API 将输出信号连接到引脚上。作为替代方案，如果除了使管脚输入启用之外不需要其他额外配置，可以随时调用 gpio_input_enable() 以实现相同的目的。

获取 IO 管脚实时配置状态

GPIO 驱动提供了一个函数 gpio_dump_io_configuration() 用来输出指定管脚的实时配置状态，包括上下拉、输入输出使能、管脚映射等。例如，以下命令可用于输出 GPIO4，GPIO18 与 GPIO26 的配置状态：

gpio_dump_io_configuration(stdout,(1ULL<<4)|(1ULL<<18)|(1ULL<<26));

其输出信息如下：

================IODUMPStart================IO[4]-Pullup:1,Pulldown:0,DriveCap:2InputEn:1,OutputEn:0,OpenDrain:0FuncSel:1(GPIO)GPIOMatrixSigInID:(simpleGPIOinput)SleepSelEn:1IO[18]-Pullup:0,Pulldown:0,DriveCap:2InputEn:0,OutputEn:1,OpenDrain:0FuncSel:1(GPIO)GPIOMatrixSigOutID:256(simpleGPIOoutput)SleepSelEn:1IO[26]**RESERVED**-Pullup:1,Pulldown:0,DriveCap:2InputEn:1,OutputEn:0,OpenDrain:0FuncSel:0(IOMUX)SleepSelEn:1=================IODUMPEnd==================

如果你想要查看所有管脚的配置状态，可以使用命令

gpio_dump_io_configuration(stdout,SOC_GPIO_VALID_GPIO_MASK);

如果 IO 管脚通过 GPIO 交换矩阵连接到内部外设信号，输出信息打印中的外设信号 ID 定义可以在 soc/esp32/include/soc/gpio_sig_map.h 头文件中查看。 **RESERVED** 字样则表示此 IO 用于连接 SPI flash 或 PSRAM，强烈建议不要重新配置这些管脚用于其他功能。

请不要依赖技术参考手册中记录的 GPIO 默认配置状态，因为特殊用途的 GPIO 可能会在 app_main 之前被引导加载程序或应用程序启动阶段的代码更改。

应用示例

peripherals/gpio/generic_gpio 演示了如何配置 GPIO 以生成脉冲，触发中断。

API 参考 - 普通 GPIO

Header File

components/esp_driver_gpio/include/driver/gpio.h

This header file can be included with:

#include"driver/gpio.h"

This header file is a part of the API provided by the esp_driver_gpio component. To declare that your component depends on esp_driver_gpio , add the following to your CMakeLists.txt:

REQUIRES esp_driver_gpio

or

PRIV_REQUIRES esp_driver_gpio

Functions

esp_err_t gpio_config ( const gpio_config_t * pGPIOConfig )

GPIO common configuration.

ConfigureGPIO's Mode,pull-up,PullDown,IntrType

备注

This function always overwrite all the current IO configurations

参数 :

pGPIOConfig -- Pointer to GPIO configure struct

返回 :

ESP_OK success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_reset_pin ( gpio_num_t gpio_num )

Reset a GPIO to a certain state (select gpio function, enable pullup and disable input and output).

参数 :

gpio_num -- GPIO number.

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_set_intr_type ( gpio_num_t gpio_num , gpio_int_type_t intr_type )

GPIO set interrupt trigger type.

参数 :

gpio_num -- GPIO number. If you want to set the trigger type of e.g. of GPIO16, gpio_num should be GPIO_NUM_16 (16);

intr_type -- Interrupt type, select from gpio_int_type_t

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_intr_enable ( gpio_num_t gpio_num )

Enable GPIO module interrupt signal.

备注

ESP32: Please do not use the interrupt of GPIO36 and GPIO39 when using ADC or Wi-Fi and Bluetooth with sleep mode enabled. Please refer to the comments of adc1_get_raw . Please refer to GPIO-3.11 of ESP32 ECO and Workarounds for Bugs for the description of this issue.

参数 :

gpio_num -- GPIO number. If you want to enable an interrupt on e.g. GPIO16, gpio_num should be GPIO_NUM_16 (16);

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_intr_disable ( gpio_num_t gpio_num )

Disable GPIO module interrupt signal.

备注

This function is allowed to be executed when Cache is disabled within ISR context, by enabling CONFIG_GPIO_CTRL_FUNC_IN_IRAM

参数 :

gpio_num -- GPIO number. If you want to disable the interrupt of e.g. GPIO16, gpio_num should be GPIO_NUM_16 (16);

返回 :

ESP_OK success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_set_level ( gpio_num_t gpio_num , uint32_t level )

GPIO set output level.

备注

This function is allowed to be executed when Cache is disabled within ISR context, by enabling CONFIG_GPIO_CTRL_FUNC_IN_IRAM

参数 :

gpio_num -- GPIO number. If you want to set the output level of e.g. GPIO16, gpio_num should be GPIO_NUM_16 (16);

level -- Output level. 0: low ; 1: high

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG GPIO number error

int gpio_get_level ( gpio_num_t gpio_num )

GPIO get input level.

警告

If the pad is not configured for input (or input and output) the returned value is always 0.

参数 :

gpio_num -- GPIO number. If you want to get the logic level of e.g. pin GPIO16, gpio_num should be GPIO_NUM_16 (16);

返回 :

0 the GPIO input level is 0

1 the GPIO input level is 1

esp_err_t gpio_set_direction ( gpio_num_t gpio_num , gpio_mode_t mode )

GPIO set direction.

Configure GPIO mode,such as output_only,input_only,output_and_input

备注

This function always overwrite all the current modes that have applied on the IO pin

参数 :

gpio_num -- Configure GPIO pins number, it should be GPIO number. If you want to set direction of e.g. GPIO16, gpio_num should be GPIO_NUM_16 (16);

mode -- GPIO direction

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG GPIO error

esp_err_t gpio_input_enable ( gpio_num_t gpio_num )

Enable input for an IO.

参数 :

gpio_num -- GPIO number

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG GPIO number error

esp_err_t gpio_set_pull_mode ( gpio_num_t gpio_num , gpio_pull_mode_t pull )

Configure GPIO internal pull-up/pull-down resistors.

备注

This function always overwrite the current pull-up/pull-down configurations

备注

ESP32: Only pins that support both input & output have integrated pull-up and pull-down resistors. Input-only GPIOs 34-39 do not.

参数 :

gpio_num -- GPIO number. If you want to set pull up or down mode for e.g. GPIO16, gpio_num should be GPIO_NUM_16 (16);

pull -- GPIO pull up/down mode.

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG : Parameter error

esp_err_t gpio_wakeup_enable ( gpio_num_t gpio_num , gpio_int_type_t intr_type )

Enable GPIO wake-up function.

参数 :

gpio_num -- GPIO number.

intr_type -- GPIO wake-up type. Only GPIO_INTR_LOW_LEVEL or GPIO_INTR_HIGH_LEVEL can be used.

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_wakeup_disable ( gpio_num_t gpio_num )

Disable GPIO wake-up function.

备注

When either CONFIG_ESP_SLEEP_GPIO_RESET_WORKAROUND or CONFIG_PM_SLP_DISABLE_GPIO is enabled, the sleep-state configuration of gpio_num is applied during sleep (and that the user must call gpio_sleep_sel_dis() again if the pin should stay on the active-state configuration).

参数 :

gpio_num -- GPIO number

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_isr_register ( void ( * fn ) ( void * ) , void * arg , int intr_alloc_flags , gpio_isr_handle_t * handle )

Register GPIO interrupt handler, the handler is an ISR. The handler will be attached to the same CPU core that this function is running on.

This ISR function is called whenever any GPIO interrupt occurs. See the alternative gpio_install_isr_service() and gpio_isr_handler_add() API in order to have the driver support per-GPIO ISRs.

To disable or remove the ISR, pass the returned handle to the interrupt allocation functions .

参数 :

fn -- Interrupt handler function.

arg -- Parameter for handler function

intr_alloc_flags -- Flags used to allocate the interrupt. One or multiple (ORred) ESP_INTR_FLAG_* values. See esp_intr_alloc.h for more info.

handle -- Pointer to return handle. If non-NULL, a handle for the interrupt will be returned here.

返回 :

ESP_OK Success ;

ESP_ERR_INVALID_ARG GPIO error

ESP_ERR_NOT_FOUND No free interrupt found with the specified flags

esp_err_t gpio_pullup_en ( gpio_num_t gpio_num )

Enable pull-up on GPIO.

参数 :

gpio_num -- GPIO number

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_pullup_dis ( gpio_num_t gpio_num )

Disable pull-up on GPIO.

参数 :

gpio_num -- GPIO number

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_pulldown_en ( gpio_num_t gpio_num )

Enable pull-down on GPIO.

参数 :

gpio_num -- GPIO number

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_pulldown_dis ( gpio_num_t gpio_num )

Disable pull-down on GPIO.

参数 :

gpio_num -- GPIO number

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_output_enable ( gpio_num_t gpio_num )

Enable output for an IO (as a simple GPIO output)

参数 :

gpio_num -- GPIO number

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG GPIO number error

esp_err_t gpio_output_disable ( gpio_num_t gpio_num )

Disable output for an IO.

参数 :

gpio_num -- GPIO number

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG GPIO number error

esp_err_t gpio_od_enable ( gpio_num_t gpio_num )

Enable open-drain for an IO.

参数 :

gpio_num -- GPIO number

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG GPIO number error

esp_err_t gpio_od_disable ( gpio_num_t gpio_num )

Disable open-drain for an IO.

参数 :

gpio_num -- GPIO number

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG GPIO number error

esp_err_t gpio_install_isr_service ( int intr_alloc_flags )

Install the GPIO driver's ETS_GPIO_INTR_SOURCE ISR handler service, which allows per-pin GPIO interrupt handlers.

This function is incompatible with gpio_isr_register() - if that function is used, a single global ISR is registered for all GPIO interrupts. If this function is used, the ISR service provides a global GPIO ISR and individual pin handlers are registered via the gpio_isr_handler_add() function.

参数 :

intr_alloc_flags -- Flags used to allocate the interrupt. One or multiple (ORred) ESP_INTR_FLAG_* values. See esp_intr_alloc.h for more info.

返回 :

ESP_OK Success

ESP_ERR_NO_MEM No memory to install this service

ESP_ERR_INVALID_STATE ISR service already installed.

ESP_ERR_NOT_FOUND No free interrupt found with the specified flags

ESP_ERR_INVALID_ARG GPIO error

esp_err_t gpio_uninstall_isr_service ( void )

Uninstall the driver's GPIO ISR service, freeing related resources.

返回 :

ESP_OK Success

esp_err_t gpio_isr_handler_add ( gpio_num_t gpio_num , gpio_isr_t isr_handler , void * args )

Add ISR handler for the corresponding GPIO pin.

Call this function after using gpio_install_isr_service() to install the driver's GPIO ISR handler service.

The pin ISR handlers no longer need to be declared with IRAM_ATTR, unless you pass the ESP_INTR_FLAG_IRAM flag when allocating the ISR in gpio_install_isr_service().

This ISR handler will be called from an ISR. So there is a stack size limit (configurable as "ISR stack size" in menuconfig). This limit is smaller compared to a global GPIO interrupt handler due to the additional level of indirection.

参数 :

gpio_num -- GPIO number

isr_handler -- ISR handler function for the corresponding GPIO number.

args -- parameter for ISR handler.

返回 :

ESP_OK Success

ESP_ERR_INVALID_STATE Wrong state, the ISR service has not been initialized.

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_isr_handler_remove ( gpio_num_t gpio_num )

Remove ISR handler for the corresponding GPIO pin.

参数 :

gpio_num -- GPIO number

返回 :

ESP_OK Success

ESP_ERR_INVALID_STATE Wrong state, the ISR service has not been initialized.

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_set_drive_capability ( gpio_num_t gpio_num , gpio_drive_cap_t strength )

Set GPIO pad drive capability.

参数 :

gpio_num -- GPIO number, only support output GPIOs

strength -- Drive capability of the pad

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_get_drive_capability ( gpio_num_t gpio_num , gpio_drive_cap_t * strength )

Get GPIO pad drive capability.

参数 :

gpio_num -- GPIO number, only support output GPIOs

strength -- Pointer to accept drive capability of the pad

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_hold_en ( gpio_num_t gpio_num )

Enable gpio pad hold function.

When a GPIO is set to hold, its state is latched at that moment and will not change when the internal signal or the IO MUX/GPIO configuration is modified (including input enable, output enable, output value, function, and drive strength values). This function can be used to retain the state of GPIOs when the power domain of where GPIO/IOMUX belongs to becomes off. For example, chip or system is reset (e.g. watchdog time-out, Deep-sleep events are triggered), or peripheral power-down in Light-sleep.

This function works in both input and output modes, and only applicable to output-capable GPIOs. If this function is enabled: in output mode: the output level of the GPIO will be locked and can not be changed. in input mode: the input read value can still reflect the changes of the input signal.

Power down or call gpio_hold_dis will disable this function.

Please be aware that,

USB pads cannot hold at low level after waking up from Deep-sleep. The USB related registers are reset, so the USB pull-up is back.

For ESP32-P4 rev < 3.0, the states of IOs can not be hold after waking up from Deep-sleep.

For ESP32/S2/C3/S3/C2, this function cannot be used to hold the state of a digital GPIO during Deep-sleep. Even if this function is enabled, the digital GPIO will be reset to its default state when the chip wakes up from Deep-sleep. If you want to hold the state of a digital GPIO during Deep-sleep, please call gpio_deep_sleep_hold_en .

参数 :

gpio_num -- GPIO number, only support output-capable GPIOs

返回 :

ESP_OK Success

ESP_ERR_NOT_SUPPORTED Not support pad hold function

esp_err_t gpio_hold_dis ( gpio_num_t gpio_num )

Disable gpio pad hold function.

When the chip is woken up from peripheral power-down sleep, the gpio will be set to the default mode, so, the gpio will output the default level if this function is called. If you don't want the level changes, the gpio should be configured to a known state before this function is called. e.g. If you hold gpio18 high during Deep-sleep, after the chip is woken up and gpio_hold_dis is called, gpio18 will output low level(because gpio18 is input mode by default). If you don't want this behavior, you should configure gpio18 as output mode and set it to high level before calling gpio_hold_dis .

参数 :

gpio_num -- GPIO number, only support output-capable GPIOs

返回 :

ESP_OK Success

ESP_ERR_NOT_SUPPORTED Not support pad hold function

void gpio_deep_sleep_hold_en ( void )

Enable all digital gpio pads hold function during Deep-sleep.

Enabling this feature makes all digital gpio pads be at the holding state during Deep-sleep. The state of each pad holds is its active configuration (not pad's sleep configuration!).

Note:

For digital IO, this API takes effect only if the corresponding digital IO pad hold function has been enabled. You can enable the GPIO pad hold function by calling gpio_hold_en . has been enabled. You can call gpio_hold_en to enable the gpio pad hold function.

Though this API targets all digital IOs, the pad hold feature only works when the chip is in Deep-sleep mode. When the chip is in active mode, the digital GPIO state can be changed freely even if you have called this function, except for IOs that are already held by gpio_hold_en .

After this API is being called, the digital gpio Deep-sleep hold feature will work during every sleep process. You should call gpio_deep_sleep_hold_dis to disable this feature.

void gpio_deep_sleep_hold_dis ( void )

Disable all digital gpio pads hold function during Deep-sleep.

esp_err_t gpio_sleep_sel_en ( gpio_num_t gpio_num )

SOC_GPIO_SUPPORT_HOLD_SINGLE_IO_IN_DSLP.

Enable SLP_SEL to change GPIO status automantically in lightsleep.

参数 :

gpio_num -- GPIO number of the pad.

返回 :

ESP_OK Success

esp_err_t gpio_sleep_sel_dis ( gpio_num_t gpio_num )

Disable SLP_SEL to change GPIO status automantically in lightsleep.

参数 :

gpio_num -- GPIO number of the pad.

返回 :

ESP_OK Success

esp_err_t gpio_sleep_set_direction ( gpio_num_t gpio_num , gpio_mode_t mode )

GPIO set direction at sleep.

Configure GPIO direction,such as output_only,input_only,output_and_input

参数 :

gpio_num -- Configure GPIO pins number, it should be GPIO number. If you want to set direction of e.g. GPIO16, gpio_num should be GPIO_NUM_16 (16);

mode -- GPIO direction

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG GPIO error

esp_err_t gpio_sleep_set_pull_mode ( gpio_num_t gpio_num , gpio_pull_mode_t pull )

Configure GPIO pull-up/pull-down resistors at sleep.

备注

ESP32: Only pins that support both input & output have integrated pull-up and pull-down resistors. Input-only GPIOs 34-39 do not.

参数 :

gpio_num -- GPIO number. If you want to set pull up or down mode for e.g. GPIO16, gpio_num should be GPIO_NUM_16 (16);

pull -- GPIO pull up/down mode.

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG : Parameter error

esp_err_t gpio_wakeup_enable_on_hp_periph_powerdown_sleep ( gpio_num_t gpio_num , gpio_int_type_t intr_type )

Enable GPIO wake-up function on peripheral powerdowned sleep (including deepsleep and peripheral powerdowned lightsleep).

备注

Called by the SDK. User shouldn't call this directly in the APP.

参数 :

gpio_num -- GPIO number.

intr_type -- GPIO wake-up type.

Always supported: GPIO_INTR_LOW_LEVEL, GPIO_INTR_HIGH_LEVEL

If SOC_RTC_GPIO_EDGE_WAKEUP_SUPPORTED: GPIO_INTR_POSEDGE, GPIO_INTR_NEGEDGE, GPIO_INTR_ANYEDGE

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_wakeup_disable_on_hp_periph_powerdown_sleep ( gpio_num_t gpio_num )

Disable GPIO peripheral powerdowned sleep (including deepsleep and peripheral powerdowned lightsleep) wake-up function.

参数 :

gpio_num -- GPIO number

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_dump_io_configuration ( FILE * out_stream , uint64_t io_bit_mask )

Dump IO configuration information to console.

参数 :

out_stream -- IO stream (e.g. stdout)

io_bit_mask -- IO pin bit mask, each bit maps to an IO

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t gpio_get_io_config ( gpio_num_t gpio_num , gpio_io_config_t * out_io_config )

Get the configuration for an IO.

参数 :

gpio_num -- GPIO number

out_io_config -- [out] Pointer to the structure that saves the specific IO configuration

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

Structures

struct gpio_config_t

Configuration parameters of GPIO pad for gpio_config function.

Public Members

uint64_t pin_bit_mask

GPIO pin: set with bit mask, each bit maps to a GPIO

gpio_mode_t mode

GPIO mode: set input/output mode

gpio_pullup_t pull_up_en

GPIO pull-up

gpio_pulldown_t pull_down_en

GPIO pull-down

gpio_int_type_t intr_type

GPIO interrupt type

Macros

GPIO_IS_HP_PERIPH_PD_WAKEUP_VALID_IO ( gpio_num )

Type Definitions

typedef intr_handle_t gpio_isr_handle_t

typedef void ( * gpio_isr_t ) ( void * arg )

GPIO interrupt handler.

Param arg :

User registered data

Header File

components/esp_hal_gpio/include/hal/gpio_types.h

This header file can be included with:

#include"hal/gpio_types.h"

This header file is a part of the API provided by the esp_hal_gpio component. To declare that your component depends on esp_hal_gpio , add the following to your CMakeLists.txt:

REQUIRES esp_hal_gpio

or

PRIV_REQUIRES esp_hal_gpio

Structures

struct gpio_io_config_t

Structure that contains the configuration of an IO.

Public Members

gpio_drive_cap_t drv

Value of drive strength

uint32_t fun_sel

Value of IOMUX function selection

uint32_t sig_out

Index of the outputting peripheral signal

uint32_t pu

Status of pull-up enabled or not

uint32_t pd

Status of pull-down enabled or not

uint32_t ie

Status of input enabled or not

uint32_t oe

Status of output enabled or not

uint32_t oe_ctrl_by_periph

True if use output enable signal from peripheral, otherwise False

uint32_t oe_inv

Whether the output enable signal is inversed or not

uint32_t od

Status of open-drain enabled or not

uint32_t slp_sel

Status of pin sleep mode enabled or not

Macros

GPIO_PIN_COUNT

GPIO_IS_VALID_GPIO ( gpio_num )

Check whether it is a valid GPIO number.

GPIO_IS_VALID_OUTPUT_GPIO ( gpio_num )

Check whether it can be a valid GPIO number of output mode.

GPIO_IS_VALID_DIGITAL_IO_PAD ( gpio_num )

Check whether it can be a valid digital I/O pad.

GPIO_PIN_REG_0

GPIO_PIN_REG_1

GPIO_PIN_REG_2

GPIO_PIN_REG_3

GPIO_PIN_REG_4

GPIO_PIN_REG_5

GPIO_PIN_REG_6

GPIO_PIN_REG_7

GPIO_PIN_REG_8

GPIO_PIN_REG_9

GPIO_PIN_REG_10

GPIO_PIN_REG_11

GPIO_PIN_REG_12

GPIO_PIN_REG_13

GPIO_PIN_REG_14

GPIO_PIN_REG_15

GPIO_PIN_REG_16

GPIO_PIN_REG_17

GPIO_PIN_REG_18

GPIO_PIN_REG_19

GPIO_PIN_REG_20

GPIO_PIN_REG_21

GPIO_PIN_REG_22

GPIO_PIN_REG_23

GPIO_PIN_REG_24

GPIO_PIN_REG_25

GPIO_PIN_REG_26

GPIO_PIN_REG_27

GPIO_PIN_REG_28

GPIO_PIN_REG_29

GPIO_PIN_REG_30

GPIO_PIN_REG_31

GPIO_PIN_REG_32

GPIO_PIN_REG_33

GPIO_PIN_REG_34

GPIO_PIN_REG_35

GPIO_PIN_REG_36

GPIO_PIN_REG_37

GPIO_PIN_REG_38

GPIO_PIN_REG_39

GPIO_PIN_REG_40

GPIO_PIN_REG_41

GPIO_PIN_REG_42

GPIO_PIN_REG_43

GPIO_PIN_REG_44

GPIO_PIN_REG_45

GPIO_PIN_REG_46

GPIO_PIN_REG_47

GPIO_PIN_REG_48

GPIO_PIN_REG_49

GPIO_PIN_REG_50

GPIO_PIN_REG_51

GPIO_PIN_REG_52

GPIO_PIN_REG_53

GPIO_PIN_REG_54

Enumerations

enum gpio_port_t

Values:

enumerator GPIO_PORT_0

enumerator GPIO_PORT_MAX

enum gpio_int_type_t

Values:

enumerator GPIO_INTR_DISABLE

Disable GPIO interrupt

enumerator GPIO_INTR_POSEDGE

GPIO interrupt type : rising edge

enumerator GPIO_INTR_NEGEDGE

GPIO interrupt type : falling edge

enumerator GPIO_INTR_ANYEDGE

GPIO interrupt type : both rising and falling edge

enumerator GPIO_INTR_LOW_LEVEL

GPIO interrupt type : input low level trigger

enumerator GPIO_INTR_HIGH_LEVEL

GPIO interrupt type : input high level trigger

enumerator GPIO_INTR_MAX

enum gpio_mode_t

Values:

enumerator GPIO_MODE_DISABLE

GPIO mode : disable input and output

enumerator GPIO_MODE_INPUT

GPIO mode : input only

enumerator GPIO_MODE_OUTPUT

GPIO mode : output only mode

enumerator GPIO_MODE_OUTPUT_OD

GPIO mode : output only with open-drain mode

enumerator GPIO_MODE_INPUT_OUTPUT_OD

GPIO mode : output and input with open-drain mode

enumerator GPIO_MODE_INPUT_OUTPUT

GPIO mode : output and input mode

enum gpio_pullup_t

Values:

enumerator GPIO_PULLUP_DISABLE

Disable GPIO pull-up resistor

enumerator GPIO_PULLUP_ENABLE

Enable GPIO pull-up resistor

enum gpio_pulldown_t

Values:

enumerator GPIO_PULLDOWN_DISABLE

Disable GPIO pull-down resistor

enumerator GPIO_PULLDOWN_ENABLE

Enable GPIO pull-down resistor

enum gpio_pull_mode_t

Values:

enumerator GPIO_PULLUP_ONLY

Pad pull up

enumerator GPIO_PULLDOWN_ONLY

Pad pull down

enumerator GPIO_PULLUP_PULLDOWN

Pad pull up + pull down

enumerator GPIO_FLOATING

Pad floating

enum gpio_drive_cap_t

Values:

enumerator GPIO_DRIVE_CAP_0

Pad drive capability: weak

enumerator GPIO_DRIVE_CAP_1

Pad drive capability: stronger

enumerator GPIO_DRIVE_CAP_2

Pad drive capability: medium

enumerator GPIO_DRIVE_CAP_DEFAULT

Pad drive capability: medium

enumerator GPIO_DRIVE_CAP_3

Pad drive capability: strongest

enumerator GPIO_DRIVE_CAP_MAX

API 参考 - RTC GPIO

Header File

components/esp_driver_gpio/include/driver/rtc_io.h

This header file can be included with:

#include"driver/rtc_io.h"

This header file is a part of the API provided by the esp_driver_gpio component. To declare that your component depends on esp_driver_gpio , add the following to your CMakeLists.txt:

REQUIRES esp_driver_gpio

or

PRIV_REQUIRES esp_driver_gpio

Functions

bool rtc_gpio_is_valid_gpio ( gpio_num_t gpio_num )

Determine if the specified IO is a valid RTC GPIO.

参数 :

gpio_num -- GPIO number

返回 :

true if the IO is valid for RTC GPIO use. false otherwise.

int rtc_io_number_get ( gpio_num_t gpio_num )

Get RTC IO index number by GPIO number.

参数 :

gpio_num -- GPIO number

返回 :

>=0: Index of RTC IO. -1 : The IO is not an RTC IO.

esp_err_t rtc_gpio_init ( gpio_num_t gpio_num )

Init an IO to be an RTC GPIO, route to RTC IO MUX.

参数 :

gpio_num -- GPIO number (e.g. GPIO_NUM_12)

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG The IO is not an RTC IO

esp_err_t rtc_gpio_deinit ( gpio_num_t gpio_num )

Deinit an IO as an RTC GPIO, route back to IO MUX.

参数 :

gpio_num -- GPIO number (e.g. GPIO_NUM_12)

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG The IO is not an RTC IO

uint32_t rtc_gpio_get_level ( gpio_num_t gpio_num )

Get the RTC IO input level.

参数 :

gpio_num -- GPIO number (e.g. GPIO_NUM_12)

返回 :

1 High level

0 Low level

ESP_ERR_INVALID_ARG The IO is not an RTC IO

esp_err_t rtc_gpio_set_level ( gpio_num_t gpio_num , uint32_t level )

Set the RTC IO output level.

参数 :

gpio_num -- GPIO number (e.g. GPIO_NUM_12)

level -- output level

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG The IO is not an RTC IO

esp_err_t rtc_gpio_set_direction ( gpio_num_t gpio_num , rtc_gpio_mode_t mode )

RTC GPIO set direction.

Configure RTC GPIO direction, such as output only, input only, output and input.

参数 :

gpio_num -- GPIO number (e.g. GPIO_NUM_12)

mode -- RTC GPIO direction

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG The IO is not an RTC IO

esp_err_t rtc_gpio_set_direction_in_sleep ( gpio_num_t gpio_num , rtc_gpio_mode_t mode )

RTC GPIO set direction in deep sleep mode or disable sleep status (default). In some application scenarios, IO needs to have another states during deep sleep.

NOTE: ESP32 supports INPUT_ONLY mode. The rest targets support INPUT_ONLY, OUTPUT_ONLY, INPUT_OUTPUT mode.

参数 :

gpio_num -- GPIO number (e.g. GPIO_NUM_12)

mode -- RTC GPIO direction

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG The IO is not an RTC IO

esp_err_t rtc_gpio_pullup_en ( gpio_num_t gpio_num )

RTC GPIO pullup enable.

This function only works for RTC IOs. In general, call gpio_pullup_en, which will work both for normal GPIOs and RTC IOs.

参数 :

gpio_num -- GPIO number (e.g. GPIO_NUM_12)

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG The IO is not an RTC IO

esp_err_t rtc_gpio_pulldown_en ( gpio_num_t gpio_num )

RTC GPIO pulldown enable.

This function only works for RTC IOs. In general, call gpio_pulldown_en, which will work both for normal GPIOs and RTC IOs.

参数 :

gpio_num -- GPIO number (e.g. GPIO_NUM_12)

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG The IO is not an RTC IO

esp_err_t rtc_gpio_pullup_dis ( gpio_num_t gpio_num )

RTC GPIO pullup disable.

This function only works for RTC IOs. In general, call gpio_pullup_dis, which will work both for normal GPIOs and RTC IOs.

参数 :

gpio_num -- GPIO number (e.g. GPIO_NUM_12)

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG The IO is not an RTC IO

esp_err_t rtc_gpio_pulldown_dis ( gpio_num_t gpio_num )

RTC GPIO pulldown disable.

This function only works for RTC IOs. In general, call gpio_pulldown_dis, which will work both for normal GPIOs and RTC IOs.

参数 :

gpio_num -- GPIO number (e.g. GPIO_NUM_12)

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG The IO is not an RTC IO

esp_err_t rtc_gpio_set_drive_capability ( gpio_num_t gpio_num , gpio_drive_cap_t strength )

Set RTC GPIO pad drive capability.

参数 :

gpio_num -- GPIO number, only support output GPIOs

strength -- Drive capability of the pad

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t rtc_gpio_get_drive_capability ( gpio_num_t gpio_num , gpio_drive_cap_t * strength )

Get RTC GPIO pad drive capability.

参数 :

gpio_num -- GPIO number, only support output GPIOs

strength -- Pointer to accept drive capability of the pad

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t rtc_gpio_iomux_func_sel ( gpio_num_t gpio_num , int func )

Select a RTC IOMUX function for the RTC IO.

参数 :

gpio_num -- GPIO number

func -- Function to assign to the pin

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG Parameter error

esp_err_t rtc_gpio_iomux_input ( gpio_num_t gpio_num , int func , uint32_t signal_idx )

Set pad input to an LP peripheral signal through the LP(RTC) IOMUX.

参数 :

gpio_num -- GPIO number

func -- The index number of the LP(RTC) IOMUX function to be selected for the pin

signal_idx -- Peripheral signal index to input. One of the *_IN_IDX signals in soc/lp_gpio_sig_map.h .

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG GPIO number error

esp_err_t rtc_gpio_iomux_output ( gpio_num_t gpio_num , int func )

Set LP peripheral output to an RTC IO pad through the LP(RTC) IOMUX.

参数 :

gpio_num -- GPIO number

func -- The index number of the LP(RTC) IOMUX function to be selected for the pin

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG GPIO number error

esp_err_t rtc_gpio_hold_en ( gpio_num_t gpio_num )

Enable hold function on an RTC IO pad.

Enabling HOLD function will cause the pad to latch current values of input enable, output enable, output value, function, drive strength values. This function is useful when going into light or deep sleep mode to prevent the pin configuration from changing.

参数 :

gpio_num -- GPIO number (e.g. GPIO_NUM_12)

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG The IO is not an RTC IO

esp_err_t rtc_gpio_hold_dis ( gpio_num_t gpio_num )

Disable hold function on an RTC IO pad.

Disabling hold function will allow the pad receive the values of input enable, output enable, output value, function, drive strength from RTC_IO peripheral.

参数 :

gpio_num -- GPIO number (e.g. GPIO_NUM_12)

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG The IO is not an RTC IO

esp_err_t rtc_gpio_force_hold_en_all ( void )

Enable force hold signal for all RTC IOs.

Each RTC pad has a "force hold" input signal from the RTC controller. If this signal is set, pad latches current values of input enable, function, output enable, and other signals which come from the RTC mux. Force hold signal is enabled before going into deep sleep for pins which are used for EXT1 wakeup.

esp_err_t rtc_gpio_force_hold_dis_all ( void )

Disable force hold signal for all RTC IOs.

esp_err_t rtc_gpio_isolate ( gpio_num_t gpio_num )

Helper function to disconnect internal circuits from an RTC IO This function disables input, output, pullup, pulldown, and enables hold feature for an RTC IO. Use this function if an RTC IO needs to be disconnected from internal circuits in deep sleep, to minimize leakage current.

In particular, for ESP32-WROVER module, call rtc_gpio_isolate(GPIO_NUM_12) before entering deep sleep, to reduce deep sleep current.

参数 :

gpio_num -- GPIO number (e.g. GPIO_NUM_12).

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG The IO is not an RTC IO

esp_err_t rtc_gpio_wakeup_enable ( gpio_num_t gpio_num , gpio_int_type_t intr_type )

Enable wakeup from sleep mode using specific GPIO.

参数 :

gpio_num -- GPIO number

intr_type -- Wakeup trigger type:

Always supported: GPIO_INTR_HIGH_LEVEL, GPIO_INTR_LOW_LEVEL

If SOC_RTC_GPIO_EDGE_WAKEUP_SUPPORTED: GPIO_INTR_POSEDGE, GPIO_INTR_NEGEDGE, GPIO_INTR_ANYEDGE

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG The IO is not an RTC IO, or intr_type is not supported by the target.

esp_err_t rtc_gpio_wakeup_disable ( gpio_num_t gpio_num )

Disable wakeup from sleep mode using specific GPIO.

参数 :

gpio_num -- GPIO number

返回 :

ESP_OK Success

ESP_ERR_INVALID_ARG The IO is not an RTC IO

Macros

RTC_GPIO_IS_VALID_GPIO ( gpio_num )

Header File

components/esp_driver_gpio/include/driver/lp_io.h

This header file can be included with:

#include"driver/lp_io.h"

This header file is a part of the API provided by the esp_driver_gpio component. To declare that your component depends on esp_driver_gpio , add the following to your CMakeLists.txt:

REQUIRES esp_driver_gpio

or

PRIV_REQUIRES esp_driver_gpio

Header File

components/esp_hal_gpio/include/hal/rtc_io_types.h

This header file can be included with:

#include"hal/rtc_io_types.h"

This header file is a part of the API provided by the esp_hal_gpio component. To declare that your component depends on esp_hal_gpio , add the following to your CMakeLists.txt:

REQUIRES esp_hal_gpio

or

PRIV_REQUIRES esp_hal_gpio

Enumerations

enum rtc_gpio_mode_t

RTCIO output/input mode type.

Values:

enumerator RTC_GPIO_MODE_INPUT_ONLY

Pad input

enumerator RTC_GPIO_MODE_OUTPUT_ONLY

Pad output

enumerator RTC_GPIO_MODE_INPUT_OUTPUT

Pad input + output

enumerator RTC_GPIO_MODE_DISABLED

Pad (output + input) disable

enumerator RTC_GPIO_MODE_OUTPUT_OD

Pad open-drain output

enumerator RTC_GPIO_MODE_INPUT_OUTPUT_OD

Pad input + open-drain output

此文档对您有帮助吗？

反馈已收到，谢谢！

如果您有其他意见，欢迎填写 乐鑫文档反馈表 。

我们重视您的反馈。

您可以填写 乐鑫文档反馈表 告诉我们如何改进该文档。
