/*
 * universal_field.ino — ESP32 universal OT field-device firmware
 * ---------------------------------------------------------------------------
 * One binary flashes to the entire fleet. Per-device identity is derived from
 * the chip MAC, so no per-board edits are needed. Role is stored in NVS and
 * defaults to "grid"; it is swappable at runtime via MQTT (cmd/<id>/role) or
 * HTTP (POST /role). Only the grid role is implemented today; the others are
 * reserved so the fleet architecture stays intact.
 *
 * Grid role models one feeder bay of a distribution substation
 * (12.47 kV system, 7.2 kV phase-to-neutral). All analog tags are derived
 * from a single slow-moving load factor so the telemetry is internally
 * coherent instead of independent noise. breaker_status is the discrete
 * control tag and the primary attack surface (Industroyer / 2016 Ukraine
 * TTP): opening it collapses feeder current and real power while the bus
 * voltage holds — a clean, detectable signature.
 *
 * First flash MUST be over USB (this is the firmware that adds the OTA
 * handler). Every reflash after this can go over Tailscale via ArduinoOTA.
 * ---------------------------------------------------------------------------
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <Preferences.h>
#include <ArduinoOTA.h>
#include <ESPmDNS.h>
#include <WebServer.h>
#include <esp_system.h>
#include "secrets.h"

#define FW_VERSION "1.0.0-grid"
#define PUBLISH_MS 2000

Preferences prefs;
WiFiClient  net;
PubSubClient mqtt(net);
WebServer   server(80);

// ---- identity (derived from MAC) ----
String role;         // active role from NVS, default "grid"
String boardShort;   // MAC tail, e.g. "3ca4f2"
String deviceName;   // e.g. "grid-substation-3ca4f2"
String topicBase;    // e.g. "grid/3ca4f2"
float  boardOffset = 0.0f;   // ±0.05 load bias, deterministic per board

// ---- physics state ----
float loadWalk    = 0.60f;
float curLoad     = 0.60f;
float voltage[3];
float current[3];
float frequency   = 60.00f;
float powerFactor = 0.97f;
float realPowerKw = 0.0f;
float xfmrTemp    = 55.0f;
bool  breakerClosed = true;

unsigned long lastPublish = 0;

// ---- prototypes ----
void publishTag(const char* tag, float value);
void publishGrid();
void updatePhysics();
void connectMQTT();

// ---------------------------------------------------------------------------
// Identity
// ---------------------------------------------------------------------------
void deriveIdentity() {
  uint8_t mac[6];
  WiFi.macAddress(mac);   // stable across ESP32 core versions (avoids esp_read_mac API drift)
  char buf[8];
  snprintf(buf, sizeof(buf), "%02x%02x%02x", mac[3], mac[4], mac[5]);
  boardShort = String(buf);
  deviceName = "grid-substation-" + boardShort;
  topicBase  = "grid/" + boardShort;

  uint32_t seed = ((uint32_t)mac[3] << 16) | ((uint32_t)mac[4] << 8) | mac[5];
  boardOffset = (((seed % 100) / 100.0f) - 0.5f) * 0.10f;  // ±0.05
  randomSeed(seed);
}

// ---------------------------------------------------------------------------
// Connectivity
// ---------------------------------------------------------------------------
void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(400); Serial.print("."); }
  Serial.println(" " + WiFi.localIP().toString());
}

void setupMDNS() {
  if (MDNS.begin(("esp32-" + boardShort).c_str())) {
    MDNS.addService("http", "tcp", 80);
  }
}

void setupOTA() {
  ArduinoOTA.setHostname(("esp32-" + boardShort).c_str());
  ArduinoOTA.setPassword(OTA_PASSWORD);
  ArduinoOTA.begin();
}

// ---------------------------------------------------------------------------
// HTTP control plane
// ---------------------------------------------------------------------------
void handleInfo() {
  char body[512];
  snprintf(body, sizeof(body),
    "{\"device\":\"%s\",\"short\":\"%s\",\"role\":\"%s\",\"fw\":\"%s\","
    "\"ip\":\"%s\",\"rssi\":%d,\"uptime_s\":%lu,\"breaker\":\"%s\",\"load\":%.3f}",
    deviceName.c_str(), boardShort.c_str(), role.c_str(), FW_VERSION,
    WiFi.localIP().toString().c_str(), WiFi.RSSI(), millis() / 1000,
    breakerClosed ? "closed" : "open", curLoad);
  server.send(200, "application/json", body);
}

void handleRoles() {
  String body = "{\"active\":\"" + role + "\",\"available\":[\"grid\"],"
                "\"reserved\":[\"substation\",\"water\",\"bms\",\"datacenter\",\"pipeline\"]}";
  server.send(200, "application/json", body);
}

void handleSetRole() {
  if (!server.hasArg("role")) { server.send(400, "text/plain", "missing role arg"); return; }
  String r = server.arg("role");
  prefs.begin("cfg", false);
  prefs.putString("role", r);
  prefs.end();
  server.send(200, "text/plain", "role set to " + r + ", rebooting");
  delay(300);
  ESP.restart();
}

// ---------------------------------------------------------------------------
// MQTT command plane
// ---------------------------------------------------------------------------
void onMessage(char* topic, byte* payload, unsigned int len) {
  String t = String(topic);
  String msg; msg.reserve(len);
  for (unsigned int i = 0; i < len; i++) msg += (char)payload[i];
  msg.trim();

  if (t.endsWith("/breaker")) {            // cmd/<id>/breaker : open|close
    if (msg == "open")  breakerClosed = false;
    if (msg == "close") breakerClosed = true;
    publishTag("breaker_status", breakerClosed ? 1 : 0);
  } else if (t.endsWith("/role")) {        // cmd/<id>/role : <rolename>
    prefs.begin("cfg", false);
    prefs.putString("role", msg);
    prefs.end();
    delay(200);
    ESP.restart();
  }
}

void connectMQTT() {
  while (!mqtt.connected()) {
    String willTopic = topicBase + "/status";
    if (mqtt.connect(deviceName.c_str(), MQTT_USER, MQTT_PASS,
                     willTopic.c_str(), 0, true, "offline")) {  // LWT
      mqtt.publish(willTopic.c_str(), "online", true);          // birth (retained)
      mqtt.subscribe(("cmd/" + boardShort + "/#").c_str());
      mqtt.subscribe("cmd/all/#");
      Serial.println("MQTT connected as " + deviceName);
    } else {
      Serial.print("MQTT rc="); Serial.println(mqtt.state());
      delay(2000);
    }
  }
}

void publishTag(const char* tag, float value) {
  char topic[96], payload[96];
  snprintf(topic, sizeof(topic), "%s/%s", topicBase.c_str(), tag);
  snprintf(payload, sizeof(payload),
           "{\"value\":%.3f,\"device\":\"%s\"}", value, deviceName.c_str());
  mqtt.publish(topic, payload);
}

// ---------------------------------------------------------------------------
// Coupled distribution-feeder model
// ---------------------------------------------------------------------------
void updatePhysics() {
  loadWalk += (random(-20, 21) / 1000.0f);           // ±0.02 random walk
  loadWalk  = constrain(loadWalk, 0.30f, 0.95f);
  float diurnal = 0.10f * sinf((millis() / 600000.0f) * 6.2832f);  // ~10-min curve (demo-compressed)
  curLoad = constrain(loadWalk + diurnal + boardOffset, 0.20f, 0.99f);

  float ld = breakerClosed ? curLoad : 0.0f;          // open breaker de-energizes the feeder

  for (int i = 0; i < 3; i++) {
    float imbalance = 1.0f + ((i - 1) * 0.004f);      // ~0.4% phase spread
    voltage[i] = (7250.0f * (1.0f - 0.015f * curLoad)) * imbalance + (random(-30, 31));
    current[i] = breakerClosed
                   ? (150.0f + 200.0f * ld) * imbalance + (random(-8, 9))
                   : (random(0, 3));                  // leakage-level residual
  }

  frequency += (random(-4, 5) / 1000.0f);
  frequency += (60.00f - frequency) * 0.05f;          // pull toward nominal
  frequency  = constrain(frequency, 59.95f, 60.05f);

  powerFactor = constrain(0.985f - 0.06f * ld + (random(-5, 6) / 1000.0f), 0.90f, 0.995f);

  float pSum = voltage[0] * current[0] + voltage[1] * current[1] + voltage[2] * current[2];
  realPowerKw = (pSum * powerFactor) / 1000.0f;

  float target = 45.0f + 30.0f * ld;                  // thermal lag toward load
  xfmrTemp += (target - xfmrTemp) * 0.03f;
}

void publishGrid() {
  publishTag("voltage_a", voltage[0]);
  publishTag("voltage_b", voltage[1]);
  publishTag("voltage_c", voltage[2]);
  publishTag("current_a", current[0]);
  publishTag("current_b", current[1]);
  publishTag("current_c", current[2]);
  publishTag("frequency", frequency);
  publishTag("power_factor", powerFactor);
  publishTag("real_power_kw", realPowerKw);
  publishTag("transformer_temp", xfmrTemp);
  publishTag("breaker_status", breakerClosed ? 1 : 0);
}

// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(200);

  prefs.begin("cfg", true);
  role = prefs.getString("role", "grid");
  prefs.end();

  connectWiFi();
  deriveIdentity();
  setupMDNS();
  setupOTA();

  server.on("/info",  handleInfo);
  server.on("/roles", handleRoles);
  server.on("/role",  HTTP_POST, handleSetRole);
  server.begin();

  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setBufferSize(512);
  mqtt.setCallback(onMessage);

  Serial.println("Booted " + deviceName + " role=" + role + " fw=" FW_VERSION);
}

void loop() {
  ArduinoOTA.handle();
  server.handleClient();
  if (!mqtt.connected()) connectMQTT();
  mqtt.loop();

  if (millis() - lastPublish >= PUBLISH_MS) {
    lastPublish = millis();
    updatePhysics();
    publishGrid();
  }
}
