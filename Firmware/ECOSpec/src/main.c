#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
#include "driver/uart.h"
#include "driver/ledc.h"
#include "driver/i2s.h"
#include "driver/spi_master.h"
#include "esp_system.h"
#include "esp_log.h"
#include "esp_spiffs.h"
#include "esp_rom_sys.h"
#include <string.h>

static const char *TAG = "main";

#define UART_NUM UART_NUM_0
#define UART_BUF 256

#define LASER_LDO_ENABLE GPIO_NUM_26
#define LASER_ENABLE GPIO_NUM_27

#define FAN_ENABLE GPIO_NUM_33

#define SERVO_PIN   GPIO_NUM_32
#define MIN_DUTY    410
#define MAX_DUTY    2048

#define I2S_NUM       I2S_NUM_0
#define WAV_FILE_PATH "/spiffs/audio.wav"
#define READ_BUF_SIZE 4096

#define DIGIPOT_MAX_POS 255
#define PIN_NUM_MOSI  GPIO_NUM_23
#define PIN_NUM_CLK   GPIO_NUM_18
#define PIN_NUM_CS    GPIO_NUM_5

static QueueHandle_t uart_event_queue;
static QueueHandle_t servo_queue;
static QueueHandle_t audio_queue;
static QueueHandle_t digipot_queue;
static SemaphoreHandle_t uart_mutex;
static spi_device_handle_t tpl_spi;

uint32_t angle_to_duty_cycle(uint8_t angle)
{
    if (angle > 180) angle = 180;
    // Map angle (0° -> 0.5ms, 180° -> 2.5ms)
    float pulse_width = 0.5 + (angle / 180.0) * 2.0;
    // Convert pulse width to duty cycle (12-bit resolution, 50Hz)
    uint32_t duty = (pulse_width / 20.0) * 4096;

    return duty;
}

static void uart_print(const char *msg) {
    xSemaphoreTake(uart_mutex, portMAX_DELAY);
    uart_write_bytes(UART_NUM, msg, strlen(msg));
    uart_wait_tx_done(UART_NUM, pdMS_TO_TICKS(100));
    xSemaphoreGive(uart_mutex);
}

typedef struct __attribute__((packed)) {
    char     riff[4];
    uint32_t file_size;
    char     wave[4];
    char     fmt[4];
    uint32_t fmt_size;
    uint16_t audio_format;
    uint16_t num_channels;
    uint32_t sample_rate;
    uint32_t byte_rate;
    uint16_t block_align;
    uint16_t bits_per_sample;
    char     data[4];
    uint32_t data_size;
} wav_header_t;

static void spiffs_init(void) {
    esp_vfs_spiffs_conf_t conf = {
        .base_path              = "/spiffs",
        .partition_label        = NULL,
        .max_files              = 5,
        .format_if_mount_failed = true,
    };
    ESP_ERROR_CHECK(esp_vfs_spiffs_register(&conf));
    ESP_LOGI(TAG, "SPIFFS mounted");
    FILE *f = fopen("/spiffs/audio.wav", "rb");
    if (f) {
        ESP_LOGI(TAG, "audio.wav found");
        fclose(f);
    } else {
        ESP_LOGI(TAG, "audio.wav NOT found");
    }
}

static void servo_init(void)
{
    ledc_timer_config_t timer = {
        .speed_mode = LEDC_HIGH_SPEED_MODE,
        .duty_resolution = LEDC_TIMER_12_BIT,
        .timer_num = LEDC_TIMER_0,
        .freq_hz = 50,
        .clk_cfg = LEDC_AUTO_CLK
    };
    ledc_timer_config(&timer);

    ledc_channel_config_t channel = {
        .gpio_num = SERVO_PIN,
        .speed_mode = LEDC_HIGH_SPEED_MODE,
        .channel = LEDC_CHANNEL_0,
        .intr_type = LEDC_INTR_DISABLE,
        .timer_sel = LEDC_TIMER_0,
        .duty = 0,
        .hpoint = 0
    };
    ledc_channel_config(&channel);
}

static void digipot_init(void)
{
    spi_bus_config_t buscfg = {
        .mosi_io_num = PIN_NUM_MOSI,
        .miso_io_num = -1,
        .sclk_io_num = PIN_NUM_CLK,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
    };

    spi_device_interface_config_t devcfg = {
        .clock_speed_hz = 100 * 1000, // 100 kHz
        .command_bits = 0,
        .address_bits = 0,
        .mode = 0,                         // SPI mode 0
        .spics_io_num = PIN_NUM_CS,
        .queue_size = 1,
    };

    spi_bus_initialize(SPI2_HOST, &buscfg, SPI_DMA_CH_AUTO);
    spi_bus_add_device(SPI2_HOST, &devcfg, &tpl_spi);
}

void digipot_set_position(uint8_t pos)
{
    if (pos > 255) pos = 255;

    uint8_t data = pos;

    spi_transaction_t t = {
        .length = 8, // bits
        .rx_buffer = NULL,
        .tx_buffer = &data,
    };

    spi_device_transmit(tpl_spi, &t);

    char buf[64];
    snprintf(buf, sizeof(buf), "digipot set to %d\r\n", pos);
    uart_print(buf);
}
/* ================= SERVO TASK ================= */
static void servo_task(void *arg) {
    bool cmd;
    bool zero = true;

    while (1) {
        if (xQueueReceive(servo_queue, &cmd, portMAX_DELAY)) {
            if (zero) {
                uart_print("Servo moving to max\r\n");
                ledc_set_duty(LEDC_HIGH_SPEED_MODE, LEDC_CHANNEL_0, angle_to_duty_cycle(180));
                ledc_update_duty(LEDC_HIGH_SPEED_MODE, LEDC_CHANNEL_0);
                vTaskDelay(pdMS_TO_TICKS(1000));
                uart_print("Servo at max\r\n");
                zero = false;
            } else {
                uart_print("Servo moving to min\r\n");
                ledc_set_duty(LEDC_HIGH_SPEED_MODE, LEDC_CHANNEL_0, angle_to_duty_cycle(0));
                ledc_update_duty(LEDC_HIGH_SPEED_MODE, LEDC_CHANNEL_0);
                vTaskDelay(pdMS_TO_TICKS(1000));
                uart_print("Servo at min\r\n");
                zero = true;
            }
            uart_print("Servo done\r\n");
        }
    }
}

static void audio_task(void *arg) {
    bool cmd;

    while (1) {
        if (xQueueReceive(audio_queue, &cmd, portMAX_DELAY)) {

            FILE *f = fopen(WAV_FILE_PATH, "rb");
            if (!f) { uart_print("ERR: no wav file\r\n"); continue; }

            wav_header_t hdr;
            fread(&hdr, sizeof(hdr), 1, f);

            if (strncmp(hdr.riff, "RIFF", 4) || strncmp(hdr.wave, "WAVE", 4) || hdr.audio_format != 1) {
                uart_print("ERR: bad wav\r\n");
                fclose(f);
                continue;
            }

            i2s_config_t i2s_cfg = {
                .mode                 = I2S_MODE_MASTER | I2S_MODE_TX | I2S_MODE_DAC_BUILT_IN,
                .sample_rate          = hdr.sample_rate,
                .bits_per_sample      = I2S_BITS_PER_SAMPLE_16BIT,
                .channel_format       = I2S_CHANNEL_FMT_ONLY_RIGHT,
                .communication_format = I2S_COMM_FORMAT_STAND_MSB,
                .intr_alloc_flags     = ESP_INTR_FLAG_LEVEL1,
                .dma_buf_count        = 8,
                .dma_buf_len          = 1024,
                .use_apll             = false,
                .tx_desc_auto_clear   = true,
            };
            i2s_driver_install(I2S_NUM, &i2s_cfg, 0, NULL);
            i2s_set_dac_mode(I2S_DAC_CHANNEL_RIGHT_EN);

            // i2s_set_clk(I2S_NUM,
            // hdr.sample_rate,
            // I2S_BITS_PER_SAMPLE_16BIT,
            // I2S_CHANNEL_MONO);

            uart_print("Playing audio\r\n");

            static uint8_t  buf[READ_BUF_SIZE];
            static uint16_t buf16[READ_BUF_SIZE];
            size_t written;

            while (true) {
                int n = fread(buf, 1, sizeof(buf), f);
                if (n <= 0) break;

                if (hdr.bits_per_sample == 16) {
                    int samples = n / 2;
                    int16_t *s16 = (int16_t *)buf;
                    for (int i = 0; i < samples; i++) {
                        // Convert signed 16-bit to unsigned 8-bit for DAC
                        buf16[i] = (uint16_t)((s16[i] + 32768) >> 8) << 8;
                    }
                    i2s_write(I2S_NUM, buf16, samples * 2, &written, portMAX_DELAY);
                } else {
                    // 8-bit unsigned, shift up for DAC
                    for (int i = 0; i < n; i++) buf16[i] = (uint16_t)buf[i] << 8;
                    i2s_write(I2S_NUM, buf16, n * 2, &written, portMAX_DELAY);
                }
            }

            fclose(f);
            i2s_zero_dma_buffer(I2S_NUM);
            i2s_driver_uninstall(I2S_NUM);
            uart_print("Audio done\r\n");
        }
    }
}

static void digipot_task(void *arg) {
    uint8_t pos;

    while (1) {
        if (xQueueReceive(digipot_queue, &pos, portMAX_DELAY)) {
            digipot_set_position(pos);
            uart_print("digipot done\r\n");
        }
    }
}

typedef enum {
    UART_STATE_MENU,
    UART_STATE_digipot_INPUT
} uart_state_t;

static void uart_rx_task(void *arg) {
    uart_event_t event;
    uint8_t rx[UART_BUF];
    char line[32];
    int idx = 0;
    uart_state_t state = UART_STATE_MENU;

    while (1) {
        if (xQueueReceive(uart_event_queue, &event, portMAX_DELAY)) {
            if (event.type != UART_DATA) continue;

            int len = uart_read_bytes(UART_NUM, rx, event.size, pdMS_TO_TICKS(10));

            for (int i = 0; i < len; i++) {
                char c = rx[i];

                // End-of-line received
                if (c == '\r' || c == '\n') {
                    if (idx == 0) continue; // ignore empty lines
                    line[idx] = '\0';
                    idx = 0;

                    char dbg[64];
                    snprintf(dbg, sizeof(dbg), "DEBUG: line='%s', state=%d\r\n", line, state);
                    uart_print(dbg);

                    if (state == UART_STATE_MENU) {
                        // Menu commands
                        if (strcmp(line, "1") == 0) {
                            bool cmd = true;
                            if (xQueueSend(servo_queue, &cmd, 0)) uart_print("OK: servo\r\n");
                            else uart_print("BUSY\r\n");
                        } else if (strcmp(line, "2") == 0) {
                            if (xQueueSend(audio_queue, &(bool){true}, 0)) uart_print("OK: audio\r\n");
                            else uart_print("BUSY\r\n");
                        } else if (strcmp(line, "3") == 0) {
                            uart_print("OK: digipot\r\nEnter digipot position (0-255): \r\n");
                            state = UART_STATE_digipot_INPUT;
                        } else if (strcmp(line, "4") == 0) {
                            static bool ldo_on = false;
                            ldo_on = !ldo_on;
                            gpio_set_level(LASER_LDO_ENABLE, ldo_on ? 1 : 0);
                            if (ldo_on) uart_print("Laser Power Set Ready\r\n");
                            else uart_print("Laser Power Disabled\r\n");
                        } else if (strcmp(line, "5") == 0) {
                            static bool laser_on = false;
                            laser_on = !laser_on;
                            gpio_set_level(LASER_ENABLE, laser_on ? 1 : 0);
                            if (laser_on) uart_print("Laser Emission Enabled\r\n");
                            else uart_print("Laser Emission Disabled\r\n");
                       } else if (strcmp(line, "9") == 0) {
                            static bool fan_set = true;
                            fan_set = !fan_set;
                            gpio_set_level(FAN_ENABLE, fan_set ? 0 : 1);
                            if (fan_set) uart_print("Fans Disabled\r\n");
                            else uart_print("Fans Enabled\r\n");
                        }                         
                    }
                    else if (state == UART_STATE_digipot_INPUT) {
                        // Numeric input for digipot    
                        char clean_line[16];
                        int j = 0;
                        for (int k = 0; k < (int)strlen(line) && j < (int)sizeof(clean_line)-1; k++) {
                            if (line[k] >= '0' && line[k] <= '9') clean_line[j++] = line[k];
                        }
                        clean_line[j] = '\0';

                        if (clean_line[0] == '\0') {
                            uart_print("Invalid input, must be 0-255\r\n");
                        } else {
                            uint8_t pos = (uint8_t)atoi(clean_line);
                            if (pos > DIGIPOT_MAX_POS) pos = DIGIPOT_MAX_POS;

                            if (xQueueSend(digipot_queue, &pos, 0)) {
                                char msg[64];
                                snprintf(msg, sizeof(msg), "Queued digipot pos %d\r\n", pos);
                                uart_print(msg);
                            } else {
                                uart_print("digipot BUSY\r\n");
                            }
                        }

                        // Return to menu state
                        state = UART_STATE_MENU;
                    }
                }
                // Normal character
                else if (idx < (int)sizeof(line)-1) {
                    line[idx++] = c;
                } else {
                    // Overflow
                    uart_print("Line too long, input ignored\r\n");
                    idx = 0;
                }
            }
        }
    }
}

void app_main(void) {

    servo_queue = xQueueCreate(1, sizeof(bool));
    audio_queue = xQueueCreate(1, sizeof(bool));
    digipot_queue   = xQueueCreate(1, sizeof(uint8_t));
    uart_mutex  = xSemaphoreCreateMutex();
    ESP_LOGI(TAG, "queues ok");

    // UART init
    uart_config_t cfg = {
        .baud_rate  = 115200,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE
    };

    gpio_config_t fan_cfg = {
        .pin_bit_mask = ((1ULL << FAN_ENABLE) | (1ULL << LASER_ENABLE) | (1ULL << LASER_LDO_ENABLE)),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE
    };
    gpio_config(&fan_cfg); 
    gpio_set_level(FAN_ENABLE, 0); // Start with fan on
    gpio_set_level(LASER_LDO_ENABLE, 0); //Laser modulation disabled
    gpio_set_level(LASER_ENABLE, 0); // Laser disabled

    uart_driver_install(UART_NUM, UART_BUF * 2, 0, 10, &uart_event_queue, 0);
    uart_param_config(UART_NUM, &cfg);
    uart_set_pin(UART_NUM, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    ESP_LOGI(TAG, "uart ok");

    spiffs_init();
    ESP_LOGI(TAG, "spiffs ok");

    servo_init();
    ESP_LOGI(TAG, "servo ok");

    digipot_init();
    digipot_set_position(255);
    ESP_LOGI(TAG, "digipot ok");

    xTaskCreate(uart_rx_task, "uart_rx", 4096,  NULL, 10, NULL);
    xTaskCreate(servo_task,   "servo",   4096,  NULL,  9, NULL);
    xTaskCreate(digipot_task, "digipot", 4096,  NULL,  9, NULL);
    xTaskCreatePinnedToCore(audio_task, "audio", 8192, NULL, 8, NULL, 1);
    ESP_LOGI(TAG, "tasks ok");
}