#include <Arduino.h>
/**
 * StockEleK — Firmware LED ESP32 v6.1
 * =====================================
 * Ruban 1 (LED_PIN)    : emplacement exact du composant
 * Ruban 2 (DRAWER_PIN) : tiroir (lettre A->Z, 26 LEDs minimum)
 * Afficheur HT16K33    : 4 digits 14-seg — affiche "A 16"
 *
 * Changelog v6.0 :
 *   - Page web embarquée sur GET / (interface de contrôle complète)
 *   - POST /config : modifier brightness, duration, drawer_color,
 *                    default_color, fade_steps en runtime
 *   - GET  /config : lire la config courante (JSON)
 *   - Preferences  : config sauvegardée en flash, survit aux redémarrages
 *   - Statut live (RSSI, heap, uptime, queue) dans la page web
 *   - Contrôle manuel depuis la page web (tiroir, test, éteindre)
 *
 * Bibliothèques requises :
 *   - FastLED
 *   - ArduinoJson
 *   - WebSockets (Markus Sattler)
 *   - Adafruit_LEDBackpack + Adafruit_GFX
 *   - Preferences (incluse dans ESP32 Arduino core)
 *
 * Câblage HT16K33 (ESP32-S3 Wroom-1) :
 *   SDA -> GPIO 8  |  SCL -> GPIO 9  |  VCC -> 3.3V  |  GND -> GND
 */

#include <WiFi.h>
#include <WebServer.h>
#include <WebSocketsServer.h>
#include <ArduinoOTA.h>
#include <FastLED.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_LEDBackpack.h>
#include <Preferences.h>

// Forward declarations (nécessaires pour le préprocesseur Arduino)
struct LedCommand;
struct RuntimeConfig;

// ======================================================================
//  CONFIGURATION — modifiez uniquement cette section
// ======================================================================

const char* SSID       = "slyhome";
const char* PASSWORD   = "vivelewifi2016vivemoi";
const char* AUTH_TOKEN = "stockelek-secret";

// Ruban 1 — emplacements composants
#define LED_PIN          5
#define NUM_LEDS         500

// Ruban 2 — tiroirs A-Z
#define DRAWER_PIN       18
#define NUM_DRAWERS      26

// Afficheur HT16K33
#define DISPLAY_ADDR      0x70
#define DISPLAY_BRIGHT    8
#define DISPLAY_SLEEP_SEC 33
#define DISPLAY_SDA       8
#define DISPLAY_SCL       9

// LEDs — valeurs par défaut (overridables via /config + Preferences)
#define DEFAULT_BRIGHTNESS   255
#define DEFAULT_DURATION_SEC 5
#define DEFAULT_FADE_STEPS   20
#define FADE_DELAY_MS        12
#define QUEUE_SIZE           4
#define MAX_LEDS_PER_CMD     16
#define WIFI_RETRY_MS        5000

// Couleurs par défaut
#define DEFAULT_COLOR_STR        "purple"
#define DEFAULT_DRAWER_COLOR_STR "white"

// ======================================================================
//  CONFIG RUNTIME (modifiable via /config, sauvegardée en Preferences)
// ======================================================================

struct RuntimeConfig {
    uint8_t brightness;       // 0-255
    int     duration;         // secondes
    int     fadeSteps;        // 5-50
    char    defaultColor[16]; // ex: "#7c6cff" ou "purple"
    char    drawerColor[16];  // ex: "white"
};

RuntimeConfig cfg;
Preferences   prefs;

void loadConfig() {
    prefs.begin("stockelek", true);  // read-only
    cfg.brightness  = prefs.getUChar("brightness", DEFAULT_BRIGHTNESS);
    cfg.duration    = prefs.getInt  ("duration",   DEFAULT_DURATION_SEC);
    cfg.fadeSteps   = prefs.getInt  ("fade_steps", DEFAULT_FADE_STEPS);
    prefs.getString("default_color",  cfg.defaultColor, sizeof(cfg.defaultColor));
    prefs.getString("drawer_color",   cfg.drawerColor,  sizeof(cfg.drawerColor));
    prefs.end();
    // Valeurs par défaut si jamais les prefs sont vides
    if (strlen(cfg.defaultColor) == 0) strlcpy(cfg.defaultColor, DEFAULT_COLOR_STR,        sizeof(cfg.defaultColor));
    if (strlen(cfg.drawerColor)  == 0) strlcpy(cfg.drawerColor,  DEFAULT_DRAWER_COLOR_STR, sizeof(cfg.drawerColor));
    Serial.println("[CFG]    brightness=" + String(cfg.brightness) +
                   " duration=" + String(cfg.duration) +
                   "s color=" + String(cfg.defaultColor) +
                   " drawer=" + String(cfg.drawerColor));
}

void saveConfig() {
    prefs.begin("stockelek", false);  // read-write
    prefs.putUChar ("brightness",    cfg.brightness);
    prefs.putInt   ("duration",      cfg.duration);
    prefs.putInt   ("fade_steps",    cfg.fadeSteps);
    prefs.putString("default_color", cfg.defaultColor);
    prefs.putString("drawer_color",  cfg.drawerColor);
    prefs.end();
    // Appliquer immédiatement
    FastLED.setBrightness(cfg.brightness);
    FastLED.show();
    Serial.println("[CFG]    Sauvegardé en flash");
}

// ======================================================================
//  PAGE WEB EMBARQUÉE (PROGMEM)
// ======================================================================

// ======================================================================
//  STRUCTURES
// ======================================================================

struct LedCommand {
    int  indices[MAX_LEDS_PER_CMD];
    int  count;
    int  drawer;
    char cell[8];
    CRGB color;
    CRGB drawerColor;
    int  duration;
    bool valid;
};

// ======================================================================
//  ETAT GLOBAL
// ======================================================================

CRGB leds[NUM_LEDS];
CRGB drawerLeds[NUM_DRAWERS];
static CRGB fadeSnapshot[MAX_LEDS_PER_CMD];

WebServer        server(80);
WebSocketsServer ws(81);

bool          ledActive = false;
unsigned long ledOffAt  = 0;

LedCommand cmdQueue[QUEUE_SIZE];
int qHead = 0, qTail = 0, qCount = 0;

int  currentIndices[MAX_LEDS_PER_CMD];
int  currentCount       = 0;
int  currentDrawer      = -1;
char currentCell[8]     = "";
CRGB currentColor       = CRGB::Black;
CRGB currentDrawerColor = CRGB::Black;
int  currentDuration    = 0;

bool testRunning = false;
int  testOffset = 0, testCount_ = 0, testStep = 0;
unsigned long testNextAt = 0;
int  testDelayMs = 80;
CRGB testColor = CRGB::Green;

// Breathing tiroir (ruban 2) — non-bloquant
bool          breatheActive  = false;
int           breatheIndex   = -1;   // index LED du tiroir actif
CRGB          breatheColor   = CRGB::Black;
unsigned long breatheNextAt  = 0;
uint8_t       breatheVal     = 0;
int8_t        breatheDir     = 1;    // +1 montée, -1 descente
#define BREATHE_STEP_MS  18          // ms entre chaque step
#define BREATHE_MIN       8          // luminosité minimale (0-255)
#define BREATHE_MAX     220          // luminosité maximale (0-255)
#define BREATHE_STEP      4          // incrément par tick

Adafruit_AlphaNum4 display = Adafruit_AlphaNum4();
bool          displayReady      = false;
bool          displaySleeping   = false;
bool          sleepBlinkState   = false;
unsigned long displayLastActive = 0;
unsigned long sleepBlinkNext    = 0;

unsigned long wifiLastCheck    = 0;
bool          wifiWasConnected = false;

// ======================================================================
//  DEBUG
// ======================================================================

void dbg(String msg) { Serial.println("[DBG] " + msg); }
void err(String msg) { Serial.println("[ERR] " + msg); }

// ======================================================================
//  WIFI WATCHDOG
// ======================================================================

void wifiWatchdog() {
    unsigned long now = millis();
    if (now - wifiLastCheck < WIFI_RETRY_MS) return;
    wifiLastCheck = now;

    if (WiFi.status() == WL_CONNECTED) {
        if (!wifiWasConnected) {
            Serial.println("[WiFi]   Reconnecte — IP=" + WiFi.localIP().toString());
            wifiWasConnected = true;
        }
        return;
    }
    if (wifiWasConnected) {
        Serial.println("[WiFi]   Connexion perdue — reconnexion...");
        wifiWasConnected = false;
    }
    WiFi.disconnect(true); delay(100);
    WiFi.begin(SSID, PASSWORD);
    unsigned long t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < 8000) delay(500);
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("[WiFi]   OK — " + WiFi.localIP().toString());
        wifiWasConnected = true;
    }
}

// ======================================================================
//  AFFICHEUR HT16K33
// ======================================================================

void displayClear() {
    if (!displayReady) return;
    display.clear(); display.writeDisplay();
    displaySleeping = false;
}

void displayShow(const char* cellId) {
    if (!displayReady) {
        if (cellId && cellId[0]) {
            int i = 0; char letter = '\0';
            while (cellId[i] && isAlpha((unsigned char)cellId[i])) { if(!i) letter=toupper((unsigned char)cellId[i]); i++; }
            Serial.printf("[DISP]   (simule) \"%c %02d\"\n", letter, atoi(&cellId[i]));
        }
        return;
    }
    displaySleeping = false; displayLastActive = millis();
    display.clear();
    if (!cellId || !cellId[0]) { display.writeDisplay(); return; }
    int i = 0; char letter = '\0';
    while (cellId[i] && isAlpha((unsigned char)cellId[i])) { if(!i) letter=toupper((unsigned char)cellId[i]); i++; }
    int number = atoi(&cellId[i]);
    if (letter) display.writeDigitAscii(0, letter);
    display.writeDigitAscii(1, ' ');
    display.writeDigitAscii(2, '0' + (number / 10));
    display.writeDigitAscii(3, '0' + (number % 10));
    display.writeDisplay();
    Serial.printf("[DISP]   \"%c %02d\"\n", letter, number);
}

void displayText(const char* text) {
    if (!displayReady) { Serial.printf("[DISP]   (simule) \"%s\"\n", text); return; }
    display.clear();
    for (int i = 0; i < 4 && text[i]; i++) display.writeDigitAscii(i, text[i]);
    display.writeDisplay();
    displaySleeping = false; displayLastActive = millis();
}

void displaySleepTick() {
    if (displayReady && !displaySleeping && displayLastActive > 0 &&
        (millis() - displayLastActive) >= (unsigned long)DISPLAY_SLEEP_SEC * 1000) {
        displaySleeping = true; sleepBlinkState = false; sleepBlinkNext = millis();
        Serial.println("[DISP]   Veille");
    }
    if (displaySleeping && millis() >= sleepBlinkNext) {
        display.clear();
        if (sleepBlinkState) {
            display.writeDigitRaw(1, 0b0000000001000000);
            display.writeDigitRaw(2, 0b0000000001000000);
        }
        display.writeDisplay();
        sleepBlinkState = !sleepBlinkState;
        sleepBlinkNext  = millis() + 800;
    }
}

// ======================================================================
//  CORS + AUTH
// ======================================================================

void addCORSHeaders() {
    server.sendHeader("Access-Control-Allow-Origin",  "*");
    server.sendHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    server.sendHeader("Access-Control-Allow-Headers", "Content-Type, X-Token");
}

void sendJSON(int code, const String& json) {
    addCORSHeaders();
    server.send(code, "application/json", json);
}

bool checkAuth() {
    if (!server.hasHeader("X-Token")) { sendJSON(401, "{\"ok\":false,\"error\":\"missing X-Token\"}"); return false; }
    if (server.header("X-Token") != String(AUTH_TOKEN)) { sendJSON(403, "{\"ok\":false,\"error\":\"invalid token\"}"); return false; }
    return true;
}

// ======================================================================
//  COULEUR
// ======================================================================

CRGB parseColor(JsonVariant v) {
    if (v.is<JsonArray>()) {
        JsonArray a = v.as<JsonArray>();
        if (a.size() >= 3) return CRGB(constrain((int)a[0],0,255), constrain((int)a[1],0,255), constrain((int)a[2],0,255));
    }
    if (v.is<const char*>()) {
        String s = String(v.as<const char*>()); s.toLowerCase();
        if (s.startsWith("#") && s.length() == 7) {
            long h = strtol(s.substring(1).c_str(), nullptr, 16);
            return CRGB((h>>16)&0xFF, (h>>8)&0xFF, h&0xFF);
        }
        if (s=="green")   return CRGB::Green;
        if (s=="blue")    return CRGB::Blue;
        if (s=="red")     return CRGB::Red;
        if (s=="yellow")  return CRGB::Yellow;
        if (s=="white")   return CRGB::White;
        if (s=="orange")  return CRGB(255,80,0);
        if (s=="cyan")    return CRGB::Cyan;
        if (s=="pink")    return CRGB(255,20,80);
        if (s=="purple")  return CRGB::Purple;
        if (s=="magenta") return CRGB::Magenta;
        if (s=="black")   return CRGB::Black;
    }
    return CRGB::Purple;
}

CRGB parseColorStr(const char* str) {
    StaticJsonDocument<32> tmp; tmp["c"] = str;
    return parseColor(tmp["c"]);
}

// ======================================================================
//  EFFETS
// ======================================================================

void fadeIn(int* indices, int count, CRGB target) {
    for (int step = 1; step <= cfg.fadeSteps; step++) {
        uint8_t ratio = (step * 255) / cfg.fadeSteps;
        CRGB c = CRGB(scale8(target.r,ratio), scale8(target.g,ratio), scale8(target.b,ratio));
        for (int i = 0; i < count; i++)
            if (indices[i] >= 0 && indices[i] < NUM_LEDS) leds[indices[i]] = c;
        FastLED.show(); delay(FADE_DELAY_MS);
    }
}

void fadeOut(int* indices, int count) {
    int n = min(count, MAX_LEDS_PER_CMD);
    for (int i = 0; i < n; i++)
        fadeSnapshot[i] = (indices[i] >= 0 && indices[i] < NUM_LEDS) ? leds[indices[i]] : CRGB::Black;
    for (int step = cfg.fadeSteps; step >= 0; step--) {
        uint8_t ratio = (step * 255) / cfg.fadeSteps;
        for (int i = 0; i < n; i++)
            if (indices[i] >= 0 && indices[i] < NUM_LEDS)
                leds[indices[i]] = CRGB(scale8(fadeSnapshot[i].r,ratio), scale8(fadeSnapshot[i].g,ratio), scale8(fadeSnapshot[i].b,ratio));
        FastLED.show(); delay(FADE_DELAY_MS);
    }
    fill_solid(leds, NUM_LEDS, CRGB::Black); FastLED.show();
}

void setDrawerLed(int index, CRGB color) {
    fill_solid(drawerLeds, NUM_DRAWERS, CRGB::Black);
    if (index >= 0 && index < NUM_DRAWERS) {
        drawerLeds[index] = color;
        // Démarrer le breathing
        breatheIndex  = index;
        breatheColor  = color;
        breatheVal    = BREATHE_MIN;
        breatheDir    = 1;
        breatheActive = true;
        breatheNextAt = millis();
    }
    FastLED.show();
}

void clearDrawerLed() {
    breatheActive = false;
    breatheIndex  = -1;
    fill_solid(drawerLeds, NUM_DRAWERS, CRGB::Black);
    FastLED.show();
}

// Breathing non-bloquant — appelé dans loop()
void drawerBreatheTick() {
    if (!breatheActive || breatheIndex < 0) return;
    if (millis() < breatheNextAt) return;

    breatheNextAt = millis() + BREATHE_STEP_MS;
    breatheVal   += breatheDir * BREATHE_STEP;

    if (breatheVal >= BREATHE_MAX) { breatheVal = BREATHE_MAX; breatheDir = -1; }
    if (breatheVal <= BREATHE_MIN) { breatheVal = BREATHE_MIN; breatheDir =  1; }

    // Appliquer la luminosité au canal
    uint8_t ratio = breatheVal;
    CRGB c = CRGB(scale8(breatheColor.r, ratio),
                  scale8(breatheColor.g, ratio),
                  scale8(breatheColor.b, ratio));
    fill_solid(drawerLeds, NUM_DRAWERS, CRGB::Black);
    drawerLeds[breatheIndex] = c;
    FastLED.show();
}

void bootSweep() {
    CRGB sweepColor = CRGB(30, 0, 60);
    for (int i = 0; i < NUM_DRAWERS; i++) {
        if (i > 0) drawerLeds[i-1] = CRGB::Black;
        drawerLeds[i] = sweepColor;
        FastLED.show(); delay(30);
    }
    fill_solid(drawerLeds, NUM_DRAWERS, CRGB::Black); FastLED.show();
    for (int f = 0; f < 2; f++) {
        drawerLeds[0] = CRGB::Green; FastLED.show(); delay(120);
        drawerLeds[0] = CRGB::Black; FastLED.show(); delay(120);
    }
}

// ======================================================================
//  FILE DE COMMANDES
// ======================================================================

bool enqueue(LedCommand& cmd) {
    if (qCount >= QUEUE_SIZE) { err("File pleine"); return false; }
    cmdQueue[qTail] = cmd; qTail = (qTail+1)%QUEUE_SIZE; qCount++; return true;
}

void execCommand(LedCommand& cmd) {
    fill_solid(leds, NUM_LEDS, CRGB::Black);
    fadeIn(cmd.indices, cmd.count, cmd.color);
    if (cmd.drawer >= 0) setDrawerLed(cmd.drawer, cmd.drawerColor);
    else clearDrawerLed();
    displayShow(cmd.cell);
    currentCount = cmd.count; currentDrawer = cmd.drawer;
    currentColor = cmd.color; currentDrawerColor = cmd.drawerColor;
    currentDuration = cmd.duration;
    strncpy(currentCell, cmd.cell, sizeof(currentCell)-1); currentCell[sizeof(currentCell)-1]='\0';
    int n = min(cmd.count, MAX_LEDS_PER_CMD);
    for (int i = 0; i < n; i++) currentIndices[i] = cmd.indices[i];
    ledOffAt = millis() + (unsigned long)cmd.duration * 1000; ledActive = true;
    ws.broadcastTXT("{\"event\":\"on\",\"count\":" + String(cmd.count) +
                    ",\"drawer\":" + String(cmd.drawer) +
                    ",\"cell\":\"" + String(cmd.cell) + "\"" +
                    ",\"duration\":" + String(cmd.duration) + "}");
}

void processQueue() {
    if (qCount == 0 || ledActive) return;
    LedCommand& cmd = cmdQueue[qHead];
    if (!cmd.valid) { qHead=(qHead+1)%QUEUE_SIZE; qCount--; return; }
    execCommand(cmd); cmd.valid = false; qHead=(qHead+1)%QUEUE_SIZE; qCount--;
}


const char HTML_PART1[] PROGMEM = R"rawhtml(<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>StockEleK LEDs</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0b0e18;--surface:#111520;--card:#161b2e;--hover:#1c2340;
  --border:#252c45;--accent:#7c6cff;--accent-dim:rgba(124,108,255,.15);
  --success:#34d17e;--warning:#f59e0b;--danger:#f43f5e;--info:#38bdf8;
  --text:#e8eaf6;--muted:#6b74a0;--faint:#3d4566;
  --radius:10px;--radius-sm:6px;--mono:'Courier New',monospace;
}
body{background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,sans-serif;min-height:100vh;padding:1rem}
h1{font-size:1.4rem;font-weight:900;letter-spacing:-.03em;color:var(--text)}
h2{font-size:.85rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:.75rem}
.header{display:flex;align-items:center;justify-content:space-between;margin-bottom:1.5rem;padding-bottom:.85rem;border-bottom:1px solid var(--border)}
.header-sub{font-size:.78rem;color:var(--muted);margin-top:.2rem}
.badge{display:inline-block;font-size:.7rem;font-weight:700;padding:.2rem .55rem;border-radius:99px;background:var(--accent-dim);color:var(--accent);border:1px solid rgba(124,108,255,.3)}
.badge-ok{background:rgba(52,209,126,.15);color:var(--success);border-color:rgba(52,209,126,.3)}
.badge-err{background:rgba(244,63,94,.15);color:var(--danger);border-color:rgba(244,63,94,.3)}
.badge-warn{background:rgba(245,158,11,.15);color:var(--warning);border-color:rgba(245,158,11,.3)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1rem;margin-bottom:1rem}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:1.1rem 1.25rem}
.card-title{font-size:.72rem;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin-bottom:.85rem}
.stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:.5rem}
.stat{background:var(--surface);border-radius:var(--radius-sm);padding:.55rem .75rem}
.stat-val{font-size:1.3rem;font-weight:800;line-height:1;color:var(--text)}
.stat-lbl{font-size:.65rem;color:var(--muted);margin-top:.15rem;text-transform:uppercase;letter-spacing:.06em}
.stat-val.ok{color:var(--success)}
.stat-val.warn{color:var(--warning)}
.stat-val.err{color:var(--danger)}
.stat-val.accent{color:var(--accent)}
.led-indicator{width:12px;height:12px;border-radius:50%;display:inline-block;margin-right:.4rem;flex-shrink:0}
.led-on{background:var(--success);box-shadow:0 0 8px var(--success)}
.led-off{background:var(--faint)}
.status-row{display:flex;align-items:center;font-size:.82rem;color:var(--muted);padding:.3rem 0;border-bottom:1px solid var(--border)}
.status-row:last-child{border-bottom:none}
.status-val{margin-left:auto;font-family:var(--mono);font-size:.78rem;color:var(--text)}
label{display:block;font-size:.75rem;font-weight:600;color:var(--muted);margin-bottom:.3rem;margin-top:.75rem}
label:first-child{margin-top:0}
input[type=text],input[type=number],input[type=color]{
  width:100%;background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius-sm);padding:.5rem .75rem;color:var(--text);
  font-size:.82rem;outline:none;transition:border-color .15s;
}
input[type=text]:focus,input[type=number]:focus{border-color:var(--accent)}
input[type=color]{padding:.2rem .3rem;height:36px;cursor:pointer}
.range-wrap{display:flex;align-items:center;gap:.75rem}
input[type=range]{flex:1;accent-color:var(--accent)}
.range-val{font-family:var(--mono);font-size:.82rem;color:var(--accent);min-width:2.5rem;text-align:right}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:.35rem;padding:.5rem 1rem;border:none;border-radius:var(--radius-sm);font-size:.82rem;font-weight:600;cursor:pointer;transition:all .15s;width:100%;margin-top:.4rem}
.btn-primary{background:var(--accent);color:#fff}
.btn-primary:hover{background:#9585ff}
.btn-secondary{background:var(--surface);color:var(--text);border:1px solid var(--border)}
.btn-secondary:hover{border-color:var(--accent);color:var(--accent)}
.btn-danger{background:rgba(244,63,94,.15);color:var(--danger);border:1px solid rgba(244,63,94,.3)}
.btn-danger:hover{background:var(--danger);color:#fff}
.btn-sm{padding:.35rem .75rem;font-size:.75rem;width:auto;margin-top:0}
.btn:disabled{opacity:.4;cursor:not-allowed}
.toast{position:fixed;bottom:1.5rem;right:1.5rem;padding:.65rem 1.1rem;border-radius:var(--radius-sm);font-size:.8rem;font-weight:600;z-index:999;opacity:0;transform:translateY(8px);transition:all .25s;pointer-events:none}
.toast.show{opacity:1;transform:none}
.toast-ok{background:rgba(52,209,126,.2);color:var(--success);border:1px solid rgba(52,209,126,.4)}
.toast-err{background:rgba(244,63,94,.2);color:var(--danger);border:1px solid rgba(244,63,94,.4)}
.toast-info{background:rgba(56,189,248,.2);color:var(--info);border:1px solid rgba(56,189,248,.4)}
.section-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:.75rem}
.color-row{display:grid;grid-template-columns:1fr 40px;gap:.5rem;align-items:end}
.color-row input[type=text]{margin-top:0}
.drawer-select{display:grid;grid-template-columns:repeat(auto-fill,minmax(38px,1fr));gap:.35rem;margin-top:.5rem}
.drawer-btn{padding:.4rem;font-size:.75rem;font-weight:700;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--muted);cursor:pointer;text-align:center;transition:all .15s}
.drawer-btn:hover{border-color:var(--accent);color:var(--accent)}
.drawer-btn.active{background:var(--accent-dim);border-color:var(--accent);color:var(--accent)}
.pulse{animation:pulse 1.5s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.cell-input{display:grid;grid-template-columns:1fr 1fr;gap:.5rem}
footer{margin-top:2rem;text-align:center;font-size:.7rem;color:var(--faint)}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>💡 StockEleK LEDs</h1>
    <div class="header-sub" id="header-ip">Chargement...</div>
  </div>
  <div style="display:flex;gap:.5rem;align-items:center">
    <span class="led-indicator" id="wifi-led"></span>
    <span id="wifi-rssi" style="font-size:.72rem;color:var(--muted)"></span>
    <span id="version-badge" class="badge">v6.1</span>
  </div>
</div>

<div class="grid">

  <!-- Statut -->
  <div class="card">
    <div class="card-title">Statut en direct <button class="btn-sm btn-secondary" onclick="refreshStatus()" style="float:right;padding:.2rem .5rem;font-size:.65rem">↻ Rafraîchir</button></div>
    <div class="stat-grid">
      <div class="stat">
        <div class="stat-val" id="stat-leds">—</div>
        <div class="stat-lbl">LEDs allumées</div>
      </div>
      <div class="stat">
        <div class="stat-val" id="stat-remaining">—</div>
        <div class="stat-lbl">Temps restant</div>
      </div>
      <div class="stat">
        <div class="stat-val" id="stat-heap">—</div>
        <div class="stat-lbl">RAM libre</div>
      </div>
      <div class="stat">
        <div class="stat-val" id="stat-uptime">—</div>
        <div class="stat-lbl">Uptime</div>
      </div>
    </div>
    <div style="margin-top:.85rem">
      <div class="status-row">
        <span class="led-indicator" id="led-active-dot"></span>LEDs
        <span class="status-val" id="status-cell">—</span>
      </div>
      <div class="status-row">
        <span class="led-indicator" id="display-dot"></span>Afficheur HT16K33
        <span class="status-val" id="status-display">—</span>
      </div>
      <div class="status-row">
        <span>File d'attente</span>
        <span class="status-val" id="status-queue">0 / 4</span>
      </div>
    </div>
    <button class="btn btn-danger" id="btn-off" onclick="ledOff()" style="margin-top:.85rem">
      ✗ Tout éteindre
    </button>
    <button class="btn btn-secondary" onclick="rebootEsp()" style="margin-top:.35rem">
      ↺ Redémarrer l'ESP32
    </button>
  </div>

  <!-- Contrôle manuel -->
  <div class="card">
    <div class="card-title">Contrôle manuel</div>

    <label>Tiroir</label>
    <div class="drawer-select" id="drawer-select"></div>

    <label>Case (ex: A01, B16)</label>
    <div class="cell-input">
      <input type="text" id="manual-cell" placeholder="A01" maxlength="6">
      <input type="number" id="manual-led" placeholder="Index LED" min="0" max="499">
    </div>

    <label>Couleur pour ce test</label>
    <div class="color-row">
      <input type="text" id="manual-color-hex" placeholder="#00cc44" value="#00cc44"
             oninput="syncColorPicker('manual-color','manual-color-hex')">
      <input type="color" id="manual-color" value="#00cc44"
             oninput="syncColorHex('manual-color','manual-color-hex')">
    </div>

    <label>Durée (secondes)</label>
    <div class="range-wrap">
      <input type="range" id="manual-duration" min="1" max="30" value="5"
             oninput="document.getElementById('manual-duration-val').textContent=this.value+'s'">
      <span class="range-val" id="manual-duration-val">5s</span>
    </div>

    <button class="btn btn-primary" onclick="manualLight()" style="margin-top:.85rem">
      💡 Allumer
    </button>

    <button class="btn btn-secondary" onclick="runTest()">
      ▶ Chenillard test
    </button>
  </div>

  <!-- Paramètres runtime -->
  <div class="card">
    <div class="section-header">
      <div class="card-title" style="margin-bottom:0">Paramètres</div>
      <button class="btn-sm btn-secondary" onclick="loadCurrentConfig()">↻ Recharger</button>
    </div>

    <label>Luminosité (0-255)</label>
    <div class="range-wrap">
      <input type="range" id="cfg-brightness" min="0" max="255" value="255"
             oninput="document.getElementById('cfg-brightness-val').textContent=this.value">
      <span class="range-val" id="cfg-brightness-val">255</span>
    </div>

    <label>Durée par défaut (secondes)</label>
    <div class="range-wrap">
      <input type="range" id="cfg-duration" min="1" max="60" value="5"
             oninput="document.getElementById('cfg-duration-val').textContent=this.value+'s'">
      <span class="range-val" id="cfg-duration-val">5s</span>
    </div>

    <label>Fade steps (fluidité animation)</label>
    <div class="range-wrap">
      <input type="range" id="cfg-fade" min="1" max="50" value="20"
             oninput="document.getElementById('cfg-fade-val').textContent=this.value">
      <span class="range-val" id="cfg-fade-val">20</span>
    </div>

    <label>Couleur par défaut (emplacements)</label>
    <div class="color-row">
      <input type="text" id="cfg-color-hex" placeholder="#7c6cff"
             oninput="syncColorPicker('cfg-color','cfg-color-hex')">
      <input type="color" id="cfg-color" value="#7c6cff"
             oninput="syncColorHex('cfg-color','cfg-color-hex')">
    </div>

    <label>Couleur tiroir (ruban 2)</label>
    <div class="color-row">
      <input type="text" id="cfg-drawer-hex" placeholder="#ffffff"
             oninput="syncColorPicker('cfg-drawer','cfg-drawer-hex')">
      <input type="color" id="cfg-drawer" value="#ffffff"
             oninput="syncColorHex('cfg-drawer','cfg-drawer-hex')">
    </div>

    <button class="btn btn-primary" onclick="saveConfig()" style="margin-top:.85rem">
      💾 Sauvegarder (flash)
    </button>
    <button class="btn btn-secondary" onclick="applyConfig()">
      ⚡ Appliquer sans sauvegarder
    </button>
  </div>

</div>

<footer>StockEleK v6.0 — <span id="footer-ip"></span></footer>

<div class="toast" id="toast"></div>

<script>
const TOKEN = ')rawhtml";
const char HTML_PART2[] PROGMEM = R"rawhtml(';

// Construire les boutons de tiroir A-Z
(function() {
  const sel = document.getElementById('drawer-select');
  for (let i = 0; i < 26; i++) {
    const letter = String.fromCharCode(65 + i);
    const btn = document.createElement('button');
    btn.className = 'drawer-btn';
    btn.textContent = letter;
    btn.dataset.drawer = i;
    btn.onclick = function() {
      document.querySelectorAll('.drawer-btn').forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      document.getElementById('manual-cell').value = letter + '01';
    };
    sel.appendChild(btn);
  }
})();

// Toast
let toastTimer;
function toast(msg, type = 'ok') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast toast-' + type + ' show';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 3000);
}

// Sync color picker <-> hex input
function syncColorHex(pickerId, hexId) {
  const val = document.getElementById(pickerId).value;
  document.getElementById(hexId).value = val;
}
function syncColorPicker(pickerId, hexId) {
  const val = document.getElementById(hexId).value;
  if (/^#[0-9a-fA-F]{6}$/.test(val))
    document.getElementById(pickerId).value = val;
}

// Formater l'uptime
function fmtUptime(sec) {
  if (sec < 60) return sec + 's';
  if (sec < 3600) return Math.floor(sec/60) + 'min ' + (sec%60) + 's';
  return Math.floor(sec/3600) + 'h ' + Math.floor((sec%3600)/60) + 'min';
}

// Rafraîchir le statut
async function refreshStatus() {
  try {
    const r = await fetch('/status', { headers: { 'X-Token': TOKEN } });
    const d = await r.json();

    // Stats
    const ledsEl  = document.getElementById('stat-leds');
    const remEl   = document.getElementById('stat-remaining');
    ledsEl.textContent  = d.leds_on;
    ledsEl.className    = 'stat-val ' + (d.active ? 'ok' : '');
    remEl.textContent   = d.remaining_sec + 's';
    remEl.className     = 'stat-val ' + (d.active ? 'accent' : '');

    const heap = Math.round(d.free_heap / 1024);
    const heapEl = document.getElementById('stat-heap');
    heapEl.textContent = heap + ' Ko';
    heapEl.className   = 'stat-val ' + (heap > 100 ? 'ok' : heap > 50 ? 'warn' : 'err');

    document.getElementById('stat-uptime').textContent = fmtUptime(d.uptime_sec);

    // LED dot
    const dot = document.getElementById('led-active-dot');
    dot.className = 'led-indicator ' + (d.active ? 'led-on pulse' : 'led-off');
    document.getElementById('status-cell').textContent = d.active ? (d.cell || d.leds_on + ' LED(s)') : 'Éteint';

    // Afficheur
    const dispDot = document.getElementById('display-dot');
    dispDot.className = 'led-indicator ' + (d.display_ready ? 'led-on' : 'led-off');
    document.getElementById('status-display').textContent =
      d.display_ready ? (d.display_sleeping ? '💤 Veille' : '✓ Actif') : '✗ Non connecté';

    // Queue
    document.getElementById('status-queue').textContent = d.queue_size + ' / 4';

    // RSSI
    document.getElementById('wifi-rssi').textContent = d.wifi_rssi + ' dBm';
    const wifiDot = document.getElementById('wifi-led');
    wifiDot.className = 'led-indicator ' +
      (d.wifi_rssi > -60 ? 'led-on' : d.wifi_rssi > -75 ? 'led-indicator' : 'led-off');
    wifiDot.style.background = d.wifi_rssi > -60 ? 'var(--success)' : d.wifi_rssi > -75 ? 'var(--warning)' : 'var(--danger)';

  } catch (e) {
    toast('Impossible de joindre l\'ESP32', 'err');
  }
}

// Charger la config courante
async function loadCurrentConfig() {
  try {
    const r = await fetch('/config', { headers: { 'X-Token': TOKEN } });
    const d = await r.json();

    document.getElementById('cfg-brightness').value     = d.brightness;
    document.getElementById('cfg-brightness-val').textContent = d.brightness;
    document.getElementById('cfg-duration').value       = d.duration;
    document.getElementById('cfg-duration-val').textContent   = d.duration + 's';
    document.getElementById('cfg-fade').value           = d.fade_steps;
    document.getElementById('cfg-fade-val').textContent = d.fade_steps;

    // Couleurs
    const toHex = c => /^#/.test(c) ? c : '#7c6cff';
    document.getElementById('cfg-color-hex').value   = d.default_color;
    document.getElementById('cfg-color').value       = toHex(d.default_color);
    document.getElementById('cfg-drawer-hex').value  = d.drawer_color;
    document.getElementById('cfg-drawer').value      = toHex(d.drawer_color);

    toast('Configuration chargée', 'info');
  } catch (e) {
    toast('Erreur chargement config', 'err');
  }
}

// Construire le body config depuis le formulaire
function buildConfigBody(persist) {
  return JSON.stringify({
    brightness:    parseInt(document.getElementById('cfg-brightness').value),
    duration:      parseInt(document.getElementById('cfg-duration').value),
    fade_steps:    parseInt(document.getElementById('cfg-fade').value),
    default_color: document.getElementById('cfg-color-hex').value,
    drawer_color:  document.getElementById('cfg-drawer-hex').value,
    persist:       persist,
  });
}

async function saveConfig() {
  try {
    const r = await fetch('/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Token': TOKEN },
      body: buildConfigBody(true),
    });
    const d = await r.json();
    toast(d.ok ? '💾 Sauvegardé en flash !' : 'Erreur : ' + d.error, d.ok ? 'ok' : 'err');
  } catch (e) { toast('Erreur réseau', 'err'); }
}

async function applyConfig() {
  try {
    const r = await fetch('/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Token': TOKEN },
      body: buildConfigBody(false),
    });
    const d = await r.json();
    toast(d.ok ? '⚡ Appliqué (non sauvegardé)' : 'Erreur', d.ok ? 'info' : 'err');
  } catch (e) { toast('Erreur réseau', 'err'); }
}

// Allumage manuel
async function manualLight() {
  const cell = document.getElementById('manual-cell').value.trim();
  const led  = parseInt(document.getElementById('manual-led').value);
  const color = document.getElementById('manual-color-hex').value;
  const dur  = parseInt(document.getElementById('manual-duration').value);

  // Trouver le tiroir actif
  const activeDrawerBtn = document.querySelector('.drawer-btn.active');
  const drawer = activeDrawerBtn ? parseInt(activeDrawerBtn.dataset.drawer) : -1;

  const leds = !isNaN(led) ? [led] : [];
  if (leds.length === 0 && !cell) { toast('Indique une case ou un index LED', 'err'); return; }

  try {
    const r = await fetch('/leds', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Token': TOKEN },
      body: JSON.stringify({ leds, color, duration: dur, drawer, cell: cell || '' }),
    });
    const d = await r.json();
    toast(d.ok ? (d.queued ? '⏳ Mis en file' : '💡 Allumé !') : 'Erreur', d.ok ? 'ok' : 'err');
    setTimeout(refreshStatus, 500);
  } catch (e) { toast('Erreur réseau', 'err'); }
}

// Éteindre
async function ledOff() {
  try {
    await fetch('/off', { method: 'POST', headers: { 'X-Token': TOKEN } });
    toast('✗ LEDs éteintes', 'info');
    setTimeout(refreshStatus, 500);
  } catch (e) { toast('Erreur réseau', 'err'); }
}

// Chenillard
async function runTest() {
  try {
    const r = await fetch('/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Token': TOKEN },
      body: JSON.stringify({ delay_ms: 60, color: 'green' }),
    });
    const d = await r.json();
    toast(d.ok ? '▶ Chenillard lancé' : 'Erreur', d.ok ? 'ok' : 'err');
  } catch (e) { toast('Erreur réseau', 'err'); }
}

// Reboot
async function rebootEsp() {
  if (!confirm("Redemarrer ESP32 ?")) return;
  try {
    const r = await fetch("/reboot", {
      method: "POST",
      headers: { "X-Token": TOKEN },
    });
    const d = await r.json();
    toast(d.ok ? "Reboot en cours..." : "Erreur", d.ok ? "info" : "err");
    if (d.ok) setTimeout(() => location.reload(), 5000);
  } catch (e) {
    toast("ESP32 redemarre...", "info");
    setTimeout(() => location.reload(), 6000);
  }
}

// Init
async function init() {
  // Afficher l'IP dans le header
  try {
    const r = await fetch('/ping');
    const d = await r.json();
    const ip = window.location.hostname;
    document.getElementById('header-ip').textContent = 'http://' + ip + '  •  ' + d.leds + ' LEDs  •  ' + d.drawers + ' tiroirs';
    document.getElementById('footer-ip').textContent = 'http://' + ip;
  } catch (e) {}

  await refreshStatus();
  await loadCurrentConfig();

  // Rafraîchissement auto toutes les 5s
  setInterval(refreshStatus, 5000);
}

init();
</script>
</body>
</html>
)rawhtml";

// ======================================================================
//  HANDLERS HTTP
// ======================================================================

void handleRoot() {
    addCORSHeaders();
    // Construire la page en injectant le token entre les deux morceaux HTML
    String page;
    page.reserve(12000);
    // HTML_PART1 et HTML_PART2 sont en PROGMEM — les lire chunk par chunk
    const char* p1 = HTML_PART1;
    while (pgm_read_byte(p1)) page += (char)pgm_read_byte(p1++);
    page += String(AUTH_TOKEN);
    const char* p2 = HTML_PART2;
    while (pgm_read_byte(p2)) page += (char)pgm_read_byte(p2++);
    server.send(200, "text/html", page);
}

void handleLeds() {
    Serial.println("\n[POST /leds]");
    if (!checkAuth()) return;
    if (!server.hasArg("plain")) { sendJSON(400,"{\"ok\":false}"); return; }
    StaticJsonDocument<1024> doc;
    if (deserializeJson(doc, server.arg("plain"))) { sendJSON(400,"{\"ok\":false,\"error\":\"invalid JSON\"}"); return; }

    LedCommand cmd;
    cmd.valid    = true;
    cmd.color    = parseColor(doc["color"]);
    cmd.duration = doc["duration"] | cfg.duration;
    cmd.drawer   = doc["drawer"]   | -1;
    cmd.count    = 0;
    cmd.drawerColor = doc.containsKey("drawer_color")
                      ? parseColor(doc["drawer_color"])
                      : parseColorStr(cfg.drawerColor);
    const char* cellStr = doc["cell"] | "";
    strncpy(cmd.cell, cellStr, sizeof(cmd.cell)-1); cmd.cell[sizeof(cmd.cell)-1]='\0';
    for (int idx : doc["leds"].as<JsonArray>())
        if (idx >= 0 && idx < NUM_LEDS && cmd.count < MAX_LEDS_PER_CMD)
            cmd.indices[cmd.count++] = idx;
    Serial.printf("[LEDs]   %d LED(s) case=%s tiroir=%s\n",
                  cmd.count, cmd.cell,
                  cmd.drawer >= 0 ? String((char)('A'+cmd.drawer)).c_str() : "-");
    if (ledActive) {
        if (enqueue(cmd)) sendJSON(202,"{\"ok\":true,\"queued\":true}");
        else              sendJSON(503,"{\"ok\":false,\"error\":\"queue full\"}");
    } else { execCommand(cmd); sendJSON(200,"{\"ok\":true,\"queued\":false}"); }
}

void handleOff() {
    if (!checkAuth()) return;
    testRunning = false; ledActive = false; qHead=qTail=qCount=0;
    fadeOut(currentIndices, currentCount); clearDrawerLed();
    displayClear(); displayLastActive = millis();
    currentCount=0; currentDrawer=-1; currentCell[0]='\0';
    ws.broadcastTXT("{\"event\":\"off\"}");
    sendJSON(200,"{\"ok\":true}");
}

void handleStatus() {
    unsigned long rem = (ledActive && millis()<ledOffAt) ? (ledOffAt-millis())/1000 : 0;
    String ind="[";
    for (int i=0;i<currentCount;i++){if(i)ind+=",";ind+=currentIndices[i];} ind+="]";
    sendJSON(200,
        "{\"ok\":true"
        ",\"active\":"           + String(ledActive?"true":"false") +
        ",\"leds_on\":"          + String(currentCount) +
        ",\"indices\":"          + ind +
        ",\"drawer\":"           + String(currentDrawer) +
        ",\"cell\":\""           + String(currentCell) + "\"" +
        ",\"remaining_sec\":"    + String(rem) +
        ",\"queue_size\":"       + String(qCount) +
        ",\"num_leds\":"         + String(NUM_LEDS) +
        ",\"display_ready\":"    + String(displayReady?"true":"false") +
        ",\"display_sleeping\":" + String(displaySleeping?"true":"false") +
        ",\"wifi_rssi\":"        + String(WiFi.RSSI()) +
        ",\"free_heap\":"        + String(ESP.getFreeHeap()) +
        ",\"uptime_sec\":"       + String(millis()/1000) + "}");
}

void handlePing() {
    sendJSON(200,
        "{\"ok\":true"
        ",\"leds\":"      + String(NUM_LEDS) +
        ",\"drawers\":"   + String(NUM_DRAWERS) +
        ",\"display\":"   + String(displayReady?"true":"false") +
        ",\"rssi\":"      + String(WiFi.RSSI()) +
        ",\"free_heap\":" + String(ESP.getFreeHeap()) +
        ",\"uptime\":"    + String(millis()/1000) + "}");
}

void handleTest() {
    if (!checkAuth()) return;
    StaticJsonDocument<256> doc;
    if (server.hasArg("plain")) deserializeJson(doc, server.arg("plain"));
    testOffset  = constrain((int)(doc["offset"]|0),      0, NUM_LEDS-1);
    testCount_  = constrain((int)(doc["count"]|NUM_LEDS), 1, NUM_LEDS-testOffset);
    testDelayMs = doc["delay_ms"] | 80;
    testColor   = doc["color"].isNull() ? CRGB::Green : parseColor(doc["color"]);
    testStep=testOffset; testRunning=true; testNextAt=millis(); ledActive=false;
    fill_solid(leds,NUM_LEDS,CRGB::Black); clearDrawerLed(); FastLED.show();
    displayText("TEST");
    sendJSON(200,"{\"ok\":true,\"offset\":"+String(testOffset)+",\"count\":"+String(testCount_)+"}");
}

// ======================================================================
//  GET /config + POST /config — v6.0
// ======================================================================

void handleGetConfig() {
    if (!checkAuth()) return;
    sendJSON(200,
        "{\"ok\":true"
        ",\"brightness\":"    + String(cfg.brightness) +
        ",\"duration\":"      + String(cfg.duration) +
        ",\"fade_steps\":"    + String(cfg.fadeSteps) +
        ",\"default_color\":\"" + String(cfg.defaultColor) + "\"" +
        ",\"drawer_color\":\"" + String(cfg.drawerColor) + "\"}");
}

void handleSetConfig() {
    if (!checkAuth()) return;
    if (!server.hasArg("plain")) { sendJSON(400,"{\"ok\":false}"); return; }
    StaticJsonDocument<256> doc;
    if (deserializeJson(doc, server.arg("plain"))) { sendJSON(400,"{\"ok\":false,\"error\":\"invalid JSON\"}"); return; }

    bool changed = false;

    if (doc.containsKey("brightness")) {
        cfg.brightness = constrain((int)doc["brightness"], 0, 255);
        FastLED.setBrightness(cfg.brightness); FastLED.show();
        changed = true;
    }
    if (doc.containsKey("duration")) {
        cfg.duration = constrain((int)doc["duration"], 1, 3600);
        changed = true;
    }
    if (doc.containsKey("fade_steps")) {
        cfg.fadeSteps = constrain((int)doc["fade_steps"], 1, 50);
        changed = true;
    }
    if (doc.containsKey("default_color")) {
        strlcpy(cfg.defaultColor, doc["default_color"] | DEFAULT_COLOR_STR, sizeof(cfg.defaultColor));
        changed = true;
    }
    if (doc.containsKey("drawer_color")) {
        strlcpy(cfg.drawerColor, doc["drawer_color"] | DEFAULT_DRAWER_COLOR_STR, sizeof(cfg.drawerColor));
        changed = true;
    }

    bool persist = doc["persist"] | false;
    if (persist && changed) saveConfig();

    Serial.printf("[CFG]    brightness=%d dur=%ds fade=%d color=%s drawer=%s persist=%s\n",
                  cfg.brightness, cfg.duration, cfg.fadeSteps,
                  cfg.defaultColor, cfg.drawerColor, persist?"oui":"non");

    sendJSON(200,
        "{\"ok\":true"
        ",\"brightness\":"    + String(cfg.brightness) +
        ",\"duration\":"      + String(cfg.duration) +
        ",\"fade_steps\":"    + String(cfg.fadeSteps) +
        ",\"default_color\":\"" + String(cfg.defaultColor) + "\"" +
        ",\"drawer_color\":\"" + String(cfg.drawerColor) + "\""
        ",\"saved\":"         + String(persist?"true":"false") + "}");
}

void handleOptions() { addCORSHeaders(); server.send(204); }

// ======================================================================
//  POST /reboot — v6.1
// ======================================================================

void handleReboot() {
    if (!checkAuth()) return;
    sendJSON(200, "{\"ok\":true,\"message\":\"Reboot dans 1s...\"}"); 
    Serial.println("[REBOOT] Redémarrage demandé via /reboot");
    delay(500);
    ESP.restart();
}

// ======================================================================
//  WEBSOCKET
// ======================================================================

void onWebSocketEvent(uint8_t num, WStype_t type, uint8_t* payload, size_t length) {
    if (type == WStype_CONNECTED)
        ws.sendTXT(num,
            "{\"event\":\"welcome\""
            ",\"leds\":"    + String(NUM_LEDS) +
            ",\"drawers\":" + String(NUM_DRAWERS) +
            ",\"display\":" + String(displayReady?"true":"false") + "}");
}

// ======================================================================
//  SETUP
// ======================================================================

void setup() {
    Serial.begin(115200); delay(500);
    Serial.println("\n+======================================+");
    Serial.println("|  StockEleK — Firmware LED v6.0       |");
    Serial.println("|  Page web : http://[IP]/             |");
    Serial.println("|  Config   : POST /config             |");
    Serial.println("+======================================+\n");

    for (int i = 0; i < QUEUE_SIZE; i++) cmdQueue[i].valid = false;

    // Config depuis Preferences
    loadConfig();

    // HT16K33
    Wire.begin(DISPLAY_SDA, DISPLAY_SCL);
    if (display.begin(DISPLAY_ADDR)) {
        displayReady = true;
        display.setBrightness(DISPLAY_BRIGHT);
        display.clear();
        for (int d=0;d<4;d++) display.writeDigitRaw(d, 0b0000000001000000);
        display.writeDisplay();
        Serial.println("[DISP]   HT16K33 OK");
    } else {
        Serial.println("[DISP]   HT16K33 non trouve — simulation Serial");
    }

    // LEDs
    FastLED.addLeds<WS2812B, LED_PIN,    BGR>(leds,       NUM_LEDS);
    FastLED.addLeds<WS2812B, DRAWER_PIN, BGR>(drawerLeds, NUM_DRAWERS);
    FastLED.setBrightness(cfg.brightness);
    fill_solid(leds,NUM_LEDS,CRGB::Black); fill_solid(drawerLeds,NUM_DRAWERS,CRGB::Black);
    FastLED.show();

    // WiFi
    WiFi.begin(SSID, PASSWORD);
    Serial.print("[WiFi]   Connexion");
    while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
    Serial.println("\n[WiFi]   IP = " + WiFi.localIP().toString() +
                   "  RSSI = " + String(WiFi.RSSI()) + " dBm");
    Serial.println("[Web]    Ouvre : http://" + WiFi.localIP().toString() + "/");
    wifiWasConnected = true; wifiLastCheck = millis();

    // OTA
    ArduinoOTA.setHostname("stockelek-leds");
    ArduinoOTA.setPassword("stockelek-ota");
    ArduinoOTA.onStart([]()   { Serial.println("[OTA]    Demarrage..."); });
    ArduinoOTA.onEnd([]()     { Serial.println("\n[OTA]    Termine."); });
    ArduinoOTA.onProgress([](unsigned int p, unsigned int t) { Serial.printf("[OTA]    %u%%\r", p*100/t); });
    ArduinoOTA.onError([](ota_error_t e) { Serial.println("[OTA]    Erreur "+String(e)); });
    ArduinoOTA.begin();

    // WebSocket
    ws.begin(); ws.onEvent(onWebSocketEvent);

    // HTTP routes
    const char* headers[] = {"X-Token"};
    server.collectHeaders(headers, 1);
    server.on("/",       HTTP_GET,     handleRoot);
    server.on("/leds",   HTTP_POST,    handleLeds);
    server.on("/off",    HTTP_POST,    handleOff);
    server.on("/test",   HTTP_POST,    handleTest);
    server.on("/status", HTTP_GET,     handleStatus);
    server.on("/ping",   HTTP_GET,     handlePing);
    server.on("/config", HTTP_GET,     handleGetConfig);
    server.on("/config", HTTP_POST,    handleSetConfig);
    // Preflight CORS
    server.on("/leds",   HTTP_OPTIONS, handleOptions);
    server.on("/off",    HTTP_OPTIONS, handleOptions);
    server.on("/test",   HTTP_OPTIONS, handleOptions);
    server.on("/config", HTTP_OPTIONS, handleOptions);
    server.on("/reboot", HTTP_POST,    handleReboot);
    server.on("/reboot", HTTP_OPTIONS, handleOptions);
    server.begin();
    Serial.println("[HTTP]   Pret sur port 80");
    Serial.println("[Heap]   " + String(ESP.getFreeHeap()) + " octets libres\n");

    bootSweep();
    if (displayReady) { delay(800); displayClear(); displayLastActive=millis(); }
    Serial.println("[READY]  En attente — http://" + WiFi.localIP().toString() + "/\n");
}

// ======================================================================
//  LOOP
// ======================================================================

void loop() {
    server.handleClient();
    ws.loop();
    ArduinoOTA.handle();
    wifiWatchdog();

    if (ledActive && millis() >= ledOffAt) {
        fadeOut(currentIndices, currentCount); clearDrawerLed();
        displayClear(); displayLastActive=millis();
        currentCount=0; currentDrawer=-1; currentCell[0]='\0';
        ledActive=false;
        ws.broadcastTXT("{\"event\":\"off\"}");
        processQueue();
    }

    displaySleepTick();
    drawerBreatheTick();

    if (testRunning && millis() >= testNextAt) {
        if (testStep > testOffset) leds[testStep-1] = CRGB::Black;
        if (testStep < testOffset + testCount_) {
            leds[testStep] = testColor; FastLED.show();
            testNextAt = millis() + testDelayMs; testStep++;
        } else {
            fill_solid(leds,NUM_LEDS,CRGB::Black); FastLED.show();
            testRunning=false; displayClear(); displayLastActive=millis();
            ws.broadcastTXT("{\"event\":\"test_done\"}");
        }
    }
}
