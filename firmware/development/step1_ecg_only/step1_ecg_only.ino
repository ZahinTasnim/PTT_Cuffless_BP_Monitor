#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// Initialize the LCD (I2C address 0x27, 16 columns, 2 rows)
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Pin for ECG signal
#define ECG_PIN A0

// Variables for heart rate calculation
unsigned long previousMillis = 0;
unsigned int heartRate = 0;
int beatDetected = 0;
int threshold = 512;  // Adjust this threshold based on the signal
unsigned long beatInterval = 0;

void setup() {
    // Initialize Serial Monitor
    Serial.begin(9600);

    // Initialize the LCD
    lcd.init();
    lcd.backlight();
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("ECG Heart Rate");
    delay(2000);
    lcd.clear();
}

void loop() {
    // Read ECG signal
    int ecgSignal = analogRead(ECG_PIN);

    // Check for a heartbeat (value crossing threshold)
    if (ecgSignal > threshold && beatDetected == 0) {
        beatDetected = 1;  // Beat detected
        unsigned long currentMillis = millis();
        beatInterval = currentMillis - previousMillis;
        previousMillis = currentMillis;

        // Calculate heart rate (BPM)
        if (beatInterval > 0) {
            heartRate = 60000 / beatInterval;  // 60,000 ms = 1 minute
        }

        // Debugging output to Serial Monitor
        Serial.print("ECG Signal: ");
        Serial.print(ecgSignal);
        Serial.print(" | BPM: ");
        Serial.println(heartRate);
    }

    // Reset detection when signal falls below threshold
    if (ecgSignal < threshold) {
        beatDetected = 0;
    }

    // Display heart rate on LCD
    lcd.setCursor(0, 0);
    lcd.print("Heart Rate:");
    lcd.setCursor(0, 1);
    lcd.print("BPM: ");
    lcd.print(heartRate);

    // Small delay to avoid overloading the loop
    delay(10);
}
