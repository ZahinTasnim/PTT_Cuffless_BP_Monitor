// Minimal PC stand-ins for the Arduino/ESP32 functions used by the firmware, so the REAL firmware source
// can be compiled and run on recorded data. Time and the analog input are driven by the test program.
#pragma once
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

extern uint64_t g_now_us;      // simulated clock, microseconds
extern int g_ecg_sample;       // value returned by analogRead(): the current 12-bit ECG sample
extern bool g_pulse_now;       // true on the tick when a pulse is "detected" (fires the beat callback)

inline unsigned long micros() { return (unsigned long)g_now_us; }
inline unsigned long millis() { return (unsigned long)(g_now_us / 1000); }
inline int analogRead(int) { return g_ecg_sample; }
inline void analogReadResolution(int) {}
inline void delay(unsigned long) {}

struct SerialClass {
    void begin(long) {}
    void print(const char *s) { fputs(s, stdout); }
    void print(char c) { putchar(c); }
    void print(unsigned char v) { printf("%u", v); }
    void print(int v) { printf("%d", v); }
    void print(unsigned int v) { printf("%u", v); }
    void print(long v) { printf("%ld", v); }
    void print(unsigned long v) { printf("%lu", v); }
    void print(float v, int d = 2) { printf("%.*f", d, v); }
    void print(double v, int d = 2) { printf("%.*f", d, v); }
    void println() { putchar('\n'); }
    template <class T> void println(T v) { print(v); putchar('\n'); }
    template <class T> void println(T v, int d) { print(v, d); putchar('\n'); }
};
extern SerialClass Serial;
