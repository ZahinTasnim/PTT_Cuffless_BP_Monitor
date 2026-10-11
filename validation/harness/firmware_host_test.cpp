// firmware_host_test.cpp -- runs the REAL version 2 firmware source on a recorded signal.
//   usage: fw_test <file.ecg> <file.pulse>
//   <file.ecg>   one 12-bit ECG sample per line, recorded at 500 Hz
//   <file.pulse> sample indices at which a pulse was detected in the fingertip PPG
// The firmware's loop() is called once per 2 ms tick. The firmware itself decides when to sample the ECG
// (every 4 ms, i.e. 250 Hz), exactly as on the ESP32. Output lines:
//   R,<tick>            an R-peak detected by the firmware (tick = 500 Hz sample index)
//   <csv line>          the firmware's own Serial output: time_ms,ecg_bpm,po_bpm,spo2,ptt_ms,ptt_median_ms
#include "Arduino.h"
#include "Wire.h"
#include <vector>
#include <fstream>

uint64_t g_now_us = 0;
int g_ecg_sample = 0;
bool g_pulse_now = false;
SerialClass Serial;
TwoWire Wire;

#include "PTT_MONITOR_V2.ino"          // the unmodified firmware source

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "usage: %s file.ecg file.pulse\n", argv[0]); return 1; }
    std::vector<int> ecg; std::vector<long> pulses;
    { std::ifstream f(argv[1]); int v; while (f >> v) ecg.push_back(v); }
    { std::ifstream f(argv[2]); long v; while (f >> v) pulses.push_back(v); }
    if (ecg.empty()) return 1;

    const uint64_t T0 = 5000000;             // start the simulated clock at 5 s
    g_now_us = T0; g_ecg_sample = ecg[0];
    setup();
    size_t nextPulse = 0; unsigned long prevR = lastRPeakUs;
    for (size_t i = 0; i < ecg.size(); ++i) {
        g_now_us = T0 + (uint64_t)i * 2000;  // 500 Hz tick
        g_ecg_sample = ecg[i];
        g_pulse_now = (nextPulse < pulses.size() && pulses[nextPulse] == (long)i);
        if (g_pulse_now) ++nextPulse;
        loop();
        if (lastRPeakUs != prevR) { printf("R,%lu\n", (unsigned long)((lastRPeakUs - T0) / 2000)); prevR = lastRPeakUs; }
    }
    return 0;
}
