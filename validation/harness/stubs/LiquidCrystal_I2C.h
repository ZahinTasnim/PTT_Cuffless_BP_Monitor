#pragma once
#include <stdint.h>
struct LiquidCrystal_I2C {
    LiquidCrystal_I2C(uint8_t, uint8_t, uint8_t) {}
    void init() {} void backlight() {} void clear() {} void setCursor(int, int) {}
    template <class T> void print(T) {}
    template <class T> void print(T, int) {}
};
