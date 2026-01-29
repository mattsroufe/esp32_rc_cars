#ifndef WEB_CONTROL_H
#define WEB_CONTROL_H

#include "secrets.h"
#include "config.h"
#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoWebsockets.h>
#include "soc/rtc_cntl_reg.h"
#include "esp_camera.h"
#include <SD.h>
#include "ServoControl.h"
#include "Esc.h"

// =============================================================================
// Camera Pin Configuration (AI Thinker Board)
// =============================================================================
namespace CameraPins {
    constexpr int PWDN = 32;
    constexpr int RESET = -1;
    constexpr int XCLK = 0;
    constexpr int SIOD = 26;
    constexpr int SIOC = 27;
    constexpr int Y9 = 35;
    constexpr int Y8 = 34;
    constexpr int Y7 = 39;
    constexpr int Y6 = 36;
    constexpr int Y5 = 21;
    constexpr int Y4 = 19;
    constexpr int Y3 = 18;
    constexpr int Y2 = 5;
    constexpr int VSYNC = 25;
    constexpr int HREF = 23;
    constexpr int PCLK = 22;
}

// =============================================================================
// Connection Configuration
// =============================================================================
namespace ConnectionConfig {
    constexpr unsigned long WIFI_TIMEOUT_MS = 30000;
    constexpr unsigned long WIFI_RETRY_DELAY_MS = 500;
    constexpr unsigned long WS_RETRY_DELAY_MS = 1000;
    constexpr unsigned long WS_RECONNECT_INTERVAL_MS = 5000;
    constexpr int MAX_RECONNECT_ATTEMPTS = 5;
}

// =============================================================================
// Global Objects
// =============================================================================
using namespace websockets;

namespace {
    WebsocketsClient wsClient;

    // Dummy servos to increment PWM channels (camera uses channels 0-1)
    ServoControl dummyServo1(Pins::DUMMY);
    ServoControl dummyServo2(Pins::DUMMY);

    // Actual control objects
    ServoControl steeringServo;
    Esc esc;

    // Timing
    unsigned long lastCommandTime = 0;
    unsigned long lastReconnectAttempt = 0;
    int reconnectAttempts = 0;

    // Connection state
    bool wsConnected = false;
}

// =============================================================================
// WebSocket Handlers
// =============================================================================
void onMessageCallback(WebsocketsMessage message) {
    lastCommandTime = millis();
    String command = message.data();

    if (command.startsWith("MOTOR:")) {
        int speed = command.substring(6).toInt();
        speed = constrain(speed, EscConfig::MIN_THROTTLE, EscConfig::MAX_THROTTLE);
        esc.control(speed);
    }
    else if (command.startsWith("SERVO:")) {
        int angle = command.substring(6).toInt();
        angle = constrain(angle, ServoConfig::DEFAULT_MIN_ANGLE, ServoConfig::DEFAULT_MAX_ANGLE);
        steeringServo.control(angle);
    }
    else if (command.startsWith("CONTROL:")) {
        String params = command.substring(8);
        int colonIndex = params.indexOf(':');
        if (colonIndex > 0) {
            int speed = constrain(params.substring(0, colonIndex).toInt(),
                                  EscConfig::MIN_THROTTLE, EscConfig::MAX_THROTTLE);
            int angle = constrain(params.substring(colonIndex + 1).toInt(),
                                  ServoConfig::DEFAULT_MIN_ANGLE, ServoConfig::DEFAULT_MAX_ANGLE);
            esc.control(speed);
            steeringServo.control(angle);
        }
    }
}

void onEventsCallback(WebsocketsEvent event, String data) {
    switch (event) {
        case WebsocketsEvent::ConnectionOpened:
            Serial.println("WebSocket: Connected");
            wsConnected = true;
            reconnectAttempts = 0;
            break;
        case WebsocketsEvent::ConnectionClosed:
            Serial.println("WebSocket: Disconnected");
            wsConnected = false;
            // Safety: reset controls on disconnect
            esc.reset();
            steeringServo.reset();
            break;
        case WebsocketsEvent::GotPing:
            break;
        case WebsocketsEvent::GotPong:
            break;
    }
}

// =============================================================================
// Connection Management
// =============================================================================
bool isWiFiConnected() {
    return WiFi.status() == WL_CONNECTED;
}

bool connectWiFi() {
    if (isWiFiConnected()) {
        return true;
    }

    Serial.print("WiFi: Connecting to ");
    Serial.println(WIFI_SSID);

    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    unsigned long startTime = millis();
    while (!isWiFiConnected()) {
        if (millis() - startTime > ConnectionConfig::WIFI_TIMEOUT_MS) {
            Serial.println("\nWiFi: Connection timeout");
            return false;
        }
        delay(ConnectionConfig::WIFI_RETRY_DELAY_MS);
        Serial.print(".");
    }

    Serial.println();
    Serial.print("WiFi: Connected, IP: ");
    Serial.println(WiFi.localIP());
    return true;
}

bool connectWebSocket() {
    if (wsConnected && wsClient.available()) {
        return true;
    }

    Serial.print("WebSocket: Connecting to ");
    Serial.println(WS_SERVER_URL);

    wsClient.onMessage(onMessageCallback);
    wsClient.onEvent(onEventsCallback);

    if (wsClient.connect(WS_SERVER_URL)) {
        Serial.println("WebSocket: Connected");
        lastCommandTime = millis();
        return true;
    }

    Serial.println("WebSocket: Connection failed");
    return false;
}

void checkConnections() {
    unsigned long now = millis();

    // Check WiFi
    if (!isWiFiConnected()) {
        Serial.println("WiFi: Connection lost, reconnecting...");
        wsConnected = false;
        esc.reset();
        steeringServo.reset();
        connectWiFi();
        return;
    }

    // Check WebSocket
    if (!wsConnected || !wsClient.available()) {
        if (now - lastReconnectAttempt >= ConnectionConfig::WS_RECONNECT_INTERVAL_MS) {
            lastReconnectAttempt = now;

            if (reconnectAttempts < ConnectionConfig::MAX_RECONNECT_ATTEMPTS) {
                Serial.printf("WebSocket: Reconnect attempt %d/%d\n",
                              reconnectAttempts + 1,
                              ConnectionConfig::MAX_RECONNECT_ATTEMPTS);
                reconnectAttempts++;

                if (connectWebSocket()) {
                    reconnectAttempts = 0;
                }
            } else {
                // Reset counter periodically to allow future reconnects
                if (now - lastReconnectAttempt >= ConnectionConfig::WS_RECONNECT_INTERVAL_MS * 10) {
                    reconnectAttempts = 0;
                }
            }
        }
    }
}

// =============================================================================
// Camera Initialization
// =============================================================================
esp_err_t initCamera() {
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = CameraPins::Y2;
    config.pin_d1 = CameraPins::Y3;
    config.pin_d2 = CameraPins::Y4;
    config.pin_d3 = CameraPins::Y5;
    config.pin_d4 = CameraPins::Y6;
    config.pin_d5 = CameraPins::Y7;
    config.pin_d6 = CameraPins::Y8;
    config.pin_d7 = CameraPins::Y9;
    config.pin_xclk = CameraPins::XCLK;
    config.pin_pclk = CameraPins::PCLK;
    config.pin_vsync = CameraPins::VSYNC;
    config.pin_href = CameraPins::HREF;
    config.pin_sscb_sda = CameraPins::SIOD;
    config.pin_sscb_scl = CameraPins::SIOC;
    config.pin_pwdn = CameraPins::PWDN;
    config.pin_reset = CameraPins::RESET;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 10;
    config.fb_count = 2;

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("Camera: Init failed (0x%x)\n", err);
        return err;
    }

    Serial.println("Camera: Initialized");
    return ESP_OK;
}

// =============================================================================
// Main Functions
// =============================================================================
void setup() {
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

    Serial.begin(115200);
    Serial.setDebugOutput(true);
    Serial.println("\n=== ESP32 RC Car Starting ===");

    // Free SD card pins
    SD.end();

    // Initialize camera
    if (initCamera() != ESP_OK) {
        Serial.println("Camera init failed, restarting...");
        delay(1000);
        ESP.restart();
    }

    // Initialize controls
    steeringServo.initialize();
    esc.initialize();
    Serial.println("Controls: Initialized");

    // Connect to network
    if (!connectWiFi()) {
        Serial.println("WiFi failed, restarting...");
        delay(1000);
        ESP.restart();
    }

    // Connect to WebSocket server
    connectWebSocket();

    lastCommandTime = millis();
    Serial.println("=== Setup Complete ===");
}

void loop() {
    // Check and maintain connections
    checkConnections();

    // Safety timeout - reset controls if no commands received
    if (millis() - lastCommandTime >= Timing::COMMAND_TIMEOUT_MS) {
        esc.reset();
        steeringServo.reset();
    }

    // Send camera frames if connected
    if (wsConnected && wsClient.available()) {
        camera_fb_t* fb = esp_camera_fb_get();
        if (fb) {
            wsClient.sendBinary(reinterpret_cast<const char*>(fb->buf), fb->len);
            esp_camera_fb_return(fb);
        }
        wsClient.poll();
    }
}

#endif // WEB_CONTROL_H
