/*
  PTT Blood Pressure Monitor -- revised firmware (v2)
  ----------------------------------------------------
  Revision of firmware/final/FINAL_PROGRAM.ino, written after the project
  (September 2026) with AI assistance. Validated on 13 real recordings
  (see validation/README.md). Same wiring as the final build (ESP32, AD8232 on GPIO36,
  MAX30100 + 20x4 I2C LCD on GPIO21/22).

  What changed compared with FINAL_PROGRAM, and why:
   1. PTT is measured beat by beat: the time from each ECG R-peak to the next
      pulse-oximeter beat, in milliseconds. The displayed value is the MEDIAN of the
      last 8 beats, so a few bad pulses during movement do not distort it.
      The original compared the moments of each sensor's highest heart rate in a
      one-minute window, and showed the time since power-on whenever one sensor
      had not recorded a maximum since the last reset.
   2. R-peaks are found from the steep SLOPE of each heartbeat, compared with the
      measured noise level (the idea behind the Pan-Tompkins detector), instead of
      a fixed "+10 counts" threshold that suited the Arduino Uno's 10-bit ADC
      (0-1023) but is far too small for the ESP32's 12-bit ADC (0-4095). The
      threshold adapts to each person's signal strength, and no beats are
      reported until 2 s of signal have been seen (noise-learning period).
   3. The LCD is updated one row at a time without lcd.clear(), so pox.update()
      runs often enough for the MAX30100 library to detect pulses.
   4. The ECG is sampled on a fixed 4 ms clock (250 Hz) instead of loop + delay(10).
   5. Every PTT reading is printed over Serial as a CSV line, for logging and
      for fitting the calibration BP = a x PTT + b.

  Known limitations: the MAX30100 library reports a beat after its own internal
  filtering, so the measured PTT includes a roughly constant delay. A per-user
  linear calibration absorbs a constant offset, but absolute values should not be
  compared directly with published PTT. Each LCD row update blocks for roughly
  10-15 ms, during which ECG samples are missed.
*/
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include "MAX30100_PulseOximeter.h"
#include <math.h>

LiquidCrystal_I2C lcd(0x27, 20, 4);
#define ECG_PIN 36                          // GPIO36 (VP), ADC1

// ---------- ECG sampling and R-peak detection ----------
const unsigned long SAMPLE_US = 4000;       // 250 Hz sampling
const unsigned long REFRACTORY_MS = 300;    // no second beat within 300 ms (max 200 bpm)
const unsigned long WARMUP_MS = 2000;       // learn the noise level before detecting beats
const float SNR_MIN = 6.0;                  // slope peak must be 6x the noise level to count
const int WINDOW = 5;                       // 5-sample (20 ms) moving average
int window[WINDOW];
int wIdx = 0;
long wSum = 0;
float hist[3];                              // last three smoothed samples
float noiseLevel = 1.0, slopePeak = 1.0;    // running noise level and running slope peak
bool above = false;
unsigned long startMs = 0, lastSampleUs = 0, lastRPeakMs = 0, lastRPeakUs = 0;
unsigned int ecgBpm = 0;

// ---------- Pulse oximeter ----------
PulseOximeter pox;
bool poxBeat = false;
unsigned long poxBeatUs = 0;

// ---------- Pulse transit time ----------
const float PTT_MIN_MS = 80, PTT_MAX_MS = 700;   // plausible range; outside it the pair is skipped
const int PTT_AVG = 8;
float pttBuf[PTT_AVG];
int pttCount = 0, pttIdx = 0;
float pttMedianMs = 0;
bool rPeakPending = false;                  // an R-peak waiting for its matching pulse

// ---------- Display ----------
unsigned long lastLcdMs = 0;
int lcdRow = 0;

// Called from inside pox.update() whenever the MAX30100 library detects a pulse.
void onBeatDetected() {
    poxBeat = true;
    poxBeatUs = micros();
}

void sampleEcg() {
    int raw = analogRead(ECG_PIN);
    wSum += raw - window[wIdx];
    window[wIdx] = raw;
    wIdx = (wIdx + 1) % WINDOW;
    hist[0] = hist[1]; hist[1] = hist[2]; hist[2] = wSum / (float)WINDOW;

    float slope = fabsf(hist[2] - hist[0]);        // change over 8 ms: large only on QRS
    if (slope > slopePeak) slopePeak = slope;      // jump up with each heartbeat...
    else slopePeak += 0.002f * (noiseLevel - slopePeak);   // ...then relax toward noise
    float threshold = noiseLevel + 0.5f * (slopePeak - noiseLevel);

    unsigned long nowMs = millis();
    if (!above && nowMs - startMs >= WARMUP_MS && slope > threshold &&
        slopePeak > SNR_MIN * noiseLevel && nowMs - lastRPeakMs > REFRACTORY_MS) {
        above = true;
        if (lastRPeakMs > 0) ecgBpm = 60000UL / (nowMs - lastRPeakMs);
        lastRPeakMs = nowMs;
        lastRPeakUs = micros();
        rPeakPending = true;
    } else if (above && slope < threshold) {
        above = false;
    }
    if (!above) noiseLevel += 0.01f * (slope - noiseLevel);   // learn noise only between beats
}

void handlePoxBeat() {
    if (!poxBeat) return;
    poxBeat = false;
    if (!rPeakPending) return;                      // pulse with no R-peak before it
    rPeakPending = false;
    float ptt = (long)(poxBeatUs - lastRPeakUs) / 1000.0f;
    if (ptt < PTT_MIN_MS || ptt > PTT_MAX_MS) return;

    pttBuf[pttIdx] = ptt;
    pttIdx = (pttIdx + 1) % PTT_AVG;
    if (pttCount < PTT_AVG) pttCount++;
    float sorted[PTT_AVG];                          // median of the last (up to) 8 readings
    for (int i = 0; i < pttCount; i++) sorted[i] = pttBuf[i];
    for (int i = 1; i < pttCount; i++) {            // insertion sort of at most 8 values
        float v = sorted[i]; int j = i - 1;
        while (j >= 0 && sorted[j] > v) { sorted[j + 1] = sorted[j]; j--; }
        sorted[j + 1] = v;
    }
    pttMedianMs = (pttCount % 2) ? sorted[pttCount / 2]
                                 : 0.5f * (sorted[pttCount / 2 - 1] + sorted[pttCount / 2]);

    Serial.print(millis());                  Serial.print(",");
    Serial.print(ecgBpm);                    Serial.print(",");
    Serial.print(pox.getHeartRate(), 1);     Serial.print(",");
    Serial.print(pox.getSpO2());             Serial.print(",");
    Serial.print(ptt, 1);                    Serial.print(",");
    Serial.println(pttMedianMs, 1);
}

// Write one full 20-character row (padded with spaces, so no lcd.clear() is needed).
void printRow(int row, const char *text) {
    char line[21];
    int n = snprintf(line, sizeof line, "%s", text);
    for (int i = (n < 20 ? n : 20); i < 20; i++) line[i] = ' ';
    line[20] = '\0';
    lcd.setCursor(0, row);
    lcd.print(line);
}

void updateLcdRow() {
    char text[32];
    switch (lcdRow) {
        case 0:
            snprintf(text, sizeof text, "ECG BPM: %u", ecgBpm);
            break;
        case 1: {
            int hr = (int)pox.getHeartRate();
            if (hr > 0) snprintf(text, sizeof text, "PO:%3d bpm SpO2:%3u%%", hr, pox.getSpO2());
            else snprintf(text, sizeof text, "PulseOx: no pulse");
            break;
        }
        case 2:
            if (pttCount > 0) snprintf(text, sizeof text, "PTT: %.1f ms", pttMedianMs);
            else snprintf(text, sizeof text, "PTT: waiting...");
            break;
        default:
            snprintf(text, sizeof text, "Beats in median: %d", pttCount);
            break;
    }
    printRow(lcdRow, text);
    lcdRow = (lcdRow + 1) % 4;
}

void setup() {
    Serial.begin(115200);
    Wire.begin(21, 22);
    analogReadResolution(12);

    lcd.init();
    lcd.backlight();
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Initializing...");

    if (!pox.begin()) {
        Serial.println("FAILED to initialize Pulse Oximeter");
        lcd.setCursor(0, 1);
        lcd.print("PulseOx Init Fail");
        for (;;);
    }
    pox.setIRLedCurrent(MAX30100_LED_CURR_11MA);
    pox.setOnBeatDetectedCallback(onBeatDetected);

    int first = analogRead(ECG_PIN);                // start the filter at the real signal level
    for (int i = 0; i < WINDOW; i++) window[i] = first;
    wSum = (long)first * WINDOW;
    hist[0] = hist[1] = hist[2] = first;
    startMs = millis();

    lcd.clear();
    Serial.println("time_ms,ecg_bpm,po_bpm,spo2,ptt_ms,ptt_median_ms");
    lastSampleUs = micros();
}

void loop() {
    pox.update();                                   // must run as often as possible

    unsigned long nowUs = micros();
    if (nowUs - lastSampleUs >= SAMPLE_US) {
        lastSampleUs = (nowUs - lastSampleUs > 4 * SAMPLE_US) ? nowUs : lastSampleUs + SAMPLE_US;
        sampleEcg();
    }

    handlePoxBeat();

    if (millis() - lastLcdMs >= 250) {             // one row every 250 ms = full screen each second
        lastLcdMs = millis();
        updateLcdRow();
    }
}
