#pragma once
#include <Arduino.h>
#include "lvgl.h"
#include "stockelec_api.h"

// ─────────────────────────────────────────────────────────────────────
//  Palette de couleurs dark (cohérente avec le mockup)
// ─────────────────────────────────────────────────────────────────────
#define C_BG_DARK    lv_color_hex(0x080c14)
#define C_BG_MID     lv_color_hex(0x0d1117)
#define C_BG_LIGHT   lv_color_hex(0x111620)
#define C_BORDER     lv_color_hex(0x1e2330)
#define C_ACCENT     lv_color_hex(0x3a8fff)
#define C_TEXT       lv_color_hex(0xdde4f0)
#define C_TEXT_MED   lv_color_hex(0x8a9ab0)
#define C_TEXT_DIM   lv_color_hex(0x3a4a5a)
#define C_SUCCESS    lv_color_hex(0x2aaa50)
#define C_DANGER     lv_color_hex(0xcc4444)
#define C_WARNING    lv_color_hex(0xcc8844)
#define C_MONO       lv_color_hex(0x5a8ab8)

// ─────────────────────────────────────────────────────────────────────
//  Widgets globaux (mis à jour par ui_update_component)
// ─────────────────────────────────────────────────────────────────────
static lv_obj_t *ui_root         = NULL;

// Header
static lv_obj_t *lbl_name        = NULL;
static lv_obj_t *lbl_manuf       = NULL;
static lv_obj_t *lbl_lcsc        = NULL;
static lv_obj_t *lbl_rohs        = NULL;

// Colonne gauche
static lv_obj_t *lbl_sym_badge   = NULL;
static lv_obj_t *lbl_fp_badge    = NULL;
static lv_obj_t *lbl_3d_badge    = NULL;

// Colonne centrale
static lv_obj_t *lbl_desc        = NULL;
static lv_obj_t *lbl_freq        = NULL;
static lv_obj_t *lbl_pkg         = NULL;
static lv_obj_t *lbl_cat         = NULL;
static lv_obj_t *lbl_price       = NULL;
static lv_obj_t *lbl_total       = NULL;

// Colonne droite
static lv_obj_t *lbl_location    = NULL;
static lv_obj_t *lbl_loc_detail  = NULL;
static lv_obj_t *lbl_qty         = NULL;
static lv_obj_t *lbl_status      = NULL;
static lv_obj_t *btn_minus       = NULL;
static lv_obj_t *btn_plus        = NULL;
static lv_obj_t *btn_confirm     = NULL;
static lv_obj_t *lbl_led_active  = NULL;

// Footer
static lv_obj_t *lbl_breadcrumb  = NULL;
static lv_obj_t *lbl_appname     = NULL;

// État interne
static int g_current_comp_id   = -1;
static int g_current_qty       = 0;
static int g_pending_delta     = 0;
static int g_min_stock         = 0;
static float g_unit_price      = 0.0f;

// ─────────────────────────────────────────────────────────────────────
//  Helpers styles inline
// ─────────────────────────────────────────────────────────────────────
static inline void set_text_style(lv_obj_t *obj, lv_color_t color, const lv_font_t *font) {
    lv_obj_set_style_text_color(obj, color, 0);
    if (font) lv_obj_set_style_text_font(obj, font, 0);
}

static lv_obj_t* make_label(lv_obj_t *parent, const char *txt,
                              lv_color_t color, const lv_font_t *font = NULL) {
    lv_obj_t *lbl = lv_label_create(parent);
    lv_label_set_text(lbl, txt);
    lv_obj_set_style_text_color(lbl, color, 0);
    if (font) lv_obj_set_style_text_font(lbl, font, 0);
    return lbl;
}

static lv_obj_t* make_badge(lv_obj_t *parent, const char *txt,
                              lv_color_t bg, lv_color_t fg) {
    lv_obj_t *badge = lv_obj_create(parent);
    lv_obj_set_style_bg_color(badge, bg, 0);
    lv_obj_set_style_border_width(badge, 0, 0);
    lv_obj_set_style_pad_all(badge, 3, 0);
    lv_obj_set_style_radius(badge, 4, 0);
    lv_obj_t *lbl = lv_label_create(badge);
    lv_label_set_text(lbl, txt);
    lv_obj_set_style_text_color(lbl, fg, 0);
    lv_obj_set_style_text_font(lbl, &lv_font_montserrat_10, 0);
    lv_obj_center(lbl);
    return badge;
}

// ─────────────────────────────────────────────────────────────────────
//  Callbacks boutons +/-
// ─────────────────────────────────────────────────────────────────────
static void cb_minus(lv_event_t *e) {
    if (g_current_qty + g_pending_delta - 1 < 0) return;
    g_pending_delta--;
    int display_qty = g_current_qty + g_pending_delta;

    char buf[8];
    snprintf(buf, sizeof(buf), "%d", display_qty);
    lv_label_set_text(lbl_qty, buf);

    // Valeur totale
    char total[20];
    snprintf(total, sizeof(total), "%.2f EUR", display_qty * g_unit_price);
    lv_label_set_text(lbl_total, total);

    // Statut seuil
    if (display_qty == 0) {
        lv_label_set_text(lbl_status, "rupture !");
        lv_obj_set_style_text_color(lbl_status, C_DANGER, 0);
    } else if (display_qty <= g_min_stock) {
        lv_label_set_text(lbl_status, "stock bas !");
        lv_obj_set_style_text_color(lbl_status, C_WARNING, 0);
    } else {
        char s[20]; snprintf(s, sizeof(s), "min. %d", g_min_stock);
        lv_label_set_text(lbl_status, s);
        lv_obj_set_style_text_color(lbl_status, C_SUCCESS, 0);
    }

    lv_obj_remove_flag(btn_confirm, LV_OBJ_FLAG_HIDDEN);
}

static void cb_plus(lv_event_t *e) {
    g_pending_delta++;
    int display_qty = g_current_qty + g_pending_delta;

    char buf[8];
    snprintf(buf, sizeof(buf), "%d", display_qty);
    lv_label_set_text(lbl_qty, buf);

    char total[20];
    snprintf(total, sizeof(total), "%.2f EUR", display_qty * g_unit_price);
    lv_label_set_text(lbl_total, total);

    char s[20]; snprintf(s, sizeof(s), "min. %d", g_min_stock);
    lv_label_set_text(lbl_status, s);
    lv_obj_set_style_text_color(lbl_status, C_SUCCESS, 0);

    lv_obj_remove_flag(btn_confirm, LV_OBJ_FLAG_HIDDEN);
}

static void cb_confirm(lv_event_t *e);  // défini dans le .ino

// ─────────────────────────────────────────────────────────────────────
//  Construction de l'UI (appelée une seule fois dans setup)
// ─────────────────────────────────────────────────────────────────────
void ui_build(lv_obj_t *screen) {
    // Fond global
    lv_obj_set_style_bg_color(screen, C_BG_DARK, 0);
    lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, 0);
    lv_obj_set_style_pad_all(screen, 0, 0);

    // ── ROOT en paysage 800×480 ──────────────────────────────────────
    ui_root = lv_obj_create(screen);
    lv_obj_set_size(ui_root, 800, 480);
    lv_obj_set_style_bg_color(ui_root, C_BG_DARK, 0);
    lv_obj_set_style_border_width(ui_root, 0, 0);
    lv_obj_set_style_pad_all(ui_root, 0, 0);
    lv_obj_set_layout(ui_root, LV_LAYOUT_FLEX);
    lv_obj_set_flex_flow(ui_root, LV_FLEX_FLOW_COLUMN);

    // ── HEADER (hauteur 44px) ────────────────────────────────────────
    lv_obj_t *header = lv_obj_create(ui_root);
    lv_obj_set_size(header, 800, 44);
    lv_obj_set_style_bg_color(header, lv_color_hex(0x0a0e14), 0);
    lv_obj_set_style_border_width(header, 0, 0);
    lv_obj_set_style_border_side(header, LV_BORDER_SIDE_BOTTOM, 0);
    lv_obj_set_style_border_color(header, C_BORDER, LV_PART_MAIN);
    lv_obj_set_style_pad_hor(header, 16, 0);
    lv_obj_set_style_pad_ver(header, 6, 0);
    lv_obj_set_flex_flow(header, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(header, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);

    // Nom + fabricant (gauche)
    lv_obj_t *hdr_left = lv_obj_create(header);
    lv_obj_set_style_bg_opa(hdr_left, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(hdr_left, 0, 0);
    lv_obj_set_style_pad_all(hdr_left, 0, 0);
    lv_obj_set_flex_flow(hdr_left, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(hdr_left, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);
    lv_obj_set_size(hdr_left, LV_SIZE_CONTENT, LV_SIZE_CONTENT);

    lbl_name  = make_label(hdr_left, "---", C_TEXT, &lv_font_montserrat_16);
    lbl_manuf = make_label(hdr_left, "", C_TEXT_DIM, &lv_font_montserrat_10);

    // Badges droite
    lv_obj_t *hdr_right = lv_obj_create(header);
    lv_obj_set_style_bg_opa(hdr_right, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(hdr_right, 0, 0);
    lv_obj_set_style_pad_all(hdr_right, 0, 0);
    lv_obj_set_flex_flow(hdr_right, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(hdr_right, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_gap(hdr_right, 6, 0);
    lv_obj_set_size(hdr_right, LV_SIZE_CONTENT, LV_SIZE_CONTENT);

    lbl_lcsc = make_label(hdr_right, "---", C_MONO, &lv_font_montserrat_10);

    // ── BODY (flex row, remplit le reste) ───────────────────────────
    lv_obj_t *body = lv_obj_create(ui_root);
    lv_obj_set_size(body, 800, 400);
    lv_obj_set_style_bg_opa(body, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(body, 0, 0);
    lv_obj_set_style_pad_all(body, 0, 0);
    lv_obj_set_flex_flow(body, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(body, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);

    // ── COL GAUCHE (200px) — KiCad badges + refs ────────────────────
    lv_obj_t *col_left = lv_obj_create(body);
    lv_obj_set_size(col_left, 200, 400);
    lv_obj_set_style_bg_color(col_left, C_BG_LIGHT, 0);
    lv_obj_set_style_border_width(col_left, 1, 0);
    lv_obj_set_style_border_side(col_left, LV_BORDER_SIDE_RIGHT, 0);
    lv_obj_set_style_border_color(col_left, C_BORDER, 0);
    lv_obj_set_style_pad_all(col_left, 12, 0);
    lv_obj_set_flex_flow(col_left, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(col_left, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);
    lv_obj_set_style_pad_gap(col_left, 8, 0);

    // Titre KiCad
    make_label(col_left, "KICAD", C_TEXT_DIM, &lv_font_montserrat_10);

    // Badges KiCad (sym / fp / 3D)
    lv_obj_t *badges_row = lv_obj_create(col_left);
    lv_obj_set_size(badges_row, 176, LV_SIZE_CONTENT);
    lv_obj_set_style_bg_opa(badges_row, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(badges_row, 0, 0);
    lv_obj_set_style_pad_all(badges_row, 0, 0);
    lv_obj_set_flex_flow(badges_row, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_gap(badges_row, 4, 0);

    lbl_sym_badge = lv_label_create(badges_row);
    lv_label_set_text(lbl_sym_badge, "sym");
    lv_obj_set_style_text_font(lbl_sym_badge, &lv_font_montserrat_10, 0);

    lbl_fp_badge  = lv_label_create(badges_row);
    lv_label_set_text(lbl_fp_badge, "fp");
    lv_obj_set_style_text_font(lbl_fp_badge, &lv_font_montserrat_10, 0);

    lbl_3d_badge  = lv_label_create(badges_row);
    lv_label_set_text(lbl_3d_badge, "3D");
    lv_obj_set_style_text_font(lbl_3d_badge, &lv_font_montserrat_10, 0);

    // Description courte
    lbl_desc = lv_label_create(col_left);
    lv_label_set_text(lbl_desc, "");
    lv_obj_set_style_text_color(lbl_desc, C_TEXT_MED, 0);
    lv_obj_set_style_text_font(lbl_desc, &lv_font_montserrat_10, 0);
    lv_label_set_long_mode(lbl_desc, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(lbl_desc, 176);

    // Package
    lbl_pkg = make_label(col_left, "", C_MONO, &lv_font_montserrat_10);

    // ── COL CENTRALE (400px) — specs ─────────────────────────────────
    lv_obj_t *col_mid = lv_obj_create(body);
    lv_obj_set_size(col_mid, 400, 400);
    lv_obj_set_style_bg_opa(col_mid, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(col_mid, 0, 0);
    lv_obj_set_style_pad_all(col_mid, 14, 0);
    lv_obj_set_flex_flow(col_mid, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_gap(col_mid, 10, 0);

    make_label(col_mid, "SPECIFICATIONS", C_TEXT_DIM, &lv_font_montserrat_10);

    // Catégorie
    lbl_cat = lv_label_create(col_mid);
    lv_label_set_text(lbl_cat, "");
    lv_obj_set_style_text_color(lbl_cat, C_TEXT_MED, 0);
    lv_obj_set_style_text_font(lbl_cat, &lv_font_montserrat_10, 0);
    lv_label_set_long_mode(lbl_cat, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(lbl_cat, 372);

    // Prix unitaire + valeur stock
    lv_obj_t *price_row = lv_obj_create(col_mid);
    lv_obj_set_size(price_row, 372, LV_SIZE_CONTENT);
    lv_obj_set_style_bg_color(price_row, lv_color_hex(0x0a0e18), 0);
    lv_obj_set_style_border_width(price_row, 1, 0);
    lv_obj_set_style_border_color(price_row, C_BORDER, 0);
    lv_obj_set_style_radius(price_row, 6, 0);
    lv_obj_set_style_pad_all(price_row, 8, 0);
    lv_obj_set_flex_flow(price_row, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(price_row, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);

    lv_obj_t *price_left = lv_obj_create(price_row);
    lv_obj_set_style_bg_opa(price_left, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(price_left, 0, 0);
    lv_obj_set_style_pad_all(price_left, 0, 0);
    make_label(price_left, "Prix unit.", C_TEXT_DIM, &lv_font_montserrat_8);
    lbl_price = make_label(price_left, "---", C_TEXT, &lv_font_montserrat_16);

    lv_obj_t *price_right = lv_obj_create(price_row);
    lv_obj_set_style_bg_opa(price_right, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(price_right, 0, 0);
    lv_obj_set_style_pad_all(price_right, 0, 0);
    make_label(price_right, "Valeur stock", C_TEXT_DIM, &lv_font_montserrat_8);
    lbl_total = make_label(price_right, "---", C_ACCENT, &lv_font_montserrat_16);

    // ── COL DROITE (200px) — emplacement + contrôle stock ───────────
    lv_obj_t *col_right = lv_obj_create(body);
    lv_obj_set_size(col_right, 200, 400);
    lv_obj_set_style_bg_color(col_right, C_BG_MID, 0);
    lv_obj_set_style_border_width(col_right, 1, 0);
    lv_obj_set_style_border_side(col_right, LV_BORDER_SIDE_LEFT, 0);
    lv_obj_set_style_border_color(col_right, C_BORDER, 0);
    lv_obj_set_style_pad_all(col_right, 14, 0);
    lv_obj_set_flex_flow(col_right, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(col_right, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_gap(col_right, 10, 0);

    // Label "EMPLACEMENT"
    make_label(col_right, "EMPLACEMENT", C_TEXT_DIM, &lv_font_montserrat_8);

    // Zone emplacement avec bordure accent
    lv_obj_t *loc_box = lv_obj_create(col_right);
    lv_obj_set_size(loc_box, 172, 80);
    lv_obj_set_style_bg_color(loc_box, lv_color_hex(0x060f20), 0);
    lv_obj_set_style_border_width(loc_box, 2, 0);
    lv_obj_set_style_border_color(loc_box, C_ACCENT, 0);
    lv_obj_set_style_radius(loc_box, 10, 0);
    lv_obj_set_flex_flow(loc_box, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(loc_box, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);

    lbl_location = lv_label_create(loc_box);
    lv_label_set_text(lbl_location, "---");
    lv_obj_set_style_text_color(lbl_location, C_ACCENT, 0);
    lv_obj_set_style_text_font(lbl_location, &lv_font_montserrat_48, 0);

    lbl_loc_detail = lv_label_create(col_right);
    lv_label_set_text(lbl_loc_detail, "");
    lv_obj_set_style_text_color(lbl_loc_detail, C_TEXT_DIM, 0);
    lv_obj_set_style_text_font(lbl_loc_detail, &lv_font_montserrat_10, 0);

    // Indicateur LED
    lbl_led_active = lv_label_create(col_right);
    lv_label_set_text(lbl_led_active, LV_SYMBOL_REFRESH " LED active");
    lv_obj_set_style_text_color(lbl_led_active, C_ACCENT, 0);
    lv_obj_set_style_text_font(lbl_led_active, &lv_font_montserrat_10, 0);
    lv_obj_add_flag(lbl_led_active, LV_OBJ_FLAG_HIDDEN);

    // Séparateur
    lv_obj_t *sep = lv_obj_create(col_right);
    lv_obj_set_size(sep, 140, 1);
    lv_obj_set_style_bg_color(sep, C_BORDER, 0);
    lv_obj_set_style_border_width(sep, 0, 0);
    lv_obj_set_style_pad_all(sep, 0, 0);

    // Label "STOCK"
    make_label(col_right, "STOCK", C_TEXT_DIM, &lv_font_montserrat_8);

    // Boutons +/-  et quantité
    lv_obj_t *qty_row = lv_obj_create(col_right);
    lv_obj_set_size(qty_row, 172, 56);
    lv_obj_set_style_bg_opa(qty_row, LV_OPA_TRANSP, 0);
    lv_obj_set_style_border_width(qty_row, 0, 0);
    lv_obj_set_style_pad_all(qty_row, 0, 0);
    lv_obj_set_flex_flow(qty_row, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(qty_row, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);

    // Bouton −
    btn_minus = lv_btn_create(qty_row);
    lv_obj_set_size(btn_minus, 52, 52);
    lv_obj_set_style_bg_color(btn_minus, lv_color_hex(0x160a0a), 0);
    lv_obj_set_style_bg_color(btn_minus, lv_color_hex(0x1f0f0f), LV_STATE_PRESSED);
    lv_obj_set_style_border_color(btn_minus, lv_color_hex(0x3a1a1a), 0);
    lv_obj_set_style_border_width(btn_minus, 1, 0);
    lv_obj_set_style_radius(btn_minus, 10, 0);
    lv_obj_t *lbl_m = lv_label_create(btn_minus);
    lv_label_set_text(lbl_m, LV_SYMBOL_MINUS);
    lv_obj_set_style_text_color(lbl_m, C_DANGER, 0);
    lv_obj_center(lbl_m);
    lv_obj_add_event_cb(btn_minus, cb_minus, LV_EVENT_CLICKED, NULL);

    // Affichage quantité
    lv_obj_t *qty_box = lv_obj_create(qty_row);
    lv_obj_set_size(qty_box, 60, 52);
    lv_obj_set_style_bg_color(qty_box, lv_color_hex(0x0a0e18), 0);
    lv_obj_set_style_border_color(qty_box, lv_color_hex(0x1a2535), 0);
    lv_obj_set_style_border_width(qty_box, 1, 0);
    lv_obj_set_style_radius(qty_box, 10, 0);
    lbl_qty = lv_label_create(qty_box);
    lv_label_set_text(lbl_qty, "0");
    lv_obj_set_style_text_color(lbl_qty, C_TEXT, 0);
    lv_obj_set_style_text_font(lbl_qty, &lv_font_montserrat_28, 0);
    lv_obj_center(lbl_qty);

    // Bouton +
    btn_plus = lv_btn_create(qty_row);
    lv_obj_set_size(btn_plus, 52, 52);
    lv_obj_set_style_bg_color(btn_plus, lv_color_hex(0x0a160a), 0);
    lv_obj_set_style_bg_color(btn_plus, lv_color_hex(0x0f1f0f), LV_STATE_PRESSED);
    lv_obj_set_style_border_color(btn_plus, lv_color_hex(0x1a3a1a), 0);
    lv_obj_set_style_border_width(btn_plus, 1, 0);
    lv_obj_set_style_radius(btn_plus, 10, 0);
    lv_obj_t *lbl_p = lv_label_create(btn_plus);
    lv_label_set_text(lbl_p, LV_SYMBOL_PLUS);
    lv_obj_set_style_text_color(lbl_p, C_SUCCESS, 0);
    lv_obj_center(lbl_p);
    lv_obj_add_event_cb(btn_plus, cb_plus, LV_EVENT_CLICKED, NULL);

    // Statut seuil
    lbl_status = lv_label_create(col_right);
    lv_label_set_text(lbl_status, "");
    lv_obj_set_style_text_color(lbl_status, C_SUCCESS, 0);
    lv_obj_set_style_text_font(lbl_status, &lv_font_montserrat_10, 0);

    // Bouton Confirmer (caché par défaut)
    btn_confirm = lv_btn_create(col_right);
    lv_obj_set_size(btn_confirm, 172, 36);
    lv_obj_set_style_bg_color(btn_confirm, lv_color_hex(0x0a1830), 0);
    lv_obj_set_style_border_color(btn_confirm, C_ACCENT, 0);
    lv_obj_set_style_border_width(btn_confirm, 1, 0);
    lv_obj_set_style_radius(btn_confirm, 8, 0);
    lv_obj_t *lbl_conf = lv_label_create(btn_confirm);
    lv_label_set_text(lbl_conf, "Confirmer");
    lv_obj_set_style_text_color(lbl_conf, C_ACCENT, 0);
    lv_obj_set_style_text_font(lbl_conf, &lv_font_montserrat_12, 0);
    lv_obj_center(lbl_conf);
    lv_obj_add_event_cb(btn_confirm, cb_confirm, LV_EVENT_CLICKED, NULL);
    lv_obj_add_flag(btn_confirm, LV_OBJ_FLAG_HIDDEN);

    // ── FOOTER (36px) ────────────────────────────────────────────────
    lv_obj_t *footer = lv_obj_create(ui_root);
    lv_obj_set_size(footer, 800, 36);
    lv_obj_set_style_bg_color(footer, lv_color_hex(0x050810), 0);
    lv_obj_set_style_border_width(footer, 1, 0);
    lv_obj_set_style_border_side(footer, LV_BORDER_SIDE_TOP, 0);
    lv_obj_set_style_border_color(footer, C_BORDER, 0);
    lv_obj_set_style_pad_hor(footer, 16, 0);
    lv_obj_set_flex_flow(footer, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(footer, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);

    lbl_breadcrumb = make_label(footer, "", C_TEXT_DIM, &lv_font_montserrat_10);
    lbl_appname    = make_label(footer, "StockEleK", C_TEXT_DIM, &lv_font_montserrat_10);
}

// ─────────────────────────────────────────────────────────────────────
//  Met à jour l'UI avec les données d'un composant
// ─────────────────────────────────────────────────────────────────────
void ui_update_component(const Component &comp) {
    g_current_comp_id = comp.id;
    g_current_qty     = comp.quantity;
    g_pending_delta   = 0;
    g_min_stock       = comp.min_stock;
    g_unit_price      = comp.unit_price;

    // Header
    lv_label_set_text(lbl_name,  comp.description);
    lv_label_set_text(lbl_manuf, comp.manufacturer);
    lv_label_set_text(lbl_lcsc,  comp.lcsc_ref);

    // Badges KiCad
    lv_obj_set_style_text_color(lbl_sym_badge, comp.kicad_sym ? C_SUCCESS : C_TEXT_DIM, 0);
    lv_obj_set_style_text_color(lbl_fp_badge,  comp.kicad_fp  ? C_SUCCESS : C_TEXT_DIM, 0);
    lv_obj_set_style_text_color(lbl_3d_badge,  comp.kicad_3d  ? C_SUCCESS : C_TEXT_DIM, 0);

    // Description + package
    lv_label_set_text(lbl_desc, comp.description);
    lv_label_set_text(lbl_pkg,  comp.package);
    lv_label_set_text(lbl_cat,  comp.category);

    // Prix
    char price_buf[20], total_buf[20];
    snprintf(price_buf, sizeof(price_buf), "%.4f EUR", comp.unit_price);
    snprintf(total_buf, sizeof(total_buf), "%.2f EUR", comp.unit_price * comp.quantity);
    lv_label_set_text(lbl_price, price_buf);
    lv_label_set_text(lbl_total, total_buf);

    // Emplacement
    lv_label_set_text(lbl_location, comp.location[0] ? comp.location : "---");

    // Détail emplacement "Tiroir X · Case NN"
    if (comp.location[0]) {
        char detail[32];
        char letter = toupper(comp.location[0]);
        int  num    = atoi(comp.location + 1);
        snprintf(detail, sizeof(detail), "Tiroir %c  Case %02d", letter, num);
        lv_label_set_text(lbl_loc_detail, detail);
    } else {
        lv_label_set_text(lbl_loc_detail, "");
    }

    // Quantité
    char qty_buf[8];
    snprintf(qty_buf, sizeof(qty_buf), "%d", comp.quantity);
    lv_label_set_text(lbl_qty, qty_buf);

    // Statut seuil
    if (comp.quantity == 0) {
        lv_label_set_text(lbl_status, "rupture !");
        lv_obj_set_style_text_color(lbl_status, C_DANGER, 0);
    } else if (comp.quantity <= comp.min_stock && comp.min_stock > 0) {
        lv_label_set_text(lbl_status, "stock bas !");
        lv_obj_set_style_text_color(lbl_status, C_WARNING, 0);
    } else {
        char s[20]; snprintf(s, sizeof(s), "min. %d", comp.min_stock);
        lv_label_set_text(lbl_status, s);
        lv_obj_set_style_text_color(lbl_status, C_SUCCESS, 0);
    }

    // Cacher bouton Confirmer
    lv_obj_add_flag(btn_confirm, LV_OBJ_FLAG_HIDDEN);

    // Footer breadcrumb
    lv_label_set_text(lbl_breadcrumb, comp.category);

    // LED active
    lv_obj_add_flag(lbl_led_active, LV_OBJ_FLAG_HIDDEN);
}

// ─────────────────────────────────────────────────────────────────────
//  Affiche/cache l'indicateur LED active
// ─────────────────────────────────────────────────────────────────────
void ui_set_led_active(bool active) {
    if (active) lv_obj_remove_flag(lbl_led_active, LV_OBJ_FLAG_HIDDEN);
    else        lv_obj_add_flag(lbl_led_active,    LV_OBJ_FLAG_HIDDEN);
}

// ─────────────────────────────────────────────────────────────────────
//  Affiche un message de statut (connexion WiFi, chargement…)
// ─────────────────────────────────────────────────────────────────────
void ui_show_status(lv_obj_t *screen, const char *msg, lv_color_t color = lv_color_hex(0xdde4f0)) {
    static lv_obj_t *status_lbl = NULL;
    if (!status_lbl) {
        status_lbl = lv_label_create(screen);
        lv_obj_set_style_text_font(status_lbl, &lv_font_montserrat_20, 0);
        lv_obj_center(status_lbl);
    }
    lv_label_set_text(status_lbl, msg);
    lv_obj_set_style_text_color(status_lbl, color, 0);
}
