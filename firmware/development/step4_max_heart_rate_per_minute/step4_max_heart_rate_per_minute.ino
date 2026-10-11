#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include "MAX30100_PulseOximeter.h"

// Initialize the LCD (I2C address 0x27, 16 columns, 2 rows)
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Define constants for AD8232
#define ECG_PIN A0
unsigned long previousMillis = 0;
unsigned int ecgHeartRate = 0;
int ecgBeatDetected = 0;
int ecgThreshold = 512; // Adjust based on ECG signal
unsigned long ecgBeatInterval = 0;

// Define constants for MAX30100/MAX30102
#define REPORTING_PERIOD_MS 3000
PulseOximeter pox;
uint32_t tsLastReport = 0;

// Variables to track maximum heart rates
unsigned int maxECGHeartRate = 0;
unsigned int maxPulseHeartRate = 0;
unsigned long startMinuteMillis = 0;

// Callback for MAX30100/MAX30102 beat detection
void onBeatDetected() {
    Serial.println("Beat detected!");
}

void setup() {
    // Initialize Serial Monitor
    Serial.begin(115200);
    Serial.println("Initializing...");

    // Initialize LCD
    lcd.init();
    lcd.backlight();
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Initializing...");
    delay(2000);
    lcd.clear();

    // Initialize MAX30100/MAX30102 Pulse Oximeter
    if (!pox.begin()) {
        Serial.println("Pulse oximeter FAILED");
        lcd.setCursor(0, 0);
        lcd.print("Oximeter Error");
        while (true); // Stay here on failure
    } else {
        Serial.println("Pulse oximeter SUCCESS");
        lcd.setCursor(0, 0);
        lcd.print("Oximeter Ready");
        delay(2000);
        lcd.clear();
    }
    pox.setIRLedCurrent(MAX30100_LED_CURR_24MA);
    pox.setOnBeatDetectedCallback(onBeatDetected);

    // Initialize minute timer
    startMinuteMillis = millis();
}

void loop() {
    // === AD8232 ECG Sensor ===
    int ecgSignal = analogRead(ECG_PIN);

    // Check for heartbeat (value crossing threshold)
    if (ecgSignal > ecgThreshold && ecgBeatDetected == 0) {
        ecgBeatDetected = 1; // Beat detected
        unsigned long currentMillis = millis();
        ecgBeatInterval = currentMillis - previousMillis;
        previousMillis = currentMillis;

        // Calculate heart rate (BPM)
        if (ecgBeatInterval > 0) {
            ecgHeartRate = 60000 / ecgBeatInterval; // 60,000 ms = 1 minute
        }

        // Update maximum ECG heart rate
        if (ecgHeartRate > maxECGHeartRate) {
            maxECGHeartRate = ecgHeartRate;
        }

        // Debugging output for ECG
        Serial.print("ECG Signal: ");
        Serial.print(ecgSignal);
        Serial.print(" | ECG BPM: ");
        Serial.println(ecgHeartRate);
    }
    if (ecgSignal < ecgThreshold) {
        ecgBeatDetected = 0;
    }

    // === MAX30100/MAX30102 Pulse Oximeter ===
    pox.update();

    if (millis() - tsLastReport > REPORTING_PERIOD_MS) {
        float maxHeartRate = pox.getHeartRate();
        float spO2 = pox.getSpO2();

        // Update maximum Pulse heart rate
        if (maxHeartRate > maxPulseHeartRate) {
            maxPulseHeartRate = maxHeartRate;
        }

        // Debugging output for MAX30100/MAX30102
        Serial.print("Pulse BPM: ");
        Serial.print(maxHeartRate);
        Serial.print("  SpO2: ");
        Serial.print(spO2);
        Serial.println("%");

        // === Display on LCD ===
        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("Pulse BPM:");
        lcd.print(maxHeartRate);
        lcd.setCursor(0, 1);
        lcd.print("SpO2:");
        lcd.print(spO2);
        lcd.print("%");
        delay(2000);

        lcd.clear();
        lcd.setCursor(0, 0);
        lcd.print("ECG BPM:");
        lcd.print(ecgHeartRate);
        lcd.setCursor(0, 1);
        lcd.print("Max ECG:");
        lcd.print(maxECGHeartRate);
        delay(2000);

        // Update last report time
        tsLastReport = millis();
    }

    // === Check if one minute has passed ===
    if (millis() - startMinuteMillis >= 60000) {
        // Print maximum values for the minute
        Serial.println("==== One Minute Report ====");
        Serial.print("Max ECG BPM: ");
        Serial.println(maxECGHeartRate);
        Serial.print("Max Pulse BPM: ");
        Serial.println(maxPulseHeartRate);

        // Reset maximum values for the next minute
        maxECGHeartRate = 0;
        maxPulseHeartRate = 0;

        // Reset the timer
        startMinuteMillis = millis();
    }
}
