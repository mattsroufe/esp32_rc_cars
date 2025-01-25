#include "secrets.h"
#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoWebsockets.h>
#include "soc/rtc_cntl_reg.h"
#include "esp_camera.h"
#include <SD.h>
#include "ServoControl.h"
#include "Esc.h"

// configuration for AI Thinker Camera board
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

// Motor and servo pins
#define DUMMY_PIN -1 // Pin for servo control

using namespace websockets;
WebsocketsClient client;

// Create two dummy instances of the Servo class to increment the pwm channels since we're using the camera
ServoControl dummyServo1(DUMMY_PIN);
ServoControl dummyServo2(DUMMY_PIN);
ServoControl steeringServo;
Esc esc;

// Time tracking variables
unsigned long lastCommandTime = 0;
const int COMMAND_TIMEOUT = 20; // command timeout ms

void onMessageCallback(WebsocketsMessage message)
{
    lastCommandTime = millis();
    String command = message.data();
    // Serial.print("Got Message: ");
    // Serial.println(command);

    if (command.startsWith("MOTOR:"))
    {
        // Control motor speed (0-255)
    }
    else if (command.startsWith("SERVO:"))
    {
        // Control servo angle (0-180)
    }
    else if (command.startsWith("CONTROL:"))
    {
        // Control servo angle (0-180)
        String commands_str = command.substring(8);
        int colonIndex = commands_str.indexOf(":"); // Find the index of the colon
        int speed = commands_str.substring(0, colonIndex).toInt();
        speed = constrain(speed, -255, 255);
        int angle = commands_str.substring(colonIndex + 1).toInt();
        angle = constrain(angle, 0, 180);
        esc.control(speed);
        steeringServo.control(angle);
        // xQueueOverwrite(controlQueue, &angle);
    }
}

void onEventsCallback(WebsocketsEvent event, String data)
{
    if (event == WebsocketsEvent::ConnectionOpened)
    {
        Serial.println("Connnection Opened");
    }
    else if (event == WebsocketsEvent::ConnectionClosed)
    {
        Serial.println("Connnection Closed");
    }
    else if (event == WebsocketsEvent::GotPing)
    {
        Serial.println("Got a Ping!");
    }
    else if (event == WebsocketsEvent::GotPong)
    {
        Serial.println("Got a Pong!");
    }
}

esp_err_t init_camera()
{
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;
    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;
    config.pin_sscb_sda = SIOD_GPIO_NUM;
    config.pin_sscb_scl = SIOC_GPIO_NUM;
    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;

    // parameters for image quality and size
    config.frame_size = FRAMESIZE_QVGA; // FRAMESIZE_ + QVGA|CIF|VGA|SVGA|XGA|SXGA|UXGA
    config.jpeg_quality = 10;           // 10-63 lower number means higher quality
    config.fb_count = 2;

    // Camera init
    esp_err_t err = esp_camera_init(&config);

    if (err != ESP_OK)
    {
        Serial.printf("camera init FAIL: 0x%x", err);
        return err;
    }

    Serial.println("camera init OK");

    return ESP_OK;
};

esp_err_t init_wifi()
{
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.println("Wifi init ");
    while (WiFi.status() != WL_CONNECTED)
    {
        delay(500);
        Serial.print(".");
    }
    Serial.println("");
    Serial.println("WiFi OK");
    Serial.println("connecting to WS: ");
    client.onMessage(onMessageCallback);
    client.onEvent(onEventsCallback);
    while (!client.connect(WS_SERVER_URL))
    {
        delay(500);
        Serial.print(".");
    }
    Serial.println("WS OK");
    // client.send("hello from ESP32 camera stream!");
    return ESP_OK;
};

void setup()
{
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

    Serial.begin(115200);
    Serial.setDebugOutput(true);

    // Now, disable the SD card to free up pins
    SD.end();
    Serial.println("SD Card disabled. Pins freed!");

    // xTaskCreate(ServoTask, "Servo", 1000, NULL, 1, NULL);

    init_camera();
    init_wifi();
    steeringServo.initialize();
    esc.initialize();
}

void loop()
{
    if (millis() - COMMAND_TIMEOUT >= lastCommandTime)
    {
        esc.control(0); // Start motor at 0 speed
        steeringServo.control(90);
        // Serial.println("Throttle reset to 0 due to timeout.");
    }

    if (client.available())
    {
        camera_fb_t *fb = esp_camera_fb_get();

        if (!fb)
            return;

        client.sendBinary((const char *)fb->buf, fb->len);

        esp_camera_fb_return(fb);

        client.poll();
    }
}
