#pragma once
#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "pins_config.h"

// ─────────────────────────────────────────────────────────────────────
//  Structure composant (ce qu'on affiche sur l'écran)
// ─────────────────────────────────────────────────────────────────────
struct Component {
    int     id;
    char    description[80];
    char    manufacturer[40];
    char    lcsc_ref[16];
    char    package[20];
    char    location[8];       // ex: "A07"
    int     quantity;
    int     min_stock;
    float   unit_price;
    char    category[60];
    bool    kicad_sym;
    bool    kicad_fp;
    bool    kicad_3d;
    bool    valid;
};

// ─────────────────────────────────────────────────────────────────────
//  Récupère un composant par son ID
// ─────────────────────────────────────────────────────────────────────
bool fetchComponent(int id, Component &comp) {
    if (WiFi.status() != WL_CONNECTED) return false;

    HTTPClient http;
    char url[128];
    snprintf(url, sizeof(url), "http://%s:%d/component/%d/json",
             STOCKELEC_HOST, STOCKELEC_PORT, id);

    http.begin(url);
    http.addHeader("X-Token", STOCKELEC_TOKEN);
    int code = http.GET();

    if (code != 200) {
        http.end();
        return false;
    }

    String body = http.getString();
    http.end();

    JsonDocument doc;
    if (deserializeJson(doc, body) != DeserializationError::Ok) return false;

    comp.id        = doc["id"] | 0;
    strlcpy(comp.description,  doc["description"]  | "", sizeof(comp.description));
    strlcpy(comp.manufacturer, doc["manufacturer"] | "", sizeof(comp.manufacturer));
    strlcpy(comp.lcsc_ref,     doc["lcsc_part_number"] | "", sizeof(comp.lcsc_ref));
    strlcpy(comp.package,      doc["package"]      | "", sizeof(comp.package));
    strlcpy(comp.location,     doc["location"]     | "", sizeof(comp.location));
    strlcpy(comp.category,     doc["category"]     | "", sizeof(comp.category));
    comp.quantity   = doc["quantity"]   | 0;
    comp.min_stock  = doc["min_stock"]  | 0;
    comp.unit_price = doc["unit_price"] | 0.0f;
    comp.kicad_sym  = doc["kicad_sym"]  | false;
    comp.kicad_fp   = doc["kicad_fp"]   | false;
    comp.kicad_3d   = doc["kicad_3d"]   | false;
    comp.valid      = true;
    return true;
}

// ─────────────────────────────────────────────────────────────────────
//  Ajuste la quantité d'un composant (+delta ou valeur absolue)
// ─────────────────────────────────────────────────────────────────────
bool adjustQuantity(int id, int delta, int &new_qty) {
    if (WiFi.status() != WL_CONNECTED) return false;

    HTTPClient http;
    char url[128];
    snprintf(url, sizeof(url), "http://%s:%d/component/%d/adjust",
             STOCKELEC_HOST, STOCKELEC_PORT, id);

    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-Token", STOCKELEC_TOKEN);

    char body[64];
    snprintf(body, sizeof(body), "{\"delta\":%d}", delta);
    int code = http.POST(body);

    if (code != 200) { http.end(); return false; }

    String resp = http.getString();
    http.end();

    JsonDocument doc;
    if (deserializeJson(doc, resp) != DeserializationError::Ok) return false;
    if (!doc["ok"].as<bool>()) return false;

    new_qty = doc["new_qty"] | 0;
    return true;
}

// ─────────────────────────────────────────────────────────────────────
//  Allume les LEDs via StockElec (pour déclencher l'allumage côté
//  serveur — dans notre cas le P4 gère les LEDs directement, cette
//  fonction est utile si tu veux logger dans StockElec)
// ─────────────────────────────────────────────────────────────────────
bool pingStockElec() {
    if (WiFi.status() != WL_CONNECTED) return false;
    HTTPClient http;
    char url[80];
    snprintf(url, sizeof(url), "http://%s:%d/", STOCKELEC_HOST, STOCKELEC_PORT);
    http.begin(url);
    int code = http.GET();
    http.end();
    return (code == 200);
}
