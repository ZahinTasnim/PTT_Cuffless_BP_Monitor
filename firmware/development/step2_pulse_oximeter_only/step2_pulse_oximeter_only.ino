#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include "MAX30100_PulseOximeter.h"

// Initialize the LCD (I2C address 0x27, 16 columns, 2 rows)
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Define constants
#define REPORTING_PERIOD_MS 3000

// Pulse oximeter object
PulseOximeter pox;
uint32_t tsLastReport = 0;

// Callback function for beat detection
void onBeatDetected() {
    Serial.println("Beat detected!");
}

void setup() {
    // Initialize Serial Monitor
    Serial.begin(115200);
    Serial.println("Initializing...");

    // Initialize the LCD
    lcd.init();
    lcd.backlight();
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Initializing...");
    delay(2000);
    lcd.clear();

    // Initialize the Pulse Oximeter
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

    // Set IR LED current for the MAX30100 sensor
    pox.setIRLedCurrent(MAX30100_LED_CURR_24MA);

    // Register callback for beat detection
    pox.setOnBeatDetectedCallback(onBeatDetected);
}

void loop() {
    // Update the Pulse Oximeter readings
    pox.update();

    // Every REPORTING_PERIOD_MS, update the LCD and Serial Monitor
    if (millis() - tsLastReport > REPORTING_PERIOD_MS) {
        float heartRate = pox.getHeartRate();
        float spO2 = pox.getSpO2();

        // Display data on Serial Monitor
        Serial.print("BPM: ");
        Serial.print(heartRate);
        Serial.print("  SpO2: ");
        Serial.print(spO2);
        Serial.println("%");

        // Display data on LCD
        lcd.setCursor(0, 0);
        lcd.print("BPM: ");
        lcd.print(heartRate);
        lcd.setCursor(0, 1);
        lcd.print("SpO2: ");
        lcd.print(spO2);
        lcd.print("%");

        // Update the last report time
        tsLastReport = millis();
    }
}
