来源：https://docs.espressif.com/projects/esp-idf/zh_CN/v5.5.4/esp32/api-reference/peripherals/adc_oneshot.html

# 模数转换器 (ADC) 单次转换模式驱动

## 简介

模数转换器集成于芯片，支持测量特定模拟 IO 管脚的模拟信号。

ESP32 有 {SOC_ADC_PERIPH_NUM} 个 ADC 单元，可以在以下场景使用：

- 生成 ADC 单次转换结果

- 生成连续 ADC 转换结果

本指南介绍了 ADC 单次转换模式。

## 功能概述

下文将分节概述安装和运行 ADC 的基本步骤：

- 资源分配 - 介绍获取 ADC 句柄所需设置的参数，以及如何在 ADC 完成工作后回收资源。

- 配置 ADC 单元实例 - 介绍配置 ADC 单元所需设置的参数，用于获取 ADC 转换的原始结果。

- 读取转换结果 - 介绍如何获取 ADC 转换的原始结果。

- 硬件限制 - 介绍与 ADC 相关的硬件限制。

- 电源管理 - 介绍电源管理的相关内容。

- IRAM 安全 - 介绍在禁用 cache 时，如何读取 ADC 转换的原始结果。

- 线程安全 - 介绍由驱动程序认证为线程安全的 API。

- Kconfig 选项 - 介绍支持的 Kconfig 选项，不同选项对驱动程序的操作会产生不同影响。

### 资源分配

ADC 单次转换模式驱动基于 ESP32 SAR ADC 模块实现，不同的 ESP 芯片可能拥有不同数量的独立 ADC。对于单次转换模式驱动而言，ADC 实例以 `adc_oneshot_unit_handle_t` 表示。

请设置所需的初始配置结构体 `adc_oneshot_unit_init_cfg_t` 安装 ADC 实例，具体如下：

- `adc_oneshot_unit_init_cfg_t::unit_id` 选择 ADC。请参阅 技术规格书，了解对应 ADC 的专用模拟 IO 管脚。

- `adc_oneshot_unit_init_cfg_t::clk_src` 选择 ADC 的时钟源。设置为 0 时，驱动程序将使用默认时钟源，详情请参阅 `adc_oneshot_clk_src_t`。

- `adc_oneshot_unit_init_cfg_t::ulp_mode` 设置是否支持 ADC 在 ULP 模式下工作。

完成 ADC 初始配置后，使用已设置的初始配置结构体 `adc_oneshot_unit_init_cfg_t` 调用 `adc_oneshot_new_unit()`。如果分配成功，该函数将返回 ADC 单元实例句柄。

该函数可能因参数无效、内存不足等原因返回错误代码。比如，当要分配的 ADC 实例已经注册时，该函数会返回 `ESP_ERR_NOT_FOUND` 错误。可用 ADC 数量可通过 `SOC_ADC_PERIPH_NUM` 查看。

如果不再需要先前创建的 ADC 单元实例，请调用 `adc_oneshot_del_unit()` 回收该实例，相关的硬件和软件资源也会回收。

#### 在普通单次转换模式下创建 ADC 单元实例句柄

`
adc_oneshot_unit_handle_t adc1_handle;
adc_oneshot_unit_init_cfg_t init_config1 = {
    .unit_id = ADC_UNIT_1,
    .ulp_mode = ADC_ULP_MODE_DISABLE,
};
ESP_ERROR_CHECK(adc_oneshot_new_unit(&init_config1, &adc1_handle));
`

#### 回收 ADC 单元实例

`
ESP_ERROR_CHECK(adc_oneshot_del_unit(adc1_handle));
`

### 配置 ADC 单元实例

创建 ADC 单元实例后，请设置 `adc_oneshot_chan_cfg_t` 配置 ADC IO 以测量模拟信号，具体如下：

- `adc_oneshot_chan_cfg_t::atten`，ADC 衰减。请参阅 技术规格书 > `ADC 特性`。

- `adc_oneshot_chan_cfg_t::bitwidth`，原始转换结果的位宽。

备注

ADC IO 及其对应的 ADC 通道编号，请参阅 技术规格书。

此外，可以使用 `adc_continuous_io_to_channel()` 和 `adc_continuous_channel_to_io()` 了解 ADC 通道和 ADC IO。

为使以上设置生效，请使用上述配置结构体调用 `adc_oneshot_config_channel()`，并指定要配置的 ADC 通道。函数 `adc_oneshot_config_channel()` 支持多次调用，以配置不同的 ADC 通道。驱动程序将在内部保存每个通道的配置。

#### 配置两个 ADC 通道

`
adc_oneshot_chan_cfg_t config = {
    .bitwidth = ADC_BITWIDTH_DEFAULT,
    .atten = ADC_ATTEN_DB_12,
};
ESP_ERROR_CHECK(adc_oneshot_config_channel(adc1_handle, EXAMPLE_ADC1_CHAN0, &config));
ESP_ERROR_CHECK(adc_oneshot_config_channel(adc1_handle, EXAMPLE_ADC1_CHAN1, &config));
`

### 读取转换结果

完成上述配置后，ADC 即可测量来自配置好的 ADC 通道的模拟信号。调用 `adc_oneshot_read()` 可以获取 ADC 通道的原始转换结果。

- `adc_oneshot_read()` 可安全使用。ADC 由其他驱动程序/外设共享，请参阅 硬件限制。函数 `adc_oneshot_read()` 使用互斥锁，避免与其他函数同时使用硬件，因此该函数不应在 ISR 上下文中使用。当 ADC 由其他驱动程序/外设占用时，该函数可能出错，并返回 `ESP_ERR_TIMEOUT` 错误。此时，ADC 原始结果无效。

该函数可能因参数无效而调用失败。

通过该函数获取的 ADC 转换结果为原始数据。可以使用以下公式，根据 ADC 原始结果计算电压：

`
Vout = Dout * Vmax / Dmax       (1)
`

其中：

| Vout | 数字输出结果，代表电压。 |
| --- | --- |
| Dout | ADC 原始数字读取结果。 |
| Vmax | 可测量的最大模拟输入电压，与 ADC 衰减相关，请参考 技术参考手册 > `片上传感器与模拟信号处理`。 |
| Dmax | 输出 ADC 原始数字读取结果的最大值，即 2^位宽，位宽即之前配置的 `adc_oneshot_chan_cfg_t::bitwidth`。 |

若需进一步校准，将 ADC 原始结果转换为以 mV 为单位的电压数据，请参考校准文档 模数转换器 (ADC) 校准驱动程序。

#### 读取原始结果

`
ESP_ERROR_CHECK(adc_oneshot_read(adc1_handle, EXAMPLE_ADC1_CHAN0, &adc_raw[0][0]));
ESP_LOGI(TAG, "ADC%d Channel[%d] Raw Data: %d", ADC_UNIT_1 + 1, EXAMPLE_ADC1_CHAN0, adc_raw[0][0]);

ESP_ERROR_CHECK(adc_oneshot_read(adc1_handle, EXAMPLE_ADC1_CHAN1, &adc_raw[0][1]));
ESP_LOGI(TAG, "ADC%d Channel[%d] Raw Data: %d", ADC_UNIT_1 + 1, EXAMPLE_ADC1_CHAN1, adc_raw[0][1]);
`

### 硬件限制

- 随机数生成器 (RNG) 以 ADC 为输入源。使用 ADC 单次转换模式驱动从 RNG 生成随机数时，随机性会减弱。

- 一个 ADC 单元每次只能在一种操作模式下运行，可以是连续模式或单次模式。`adc_oneshot_start()` 提供了保护措施。

- Wi-Fi 也使用 ADC2，`adc_oneshot_read()` 提供了 Wi-Fi 驱动与 ADC 单次转换模式驱动间的保护。

- ESP32-DevKitC：GPIO0 已用于自动烧录功能，不能用于 ADC 单次转换模式。

- ESP-WROVER-KIT：GPIO0、GPIO2、GPIO4 和 GPIO15 已有其他用途，不能用于 ADC 单次转换模式。

### 电源管理

启用电源管理，即启用 CONFIG_PM_ENABLE 时，系统在空闲状态下可能会调整系统时钟频率。然而，ADC 单次转换模式驱动以轮询例程运行，`adc_oneshot_read()` 会不断检查 CPU 是否完成读取，直到函数返回。在此期间，ADC 单次转换模式驱动程序所在的任务不会受阻塞。因此，在读取时时钟频率保持稳定。

### IRAM 安全

flash 写入/擦除、OTA 等原因都可能导致 cache 禁用，此时，默认不应运行任何 ADC 单次转换模式驱动 API。如果在禁用 cache 时执行了 ADC 单次转换模式驱动 API，可能会出现类似 `Illegal Instruction` 或 `Load/Store Prohibited` 的错误。

### 线程安全

- `adc_oneshot_new_unit()`

- `adc_oneshot_config_channel()`

- `adc_oneshot_read()`

上述函数均为线程安全，使用时，可以直接从不同的 RTOS 任务中调用以上函数，无需额外锁保护。

- `adc_oneshot_del_unit()` 非线程安全。此外，与上文中线程安全的函数一起调用该函数时，可能导致线程安全函数的调用出错。

### Kconfig 选项

- CONFIG_ADC_ONESHOT_CTRL_FUNC_IN_IRAM 决定了放置 ADC 快速读取函数的位置，即 IRAM 或 flash 中，详情请参阅 IRAM 安全。

## 应用示例

- peripherals/adc/oneshot_read 演示了如何使用 ADC 单次模式驱动程序从 GPIO 管脚获取单次 ADC 数值，并展示了如何使用 ADC 校准功能在 ESP32 上获得校准后的结果，单位为毫伏。

## API 参考

### Header File

- components/hal/include/hal/adc_types.h

- This header file can be included with:

`
#include "hal/adc_types.h"
`

### Structures

struct adc_digi_pattern_config_t

ADC digital controller pattern configuration.

Public Members

uint8_t atten

Attenuation of this ADC channel.

uint8_t channel

ADC channel.

uint8_t unit

ADC unit.

uint8_t bit_width

ADC output bit width.

struct adc_digi_output_data_t

ADC digital controller (DMA mode) output data format. Used to analyze the acquired ADC (DMA) data.

备注

ESP32: Only `type1` is valid. ADC2 does not support DMA mode.

备注

ESP32-S2: Member `channel` can be used to judge the validity of the ADC data, because the role of the arbiter may get invalid ADC data.

Public Members

uint16_t data

ADC real output data info. Resolution: 12 bit.

ADC real output data info. Resolution: 11 bit.

uint16_t channel

ADC channel index info.

ADC channel index info. For ESP32-S2: If (channel < ADC_CHANNEL_MAX), The data is valid. If (channel > ADC_CHANNEL_MAX), The data is invalid.

struct adc_digi_output_data_t type1

ADC type1

uint16_t unit

ADC unit index info. 0: ADC1; 1: ADC2.

struct adc_digi_output_data_t type2

When the configured output format is 11bit.

uint16_t val

Raw data value

### Type Definitions

typedef soc_periph_adc_rtc_clk_src_t adc_oneshot_clk_src_t

Clock source type of oneshot mode which uses RTC controller.

typedef soc_periph_adc_digi_clk_src_t adc_continuous_clk_src_t

Clock source type of continuous mode which uses digital controller.

### Enumerations

enum adc_unit_t

ADC unit.

Values:

enumerator ADC_UNIT_1

SAR ADC 1.

enumerator ADC_UNIT_2

SAR ADC 2.

enum adc_channel_t

ADC channels.

Values:

enumerator ADC_CHANNEL_0

ADC channel.

enumerator ADC_CHANNEL_1

ADC channel.

enumerator ADC_CHANNEL_2

ADC channel.

enumerator ADC_CHANNEL_3

ADC channel.

enumerator ADC_CHANNEL_4

ADC channel.

enumerator ADC_CHANNEL_5

ADC channel.

enumerator ADC_CHANNEL_6

ADC channel.

enumerator ADC_CHANNEL_7

ADC channel.

enumerator ADC_CHANNEL_8

ADC channel.

enumerator ADC_CHANNEL_9

ADC channel.

enumerator ADC_CHANNEL_10

ADC channel.

enum adc_atten_t

ADC attenuation parameter. Different parameters determine the range of the ADC.

Values:

enumerator ADC_ATTEN_DB_0

No input attenuation, ADC can measure up to approx.

enumerator ADC_ATTEN_DB_2_5

The input voltage of ADC will be attenuated extending the range of measurement by about 2.5 dB.

enumerator ADC_ATTEN_DB_6

The input voltage of ADC will be attenuated extending the range of measurement by about 6 dB.

enumerator ADC_ATTEN_DB_12

The input voltage of ADC will be attenuated extending the range of measurement by about 12 dB.

enumerator ADC_ATTEN_DB_11

This is deprecated, it behaves the same as `ADC_ATTEN_DB_12`

enum adc_bitwidth_t

ADC bitwidth.

Values:

enumerator ADC_BITWIDTH_DEFAULT

Default ADC output bits, max supported width will be selected.

enumerator ADC_BITWIDTH_9

ADC output width is 9Bit.

enumerator ADC_BITWIDTH_10

ADC output width is 10Bit.

enumerator ADC_BITWIDTH_11

ADC output width is 11Bit.

enumerator ADC_BITWIDTH_12

ADC output width is 12Bit.

enumerator ADC_BITWIDTH_13

ADC output width is 13Bit.

enum adc_ulp_mode_t

ADC ULP working mode.

This decides the controller that controls ADC when in low power mode. Set `ADC_ULP_MODE_DISABLE` for normal mode.

Values:

enumerator ADC_ULP_MODE_DISABLE

ADC ULP mode is disabled.

enumerator ADC_ULP_MODE_FSM

ADC is controlled by ULP FSM.

enumerator ADC_ULP_MODE_RISCV

ADC is controlled by ULP RISCV.

enum adc_digi_convert_mode_t

ADC digital controller (DMA mode) work mode.

Values:

enumerator ADC_CONV_SINGLE_UNIT_1

Only use ADC1 for conversion.

enumerator ADC_CONV_SINGLE_UNIT_2

Only use ADC2 for conversion.

enumerator ADC_CONV_BOTH_UNIT

Use Both ADC1 and ADC2 for conversion simultaneously.

enumerator ADC_CONV_ALTER_UNIT

Use both ADC1 and ADC2 for conversion by turn. e.g. ADC1 -> ADC2 -> ADC1 -> ADC2 .....

enum adc_digi_output_format_t

ADC digital controller (DMA mode) output data format option.

Values:

enumerator ADC_DIGI_OUTPUT_FORMAT_TYPE1

See `adc_digi_output_data_t.type1`

enumerator ADC_DIGI_OUTPUT_FORMAT_TYPE2

See `adc_digi_output_data_t.type2`

enum adc_digi_iir_filter_t

ADC IIR Filter ID.

Values:

enumerator ADC_DIGI_IIR_FILTER_0

Filter 0.

enumerator ADC_DIGI_IIR_FILTER_1

Filter 1.

enum adc_digi_iir_filter_coeff_t

IIR Filter Coefficient.

Values:

enumerator ADC_DIGI_IIR_FILTER_COEFF_2

The filter coefficient is 2.

enumerator ADC_DIGI_IIR_FILTER_COEFF_4

The filter coefficient is 4.

enumerator ADC_DIGI_IIR_FILTER_COEFF_8

The filter coefficient is 8.

enumerator ADC_DIGI_IIR_FILTER_COEFF_16

The filter coefficient is 16.

enumerator ADC_DIGI_IIR_FILTER_COEFF_32

The filter coefficient is 32.

enumerator ADC_DIGI_IIR_FILTER_COEFF_64

The filter coefficient is 64.

enum adc_monitor_id_t

ADC monitor (continuous mode) ID.

Values:

enumerator ADC_MONITOR_0

The monitor index 0.

enumerator ADC_MONITOR_1

The monitor index 1.

enum adc_monitor_mode_t

Monitor config/event mode type.

Values:

enumerator ADC_MONITOR_MODE_HIGH

ADC raw_result > threshold value, monitor interrupt will be generated.

enumerator ADC_MONITOR_MODE_LOW

ADC raw_result < threshold value, monitor interrupt will be generated.

### Header File

- components/esp_adc/include/esp_adc/adc_oneshot.h

- This header file can be included with:

`
#include "esp_adc/adc_oneshot.h"
`

- This header file is a part of the API provided by the `esp_adc` component. To declare that your component depends on `esp_adc`, add the following to your CMakeLists.txt:

`
REQUIRES esp_adc
`

or

`
PRIV_REQUIRES esp_adc
`

### Functions

esp_err_t adc_oneshot_new_unit(const adc_oneshot_unit_init_cfg_t *init_config, adc_oneshot_unit_handle_t *ret_unit)

Create a handle to a specific ADC unit.

备注

This API is thread-safe. For more details, see ADC programming guide

参数:

- init_config -- [in] Driver initial configurations

- ret_unit -- [out] ADC unit handle

返回:

- ESP_OK: On success

- ESP_ERR_INVALID_ARG: Invalid arguments

- ESP_ERR_NO_MEM: No memory

- ESP_ERR_NOT_FOUND: The ADC peripheral to be claimed is already in use

- ESP_FAIL: Clock source isn't initialised correctly

esp_err_t adc_oneshot_config_channel(adc_oneshot_unit_handle_t handle, adc_channel_t channel, const adc_oneshot_chan_cfg_t *config)

Set ADC oneshot mode required configurations.

备注

This API is thread-safe. For more details, see ADC programming guide

参数:

- handle -- [in] ADC handle

- channel -- [in] ADC channel to be configured

- config -- [in] ADC configurations

返回:

- ESP_OK: On success

- ESP_ERR_INVALID_ARG: Invalid arguments

esp_err_t adc_oneshot_read(adc_oneshot_unit_handle_t handle, adc_channel_t chan, int *out_raw)

Get one ADC conversion raw result.

备注

This API is thread-safe. For more details, see ADC programming guide

备注

This API should NOT be called in an ISR context

参数:

- handle -- [in] ADC handle

- chan -- [in] ADC channel

- out_raw -- [out] ADC conversion raw result

返回:

- ESP_OK: On success

- ESP_ERR_INVALID_ARG: Invalid arguments

- ESP_ERR_TIMEOUT: Timeout, the ADC result is invalid

esp_err_t adc_oneshot_del_unit(adc_oneshot_unit_handle_t handle)

Delete the ADC unit handle.

备注

This API is thread-safe. For more details, see ADC programming guide

参数:

handle -- [in] ADC handle

返回:

- ESP_OK: On success

- ESP_ERR_INVALID_ARG: Invalid arguments

- ESP_ERR_NOT_FOUND: The ADC peripheral to be disclaimed isn't in use

esp_err_t adc_oneshot_io_to_channel(int io_num, adc_unit_t *const unit_id, adc_channel_t *const channel)

Get ADC channel from the given GPIO number.

参数:

- io_num -- [in] GPIO number

- unit_id -- [out] ADC unit

- channel -- [out] ADC channel

返回:

- ESP_OK: On success

- ESP_ERR_INVALID_ARG: Invalid argument

- ESP_ERR_NOT_FOUND: The IO is not a valid ADC pad

esp_err_t adc_oneshot_channel_to_io(adc_unit_t unit_id, adc_channel_t channel, int *const io_num)

Get GPIO number from the given ADC channel.

参数:

- unit_id -- [in] ADC unit

- channel -- [in] ADC channel

- io_num -- [out] GPIO number

- - -- ESP_OK: On success

  - ESP_ERR_INVALID_ARG: Invalid argument

esp_err_t adc_oneshot_get_calibrated_result(adc_oneshot_unit_handle_t handle, adc_cali_handle_t cali_handle, adc_channel_t chan, int *cali_result)

Convenience function to get ADC calibrated result.

This is an all-in-one function which does:

- oneshot read ADC raw result

- calibrate the raw result and convert it into calibrated result (in mV)

参数:

- handle -- [in] ADC oneshot handle, you should call adc_oneshot_new_unit() to get this handle

- cali_handle -- [in] ADC calibration handle, you should call adc_cali_create_scheme_x() in adc_cali_scheme.h to create a handle

- chan -- [in] ADC channel

- cali_result -- [out] Calibrated ADC result (in mV)

返回:

- ESP_OK Other return errors from adc_oneshot_read() and adc_cali_raw_to_voltage()

### Structures

struct adc_oneshot_unit_init_cfg_t

ADC oneshot driver initial configurations.

Public Members

adc_unit_t unit_id

ADC unit.

adc_oneshot_clk_src_t clk_src

Clock source.

adc_ulp_mode_t ulp_mode

ADC controlled by ULP, see `adc_ulp_mode_t`

struct adc_oneshot_chan_cfg_t

ADC channel configurations.

Public Members

adc_atten_t atten

ADC attenuation.

adc_bitwidth_t bitwidth

ADC conversion result bits.

### Type Definitions

typedef struct adc_oneshot_unit_ctx_t *adc_oneshot_unit_handle_t

Type of ADC unit handle for oneshot mode.

此文档对您有帮助吗？

- 反馈已收到，谢谢！

- 如果您有其他意见，欢迎填写乐鑫文档反馈表。

- 我们重视您的反馈。

- 您可以填写乐鑫文档反馈表告诉我们如何改进该文档。
