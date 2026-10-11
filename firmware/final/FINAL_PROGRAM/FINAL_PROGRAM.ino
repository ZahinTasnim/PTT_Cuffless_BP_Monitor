#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include "MAX30100_PulseOximeter.h"

// Initialize the LCD (I2C address 0x27, 20 columns, 4 rows)
LiquidCrystal_I2C lcd(0x27, 20, 4);

// Pin for ECG signal
#define ECG_PIN 36 // GPIO36 (VP) for ESP32 ADC input

// Variables for ECG heart rate calculation
unsigned long previousMillis = 0;
unsigned int ecgHeartRate = 0;
int beatDetected = 0;
unsigned long beatInterval = 0;

// Threshold adjustment variables
int threshold = 212;
int signalAverage = 512;
const int windowSize = 10;
int signalWindow[windowSize];
int windowIndex = 0;

// Debounce time for beat detection
const unsigned long debounceTime = 300;

// Pulse oximeter configuration
#define REPORTING_PERIOD_MS 1000
PulseOximeter pox;
uint32_t tsLastReport = 0;
unsigned int poxHeartRate = 0;
unsigned int poxSpO2 = 0;

// Variables for Maximum Heart Rate tracking
unsigned int maxECGHeartRate = 0;
unsigned int maxPOXHeartRate = 0;
unsigned long maxECGTime = 0;
unsigned long maxPOXTime = 0;
unsigned long maxTimeDistance = 0;

// Time tracking for one-minute interval
unsigned long lastResetTime = 0;
const unsigned long minuteInterval = 60000;

// Callback function for beat detection in pulse oximeter
void onBeatDetected() {
    Serial.println("Pulse oximeter beat detected!");
}

void setup() {
    Wire.begin(21, 22);
    Serial.begin(115200);

    lcd.init();
    lcd.backlight();
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Initializing...");
    delay(2000);
    lcd.clear();

    for (int i = 0; i < windowSize; i++) {
        signalWindow[i] = 512;
    }

    Serial.println("Initializing Pulse Oximeter...");
    if (!pox.begin()) {
        Serial.println("FAILED to initialize Pulse Oximeter");
        lcd.setCursor(0, 0);
        lcd.print("PulseOx Init Fail");
        for (;;);
    } else {
        Serial.println("Pulse Oximeter initialized successfully");
    }
    pox.setIRLedCurrent(MAX30100_LED_CURR_11MA);
    pox.setOnBeatDetectedCallback(onBeatDetected);

    lastResetTime = millis();
}

void loop() {
    int rawSignal = analogRead(ECG_PIN);

    signalWindow[windowIndex] = rawSignal;
    windowIndex = (windowIndex + 1) % windowSize;

    int filteredSignal = 0;
    for (int i = 0; i < windowSize; i++) {
        filteredSignal += signalWindow[i];
    }
    filteredSignal /= windowSize;

    signalAverage = (signalAverage * 9 + filteredSignal) / 10;
    threshold = signalAverage + 10;

    if (filteredSignal > threshold && beatDetected == 0) {
        unsigned long currentMillis = millis();

        if (currentMillis - previousMillis > debounceTime) {
            beatDetected = 1;
            beatInterval = currentMillis - previousMillis;
            previousMillis = currentMillis;

            if (beatInterval > 0) {
                ecgHeartRate = 60000 / beatInterval;
            }

            if (ecgHeartRate > maxECGHeartRate) {
                maxECGHeartRate = ecgHeartRate;
                maxECGTime = millis();
            }
            Serial.print("ECG BPM: ");
            Serial.println(ecgHeartRate);
        }
    }
    if (filteredSignal < threshold) {
        beatDetected = 0;
    }

    pox.update();
    if (millis() - tsLastReport > REPORTING_PERIOD_MS) {
        lcd.clear();
        poxHeartRate = pox.getHeartRate();
        poxSpO2 = pox.getSpO2();

        if (poxHeartRate > 0 && poxHeartRate < 200 && poxSpO2 > 0) {
            Serial.print("PulseOx BPM: ");
            Serial.print(poxHeartRate);
            Serial.print(" / SpO2: ");
            Serial.print(poxSpO2);
            Serial.println("%");

            if (poxHeartRate > maxPOXHeartRate) {
                maxPOXHeartRate = poxHeartRate;
                maxPOXTime = millis();
            }
            maxTimeDistance = abs((long)maxPOXTime - (long)maxECGTime);
        }

        lcd.setCursor(0, 0);
        lcd.print("ECG BPM: ");
        lcd.print(ecgHeartRate);

        lcd.setCursor(0, 1);
        if (poxHeartRate > 0)
            lcd.print("PO BPM: ");
        else
            lcd.print("PulseOx: No Data");
        lcd.print(poxHeartRate);

        lcd.setCursor(0, 2);
        lcd.print("M-ECG: ");
        lcd.print(maxECGHeartRate);
        lcd.setCursor(11, 2);
        lcd.print("M-PO: ");
        lcd.print(maxPOXHeartRate);

        lcd.setCursor(0, 3);
        lcd.print("PTT: ");
        lcd.print(maxTimeDistance / 1000);
        lcd.print("s");
        tsLastReport = millis();
    }

    if (millis() - lastResetTime >= minuteInterval) {
        maxECGHeartRate = 0;
        maxPOXHeartRate = 0;
        maxECGTime = 0;
        maxPOXTime = 0;
        maxTimeDistance = 0;
        lastResetTime = millis();
    }
    delay(10);
}
