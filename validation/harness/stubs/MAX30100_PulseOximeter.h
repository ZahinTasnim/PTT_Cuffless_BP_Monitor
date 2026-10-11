#pragma once
#include <stdint.h>
extern bool g_pulse_now;
enum LEDCurrent { MAX30100_LED_CURR_7_6MA, MAX30100_LED_CURR_11MA };
// Stand-in for the pulse oximeter: update() fires the firmware's beat callback on the ticks the test program
// marks as "pulse detected" (events found in the recorded fingertip PPG).
class PulseOximeter {
public:
    bool begin() { return true; }
    void update() { if (g_pulse_now && cb_) { g_pulse_now = false; cb_(); } }
    float getHeartRate() { return 0.0f; }
    uint8_t getSpO2() { return 0; }
    void setIRLedCurrent(LEDCurrent) {}
    void setOnBeatDetectedCallback(void (*cb)()) { cb_ = cb; }
private:
    void (*cb_)() = nullptr;
};
