#include "secrets.h"
#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoWebsockets.h>
#include "esp_camera.h"
#include "ServoControl.h"
#include "Esc.h"

using namespace websockets;
WebsocketsClient client;

// ==== Hardware ====
ServoControl steeringServo;
Esc esc;

// ==== FreeRTOS handles ====
TaskHandle_t networkTaskHandle;
TaskHandle_t cameraTaskHandle;
TaskHandle_t controlTaskHandle;

// ==== Queues ====
QueueHandle_t controlQueue;     // For motor commands
QueueHandle_t frameQueue;       // For camera frames

// ==== Timeout ====
unsigned long lastCommandTime = 0;
const int COMMAND_TIMEOUT = 100; // ms

// ==== Control struct ====
struct ControlCommand {
  int speed; // -255 to 255
  int angle; // 0–180
};

// ==== Camera Init ====
esp_err_t init_camera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = 5;
  config.pin_d1 = 18;
  config.pin_d2 = 19;
  config.pin_d3 = 21;
  config.pin_d4 = 36;
  config.pin_d5 = 39;
  config.pin_d6 = 34;
  config.pin_d7 = 35;
  config.pin_xclk = 0;
  config.pin_pclk = 22;
  config.pin_vsync = 25;
  config.pin_href = 23;
  config.pin_sscb_sda = 26;
  config.pin_sscb_scl = 27;
  config.pin_pwdn = 32;
  config.pin_reset = -1;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 7;
  config.fb_count = 2; // double buffer for smoother streaming

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return err;
  }

  Serial.println("Camera initialized successfully.");
  return ESP_OK;
}

// ==== Wi-Fi and WebSocket Init ====
esp_err_t init_wifi() {
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.println("Connecting to WiFi...");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Connected!");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());

  client.onEvent([](WebsocketsEvent event, String data) {
    if (event == WebsocketsEvent::ConnectionOpened) Serial.println("WebSocket Connected!");
    if (event == WebsocketsEvent::ConnectionClosed) Serial.println("WebSocket Closed!");
  });

  client.onMessage([](WebsocketsMessage message) {
    String command = message.data();
    lastCommandTime = millis();

    if (command.startsWith("CONTROL:")) {
      String params = command.substring(8);
      int colon = params.indexOf(':');
      int speed = constrain(params.substring(0, colon).toInt(), -255, 255);
      int angle = constrain(params.substring(colon + 1).toInt(), 0, 180);

      ControlCommand cmd = {speed, angle};
      xQueueOverwrite(controlQueue, &cmd);
    }
  });

  while (!client.connect(WS_SERVER_URL)) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWebSocket connected.");
  return ESP_OK;
}

// ==== Camera Task with overwrite ====
void cameraTask(void *pvParameters) {
    camera_fb_t *fb = nullptr;
    camera_fb_t *old_fb = nullptr;

    while (true) {
        fb = esp_camera_fb_get();
        if (!fb) {
            vTaskDelay(1);
            continue;
        }

        // Overwrite any old frame in the queue
        if (xQueueReceive(frameQueue, &old_fb, 0) == pdTRUE) {
            // There was an old frame; return its buffer
            esp_camera_fb_return(old_fb);
        }

        // Push the new frame
        xQueueSend(frameQueue, &fb, portMAX_DELAY);

        vTaskDelay(1);
    }
}

// ==== Network Task optimized for high FPS ====
void networkTask(void *pvParameters) {
    camera_fb_t *fb = nullptr;

    while (true) {
        // Handle incoming messages
        client.poll();

        // Try to get the latest frame
        if (xQueueReceive(frameQueue, &fb, 0) == pdTRUE) {
            if (client.available()) {
                client.sendBinary((const char *)fb->buf, fb->len);
            }
            // Return the buffer after sending
            esp_camera_fb_return(fb);
        }

        // Very short delay to yield to other tasks
        vTaskDelay(1); 
    }
}

// ==== Control Task ====
void controlTask(void *pvParameters) {
  ControlCommand cmd = {0, 90};

  while (true) {
    if (xQueueReceive(controlQueue, &cmd, pdMS_TO_TICKS(20))) {
      esc.control(cmd.speed);
      steeringServo.control(cmd.angle);
      lastCommandTime = millis();
    }

    if (millis() - lastCommandTime > COMMAND_TIMEOUT) {
      esc.control(0);
      steeringServo.control(90);
    }

    vTaskDelay(10);
  }
}

// ==== Setup ====
void setup() {
  Serial.begin(115200);
  Serial.println("Booting...");

  init_camera();
  init_wifi();

  steeringServo.initialize();
  esc.initialize();

  // Create queues
  controlQueue = xQueueCreate(1, sizeof(ControlCommand));
  frameQueue = xQueueCreate(1, sizeof(camera_fb_t *));

  // Start tasks
  xTaskCreatePinnedToCore(cameraTask, "CameraTask", 4096, NULL, 2, &cameraTaskHandle, 1);
  xTaskCreatePinnedToCore(networkTask, "NetworkTask", 6144, NULL, 3, &networkTaskHandle, 0);
  xTaskCreatePinnedToCore(controlTask, "ControlTask", 2048, NULL, 2, &controlTaskHandle, 0);

  Serial.println("All tasks started successfully!");
}

void loop() {
  vTaskDelay(1000); // loop does nothing; all work happens in tasks
}
