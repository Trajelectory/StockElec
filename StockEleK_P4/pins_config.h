#pragma once

// ── Écran MIPI DSI ST7701 ──────────────────────────────────────────
#define LCD_H_RES   480
#define LCD_V_RES   800
#define LCD_RST     -1
#define LCD_LED     -1

// ── Tactile GT911 ──────────────────────────────────────────────────
#define TP_I2C_SDA  7
#define TP_I2C_SCL  8
#define TP_RST      -1
#define TP_INT      -1

// ── LEDs WS2812B (sur connecteur JP1) ─────────────────────────────
// Ruban 1 : emplacements (cases A01, B03…) → JP1 pin 15/16
#define LED_PIN         29
#define NUM_LEDS        500

// Ruban 2 : tiroirs (lettre A-Z) → JP1 pin 11/12
#define DRAWER_PIN      31
#define NUM_DRAWERS     26

// ── Luminosité LEDs ────────────────────────────────────────────────
#define LED_BRIGHTNESS  180   // 0-255

// ── WiFi ───────────────────────────────────────────────────────────
#define WIFI_SSID       "slyhome"
#define WIFI_PASSWORD   "vivelewifi2016vivemoi"

// ── StockElec serveur ──────────────────────────────────────────────
#define STOCKELEC_HOST  "192.168.1.48"   // IP du PC avec StockElec
#define STOCKELEC_PORT  5000
#define STOCKELEC_TOKEN "stockelek-secret"

// ── LVGL ───────────────────────────────────────────────────────────
#define EXAMPLE_LVGL_PORT_TASK_MAX_DELAY_MS  500
#define EXAMPLE_LVGL_PORT_TASK_MIN_DELAY_MS  5
#define EXAMPLE_LVGL_PORT_TASK_PRIORITY      4
#define EXAMPLE_LVGL_PORT_TASK_STACK_SIZE_KB 8
#define EXAMPLE_LVGL_PORT_TASK_CORE          1
#define EXAMPLE_LVGL_PORT_TICK               2
