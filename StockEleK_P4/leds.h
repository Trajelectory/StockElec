#pragma once
#include <Arduino.h>
#include <FastLED.h>
#include "pins_config.h"

// ─────────────────────────────────────────────────────────────────────
//  Tableaux LEDs
// ─────────────────────────────────────────────────────────────────────
static CRGB leds_positions[NUM_LEDS];    // ruban emplacements
static CRGB leds_drawers[NUM_DRAWERS];   // ruban tiroirs

static int  g_active_led_index  = -1;
static int  g_active_drawer_idx = -1;
static uint32_t g_led_off_time  = 0;
static uint32_t g_led_duration  = 5000;  // ms

// ─────────────────────────────────────────────────────────────────────
//  Init
// ─────────────────────────────────────────────────────────────────────
void leds_init() {
    FastLED.addLeds<WS2812B, LED_PIN,    GRB>(leds_positions, NUM_LEDS);
    FastLED.addLeds<WS2812B, DRAWER_PIN, GRB>(leds_drawers,   NUM_DRAWERS);
    FastLED.setBrightness(LED_BRIGHTNESS);
    FastLED.clear(true);
}

// ─────────────────────────────────────────────────────────────────────
//  Parse un emplacement type "A07" → lettre + numéro
//  Retourne false si invalide
// ─────────────────────────────────────────────────────────────────────
bool parseLocation(const char *loc, int &drawer_idx, int &pos_idx) {
    if (!loc || strlen(loc) < 2) return false;
    char letter = toupper(loc[0]);
    if (letter < 'A' || letter > 'Z') return false;
    int num = atoi(loc + 1);
    if (num < 1) return false;
    drawer_idx = letter - 'A';          // A=0, B=1 …
    pos_idx    = (drawer_idx * 20) + (num - 1); // 20 cases par tiroir
    if (pos_idx >= NUM_LEDS) return false;
    return true;
}

// ─────────────────────────────────────────────────────────────────────
//  Allume la LED d'un emplacement (ex: "A07") avec une couleur
//  pendant 'duration_ms' millisecondes
// ─────────────────────────────────────────────────────────────────────
void leds_show(const char *location, CRGB color, uint32_t duration_ms = 5000) {
    // Éteindre les LEDs précédentes
    FastLED.clear(true);

    int drawer_idx, pos_idx;
    if (!parseLocation(location, drawer_idx, pos_idx)) return;

    // Allumer la LED de position
    leds_positions[pos_idx] = color;

    // Allumer la LED du tiroir
    leds_drawers[drawer_idx] = color;

    FastLED.show();

    g_active_led_index  = pos_idx;
    g_active_drawer_idx = drawer_idx;
    g_led_duration      = duration_ms;
    g_led_off_time      = millis() + duration_ms;
}

// ─────────────────────────────────────────────────────────────────────
//  Éteindre toutes les LEDs
// ─────────────────────────────────────────────────────────────────────
void leds_off() {
    FastLED.clear(true);
    g_active_led_index  = -1;
    g_active_drawer_idx = -1;
    g_led_off_time      = 0;
}

// ─────────────────────────────────────────────────────────────────────
//  À appeler dans loop() — gère l'extinction automatique
// ─────────────────────────────────────────────────────────────────────
void leds_update() {
    if (g_led_off_time > 0 && millis() >= g_led_off_time) {
        leds_off();
    }
}

// ─────────────────────────────────────────────────────────────────────
//  Couleur selon la catégorie (même logique que StockElec)
// ─────────────────────────────────────────────────────────────────────
CRGB colorForCategory(const char *category) {
    if (!category) return CRGB::White;
    String cat = String(category);
    cat.toLowerCase();
    if (cat.indexOf("resist") >= 0)   return CRGB(255, 100,   0);  // orange
    if (cat.indexOf("capac")  >= 0)   return CRGB(  0, 100, 255);  // bleu
    if (cat.indexOf("transis") >= 0)  return CRGB(  0, 200,  50);  // vert
    if (cat.indexOf("diode")  >= 0)   return CRGB(255, 255,   0);  // jaune
    if (cat.indexOf("led")    >= 0)   return CRGB(255, 255,   0);
    if (cat.indexOf("ic")     >= 0)   return CRGB(150,   0, 255);  // violet
    if (cat.indexOf("connec") >= 0)   return CRGB(255,  50,  50);  // rouge
    if (cat.indexOf("inductor") >= 0) return CRGB(  0, 255, 200);  // cyan
    return CRGB::White;
}
