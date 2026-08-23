/*
  HerPulse — example Wi-Fi POST from an ESP32 / Arduino Q board
  to the Flask backend's /api/device/data endpoint.

  Sends the raw R/G/B triplet from each of the 3 sensor channels
  (Hb, Protein, pH) exactly as the trained Random Forest model expects —
  no pre-computed values. The backend derives the "Ratio" feature itself.

  Swap the placeholder rXX/gXX/bXX values below for real sensor reads
  once the pad sensor is wired up.
*/

#include <WiFi.h>
#include <HTTPClient.h>

const char* WIFI_SSID     = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

const char* SERVER_URL   = "http://192.168.1.5:5000/api/device/data"; // your laptop's LAN IP while dev testing
const char* DEVICE_ID    = "HerPulse_Q";
const char* DEVICE_KEY   = "herpulse-device-key"; // must match HERPULSE_DEVICE_KEY in app.py

void setup() {
  Serial.begin(115200);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting to Wi-Fi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(400);
    Serial.print(".");
  }
  Serial.println("\nConnected. IP: " + WiFi.localIP().toString());
}

void sendReading(int rHb, int gHb, int bHb,
                  int rProtein, int gProtein, int bProtein,
                  int rPh, int gPh, int bPh) {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);

  String body = String("{\"device_id\":\"") + DEVICE_ID +
                "\",\"r_hb\":" + rHb + ",\"g_hb\":" + gHb + ",\"b_hb\":" + bHb +
                ",\"r_protein\":" + rProtein + ",\"g_protein\":" + gProtein + ",\"b_protein\":" + bProtein +
                ",\"r_ph\":" + rPh + ",\"g_ph\":" + gPh + ",\"b_ph\":" + bPh + "}";

  int code = http.POST(body);
  Serial.println("POST -> " + String(code) + " : " + http.getString());
  http.end();
}

void loop() {
  // Replace with real sensor reads (e.g. from an RGB color sensor per pad zone).
  int rHb = 192, gHb = 65, bHb = 36;
  int rProtein = 171, gProtein = 84, bProtein = 78;
  int rPh = 164, gPh = 155, bPh = 83;

  sendReading(rHb, gHb, bHb, rProtein, gProtein, bProtein, rPh, gPh, bPh);
  delay(5000);
}
