/*
 * StockEleK — Firmware ESP32-P4 (GUITION JC4880P443C-I-W-Y)
 * LVGL v9 / esp32-arduino v3.3.x
 */

#pragma GCC push_options
#pragma GCC optimize("O3")

#include <Arduino.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_timer.h"
#include "driver/i2c_master.h"
#include "esp_lcd_mipi_dsi.h"
#include "lvgl.h"
#include "WiFi.h"
#include "WebServer.h"
#include <ArduinoJson.h>

#include "pins_config.h"
#include "src/lcd/st7701_lcd.h"
#include "src/touch/gt911_touch.h"
#include "leds.h"
#include "stockelec_api.h"
#include "test_tray.h"
#include "ui.h"

static bsp_lcd_handles_t lcd_panels;
static st7701_lcd  lcd   = st7701_lcd(LCD_RST);
static gt911_touch touch = gt911_touch(TP_I2C_SDA, TP_I2C_SCL, TP_RST, TP_INT);

static lv_display_t *g_display = NULL;
static lv_indev_t   *g_indev   = NULL;
static lv_color_t   *buf1      = NULL;
static lv_color_t   *buf2      = NULL;

static SemaphoreHandle_t lvgl_mux = NULL;
static WebServer         server(80);

static Component      g_comp;
static volatile bool  g_comp_dirty = false;

// ── LVGL v9 flush callback ────────────────────────────────────────────
static bool lvgl_flush_ready_cb(esp_lcd_panel_handle_t panel_io,
                                 esp_lcd_dpi_panel_event_data_t *edata,
                                 void *user_ctx)
{
    lv_display_flush_ready((lv_display_t *)user_ctx);
    return false;
}

static void my_disp_flush(lv_display_t *disp,
                           const lv_area_t *area,
                           uint8_t *px_map)
{
    lcd.lcd_draw_bitmap(area->x1, area->y1,
                        area->x2 + 1, area->y2 + 1,
                        (uint16_t *)px_map);
}

// ── Touch callback ────────────────────────────────────────────────────
static void my_touchpad_read(lv_indev_t *indev, lv_indev_data_t *data)
{
    uint16_t tx, ty;
    if (touch.getTouch(&tx, &ty)) {
        data->state   = LV_INDEV_STATE_PRESSED;
        data->point.x = ty;
        data->point.y = LCD_H_RES - tx;
    } else {
        data->state = LV_INDEV_STATE_RELEASED;
    }
}

// ── Timer tick ────────────────────────────────────────────────────────
static void lvgl_tick_cb(void *arg) { lv_tick_inc(2); }

// ── Callback Confirmer ────────────────────────────────────────────────
static void cb_confirm(lv_event_t *e)
{
    if (g_current_comp_id < 0 || g_pending_delta == 0) return;
    int new_qty = 0;
    bool ok = adjustQuantity(g_current_comp_id, g_pending_delta, new_qty);
    lv_obj_t *lbl_conf = lv_obj_get_child(btn_confirm, 0);
    if (ok) {
        g_current_qty = new_qty; g_pending_delta = 0;
        char buf[8]; snprintf(buf, sizeof(buf), "%d", new_qty);
        lv_label_set_text(lbl_qty, buf);
        lv_label_set_text(lbl_conf, LV_SYMBOL_OK " Envoye !");
        lv_obj_set_style_text_color(lbl_conf, lv_color_hex(0x2aaa50), 0);
    } else {
        lv_label_set_text(lbl_conf, "Erreur reseau");
        lv_obj_set_style_text_color(lbl_conf, lv_color_hex(0xcc4444), 0);
    }
    lv_timer_t *t = lv_timer_create([](lv_timer_t *timer) {
        lv_obj_add_flag(btn_confirm, LV_OBJ_FLAG_HIDDEN);
        lv_obj_t *lbl = lv_obj_get_child(btn_confirm, 0);
        lv_label_set_text(lbl, "Confirmer");
        lv_obj_set_style_text_color(lbl, lv_color_hex(0x3a7acc), 0);
        lv_timer_delete(timer);
    }, 2000, NULL);
    (void)t;
}

// ── Routes HTTP ───────────────────────────────────────────────────────
void handle_led()
{
    if (!server.hasArg("plain")) { server.send(400); return; }
    JsonDocument doc;
    if (deserializeJson(doc, server.arg("plain"))) { server.send(400); return; }

    const char *cell      = doc["cell"]         | "";
    uint32_t    duration  = doc["duration"]      | 5;
    int         comp_id   = doc["component_id"]  | -1;
    const char *color_str = doc["color"]         | "#ffffff";

    long hex   = strtol(color_str + (color_str[0]=='#' ? 1 : 0), NULL, 16);
    CRGB color = CRGB((hex>>16)&0xFF, (hex>>8)&0xFF, hex&0xFF);

    leds_show(cell, color, duration * 1000UL);

    if (comp_id > 0 && fetchComponent(comp_id, g_comp))
        g_comp_dirty = true;

    if (xSemaphoreTake(lvgl_mux, pdMS_TO_TICKS(50))) {
        ui_set_led_active(true);
        xSemaphoreGive(lvgl_mux);
    }
    server.send(200, "application/json", "{\"ok\":true}");
}

void handle_off()
{
    leds_off();
    if (xSemaphoreTake(lvgl_mux, pdMS_TO_TICKS(50))) {
        ui_set_led_active(false);
        xSemaphoreGive(lvgl_mux);
    }
    server.send(200, "application/json", "{\"ok\":true}");
}

void handle_ping()
{
    char buf[80];
    snprintf(buf, sizeof(buf), "{\"ok\":true,\"display\":true,\"uptime\":%lu}", millis()/1000);
    server.send(200, "application/json", buf);
}

void handle_status()
{
    char buf[200];
    snprintf(buf, sizeof(buf),
             "{\"ok\":true,\"active\":%s,\"component_id\":%d,\"uptime\":%lu,\"ip\":\"%s\"}",
             g_led_off_time > 0 ? "true" : "false",
             g_current_comp_id, millis()/1000,
             WiFi.localIP().toString().c_str());
    server.send(200, "application/json", buf);
}

// POST /test — chenillard tiroirs puis emplacements
void handle_test()
{
    uint32_t delay_ms = 80;
    char     color_buf[16] = "#ffffff";
    int      offset = 0, count = 0;

    if (server.hasArg("plain")) {
        JsonDocument doc;
        if (!deserializeJson(doc, server.arg("plain"))) {
            delay_ms = doc["delay_ms"] | 80;
            strlcpy(color_buf, doc["color"] | "#ffffff", sizeof(color_buf));
            offset = doc["offset"] | 0;
            count  = doc["count"]  | 0;
        }
    }

    // Construire l'overlay si nécessaire
    if (xSemaphoreTake(lvgl_mux, pdMS_TO_TICKS(100))) {
        test_ui_build(lv_screen_active());
        xSemaphoreGive(lvgl_mux);
    }

    run_test(delay_ms, color_buf, offset, count);

    char resp[80];
    snprintf(resp, sizeof(resp),
             "{\"ok\":true,\"delay_ms\":%lu,\"color\":\"%s\"}", delay_ms, color_buf);
    server.send(200, "application/json", resp);
}

// ── Tâche HTTP (core 0) ───────────────────────────────────────────────
void taskHTTP(void *arg)
{
    server.on("/led",    HTTP_POST, handle_led);
    server.on("/off",    HTTP_POST, handle_off);
    server.on("/ping",   HTTP_GET,  handle_ping);
    server.on("/status", HTTP_GET,  handle_status);
    server.on("/test",   HTTP_POST, handle_test);
    server.begin();
    Serial.printf("[HTTP] OK — IP: %s\n", WiFi.localIP().toString().c_str());
    while (true) { server.handleClient(); vTaskDelay(pdMS_TO_TICKS(2)); }
}

// ── WiFi ──────────────────────────────────────────────────────────────
void connectWiFi()
{
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    int n = 0;
    while (WiFi.status() != WL_CONNECTED && n++ < 30) { delay(500); Serial.print("."); }
    Serial.printf("\n[WiFi] %s\n",
        WiFi.status() == WL_CONNECTED
            ? WiFi.localIP().toString().c_str()
            : "Echec");
}

// ── SETUP ─────────────────────────────────────────────────────────────
void setup()
{
    Serial.begin(115200);
    Serial.println("=== StockEleK P4 ===");

    leds_init();

    i2c_master_bus_handle_t i2c_handle = NULL;
    i2c_master_bus_config_t i2c_conf = {
        .i2c_port = I2C_NUM_1,
        .sda_io_num = (gpio_num_t)TP_I2C_SDA,
        .scl_io_num = (gpio_num_t)TP_I2C_SCL,
        .clk_source = I2C_CLK_SRC_DEFAULT,
        .glitch_ignore_cnt = 7,
        .flags = { .enable_internal_pullup = 1 },
    };
    i2c_new_master_bus(&i2c_conf, &i2c_handle);

    lcd.begin();
    touch.begin();
    touch.set_rotation(1);
    lcd.get_handle(&lcd_panels);

    // LVGL v9
    lv_init();

    size_t buf_size = LCD_H_RES * LCD_V_RES * sizeof(lv_color_t);
    buf1 = (lv_color_t *)heap_caps_malloc(buf_size, MALLOC_CAP_SPIRAM);
    buf2 = (lv_color_t *)heap_caps_malloc(buf_size, MALLOC_CAP_SPIRAM);
    assert(buf1 && buf2);

    // Display en paysage 800×480
    g_display = lv_display_create(LCD_V_RES, LCD_H_RES);
    lv_display_set_buffers(g_display, buf1, buf2, buf_size,
                           LV_DISPLAY_RENDER_MODE_FULL);
    lv_display_set_flush_cb(g_display, my_disp_flush);
    lv_display_set_rotation(g_display, LV_DISPLAY_ROTATION_90);

    esp_lcd_dpi_panel_event_callbacks_t cbs = {};
    cbs.on_color_trans_done = lvgl_flush_ready_cb;
    esp_lcd_dpi_panel_register_event_callbacks(lcd_panels.panel, &cbs, g_display);

    // Touch
    g_indev = lv_indev_create();
    lv_indev_set_type(g_indev, LV_INDEV_TYPE_POINTER);
    lv_indev_set_read_cb(g_indev, my_touchpad_read);

    // Tick timer
    esp_timer_handle_t tick_timer;
    esp_timer_create_args_t tick_args = {
        .callback = lvgl_tick_cb,
        .name = "lvgl_tick",
        .skip_unhandled_events = true,
    };
    esp_timer_create(&tick_args, &tick_timer);
    esp_timer_start_periodic(tick_timer, 2000);

    lvgl_mux = xSemaphoreCreateMutex();
    test_tray_set_mutex(&lvgl_mux);

    // UI principale + overlay test
    if (xSemaphoreTake(lvgl_mux, portMAX_DELAY)) {
        ui_build(lv_screen_active());
        test_ui_build(lv_screen_active());
        xSemaphoreGive(lvgl_mux);
    }

    // WiFi
    if (xSemaphoreTake(lvgl_mux, pdMS_TO_TICKS(100))) {
        ui_show_status(lv_screen_active(), "Connexion WiFi...");
        lv_timer_handler();
        xSemaphoreGive(lvgl_mux);
    }

    connectWiFi();

    if (WiFi.status() == WL_CONNECTED) {
        if (xSemaphoreTake(lvgl_mux, pdMS_TO_TICKS(100))) {
            char ip[48];
            snprintf(ip, sizeof(ip), "StockEleK  %s", WiFi.localIP().toString().c_str());
            lv_label_set_text(lbl_appname, ip);
            xSemaphoreGive(lvgl_mux);
        }
        xTaskCreatePinnedToCore(taskHTTP, "HTTP", 8192, NULL, 5, NULL, 0);
    }

    Serial.println("[READY]");
}

// ── LOOP (core 1) ─────────────────────────────────────────────────────
void loop()
{
    leds_update();

    if (g_comp_dirty) {
        g_comp_dirty = false;
        if (xSemaphoreTake(lvgl_mux, pdMS_TO_TICKS(100))) {
            ui_update_component(g_comp);
            ui_set_led_active(g_led_off_time > 0);
            xSemaphoreGive(lvgl_mux);
        }
    }

    if (xSemaphoreTake(lvgl_mux, pdMS_TO_TICKS(10))) {
        lv_timer_handler();
        xSemaphoreGive(lvgl_mux);
    }

    delay(5);
}
