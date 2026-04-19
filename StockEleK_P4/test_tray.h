#pragma once
#include <Arduino.h>
#include <FastLED.h>
#include "lvgl.h"
#include "leds.h"
#include "pins_config.h"

// Pointeur vers le mutex LVGL — initialisé depuis setup() via test_tray_set_mutex()
static SemaphoreHandle_t *_test_lvgl_mux = nullptr;
inline void test_tray_set_mutex(SemaphoreHandle_t *mux) { _test_lvgl_mux = mux; }

static lv_obj_t *test_overlay    = NULL;
static lv_obj_t *test_lbl_title  = NULL;
static lv_obj_t *test_lbl_ruban  = NULL;
static lv_obj_t *test_lbl_index  = NULL;
static lv_obj_t *test_bar        = NULL;
static lv_obj_t *test_lbl_pct    = NULL;


// ─────────────────────────────────────────────────────────────────────
//  Construit l'overlay de test (appelé une seule fois)
// ─────────────────────────────────────────────────────────────────────
static void test_ui_build(lv_obj_t *screen)
{
    if (test_overlay) return;   // déjà construit

    // Fond semi-transparent plein écran
    test_overlay = lv_obj_create(screen);
    lv_obj_set_size(test_overlay, 800, 480);
    lv_obj_set_pos(test_overlay, 0, 0);
    lv_obj_set_style_bg_color(test_overlay, lv_color_hex(0x060810), 0);
    lv_obj_set_style_bg_opa(test_overlay, LV_OPA_90, 0);
    lv_obj_set_style_border_width(test_overlay, 0, 0);
    lv_obj_set_style_pad_all(test_overlay, 0, 0);
    lv_obj_set_flex_flow(test_overlay, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(test_overlay, LV_FLEX_ALIGN_CENTER,
                           LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_gap(test_overlay, 20, 0);

    // Titre
    test_lbl_title = lv_label_create(test_overlay);
    lv_label_set_text(test_lbl_title, "TEST RUBAN LED");
    lv_obj_set_style_text_color(test_lbl_title, lv_color_hex(0x3a8fff), 0);
    lv_obj_set_style_text_font(test_lbl_title, &lv_font_montserrat_28, 0);

    // Nom du ruban en cours
    test_lbl_ruban = lv_label_create(test_overlay);
    lv_label_set_text(test_lbl_ruban, "Tiroirs");
    lv_obj_set_style_text_color(test_lbl_ruban, lv_color_hex(0x8a9ab0), 0);
    lv_obj_set_style_text_font(test_lbl_ruban, &lv_font_montserrat_16, 0);

    // Index / case en cours
    test_lbl_index = lv_label_create(test_overlay);
    lv_label_set_text(test_lbl_index, "---");
    lv_obj_set_style_text_color(test_lbl_index, lv_color_hex(0xdde4f0), 0);
    lv_obj_set_style_text_font(test_lbl_index, &lv_font_montserrat_48, 0);

    // Barre de progression
    test_bar = lv_bar_create(test_overlay);
    lv_obj_set_size(test_bar, 600, 20);
    lv_bar_set_range(test_bar, 0, 100);
    lv_bar_set_value(test_bar, 0, LV_ANIM_OFF);
    lv_obj_set_style_bg_color(test_bar, lv_color_hex(0x1a2535), 0);
    lv_obj_set_style_bg_color(test_bar, lv_color_hex(0x3a8fff), LV_PART_INDICATOR);
    lv_obj_set_style_radius(test_bar, 10, 0);
    lv_obj_set_style_radius(test_bar, 10, LV_PART_INDICATOR);

    // Pourcentage
    test_lbl_pct = lv_label_create(test_overlay);
    lv_label_set_text(test_lbl_pct, "0%");
    lv_obj_set_style_text_color(test_lbl_pct, lv_color_hex(0x3a5a7a), 0);
    lv_obj_set_style_text_font(test_lbl_pct, &lv_font_montserrat_14, 0);

    // Caché par défaut
    lv_obj_add_flag(test_overlay, LV_OBJ_FLAG_HIDDEN);
}

// ─────────────────────────────────────────────────────────────────────
//  Met à jour l'affichage pendant le test
// ─────────────────────────────────────────────────────────────────────
static void test_ui_update(const char *ruban, const char *index_str,
                            int progress_pct, lv_color_t color)
{
    if (!test_overlay) return;
    if (_test_lvgl_mux && xSemaphoreTake(*_test_lvgl_mux, pdMS_TO_TICKS(30))) {
        lv_obj_remove_flag(test_overlay, LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text(test_lbl_ruban, ruban);
        lv_label_set_text(test_lbl_index, index_str);
        lv_bar_set_value(test_bar, progress_pct, LV_ANIM_OFF);
        // Couleur dynamique du titre selon la couleur LED
        lv_obj_set_style_text_color(test_lbl_index, color, 0);
        char pct_buf[8];
        snprintf(pct_buf, sizeof(pct_buf), "%d%%", progress_pct);
        lv_label_set_text(test_lbl_pct, pct_buf);
        lv_timer_handler();
        xSemaphoreGive(*_test_lvgl_mux);
    }
}

static void test_ui_hide()
{
    if (!test_overlay) return;
    if (_test_lvgl_mux && xSemaphoreTake(*_test_lvgl_mux, pdMS_TO_TICKS(50))) {
        lv_obj_add_flag(test_overlay, LV_OBJ_FLAG_HIDDEN);
        lv_timer_handler();
        xSemaphoreGive(*_test_lvgl_mux);
    }
}

// ─────────────────────────────────────────────────────────────────────
//  Tâche de test — tourne sur core 0 pour ne pas bloquer l'UI
// ─────────────────────────────────────────────────────────────────────
struct TestParams {
    uint32_t delay_ms;
    CRGB     color;
    int      offset;      // offset LED emplacements (0 par défaut)
    int      count;       // nb LEDs emplacements à tester (0 = NUM_LEDS)
};

static void taskTest(void *arg)
{
    TestParams *p = (TestParams *)arg;
    uint32_t delay_ms = p->delay_ms;
    CRGB     color    = p->color;
    int      offset   = p->offset;
    int      count    = (p->count > 0) ? p->count : NUM_LEDS;
    delete p;

    int total = NUM_DRAWERS + count;

    // ── Phase 1 : Ruban tiroirs (A à Z) ─────────────────────────────
    FastLED.clear(true);
    for (int i = 0; i < NUM_DRAWERS; i++) {
        // Éteindre LED précédente
        if (i > 0) leds_drawers[i - 1] = CRGB::Black;
        leds_drawers[i] = color;
        FastLED.show();

        char letter[4];
        snprintf(letter, sizeof(letter), "%c", 'A' + i);
        int pct = (i * 100) / total;
        test_ui_update("Tiroirs", letter, pct, lv_color_hex(
            ((color.r & 0xFF) << 16) | ((color.g & 0xFF) << 8) | (color.b & 0xFF)
        ));

        vTaskDelay(pdMS_TO_TICKS(delay_ms));
    }
    // Éteindre dernier tiroir
    leds_drawers[NUM_DRAWERS - 1] = CRGB::Black;
    FastLED.show();

    // ── Phase 2 : Ruban emplacements ────────────────────────────────
    for (int i = 0; i < count; i++) {
        int led_idx = offset + i;
        if (led_idx >= NUM_LEDS) break;

        if (i > 0) leds_positions[offset + i - 1] = CRGB::Black;
        leds_positions[led_idx] = color;
        FastLED.show();

        // Calcul case : tiroir A = 0-19, B = 20-39 …
        int drawer_idx = i / 20;
        int case_num   = (i % 20) + 1;
        char case_str[8];
        snprintf(case_str, sizeof(case_str), "%c%02d", 'A' + drawer_idx, case_num);

        int pct = ((NUM_DRAWERS + i) * 100) / total;
        test_ui_update("Emplacements", case_str, pct, lv_color_hex(
            ((color.r & 0xFF) << 16) | ((color.g & 0xFF) << 8) | (color.b & 0xFF)
        ));

        vTaskDelay(pdMS_TO_TICKS(delay_ms));
    }

    // ── Fin : tout éteindre + message ───────────────────────────────
    FastLED.clear(true);

    // Afficher "Terminé" 1 seconde
    if (_test_lvgl_mux && xSemaphoreTake(*_test_lvgl_mux, pdMS_TO_TICKS(100))) {
        lv_bar_set_value(test_bar, 100, LV_ANIM_OFF);
        lv_label_set_text(test_lbl_index, "OK !");
        lv_label_set_text(test_lbl_ruban, "Test terminé");
        lv_label_set_text(test_lbl_pct, "100%");
        lv_obj_set_style_text_color(test_lbl_index, lv_color_hex(0x2aaa50), 0);
        lv_timer_handler();
        xSemaphoreGive(*_test_lvgl_mux);
    }
    vTaskDelay(pdMS_TO_TICKS(1500));

    test_ui_hide();
    vTaskDelete(NULL);
}

// ─────────────────────────────────────────────────────────────────────
//  Lancer un test depuis la route HTTP
//  delay_ms : délai entre chaque LED (défaut 80ms)
//  color_str : couleur hex "#RRGGBB" (défaut blanc)
//  offset    : première LED emplacement à tester
//  count     : nombre de LEDs emplacements (0 = toutes)
// ─────────────────────────────────────────────────────────────────────
void run_test(uint32_t delay_ms, const char *color_str,
              int offset = 0, int count = 0)
{
    // Construire la couleur
    long hex   = strtol(color_str[0] == '#' ? color_str + 1 : color_str, NULL, 16);
    CRGB color = CRGB((hex >> 16) & 0xFF, (hex >> 8) & 0xFF, hex & 0xFF);
    if (color.r == 0 && color.g == 0 && color.b == 0)
        color = CRGB::White;

    TestParams *p = new TestParams{delay_ms, color, offset, count};
    xTaskCreatePinnedToCore(taskTest, "LED_TEST", 4096, p, 3, NULL, 0);
}
