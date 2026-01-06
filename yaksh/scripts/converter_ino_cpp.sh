#!/bin/sh
# Convert Arduino .ino → C++ for Yaksh evaluator
# Adds generic wrappers for setup() / loop()

set -e

if [ $# -lt 2 ]; then
    echo "Usage: $0 <input.ino> <output.cpp>"
    exit 1
fi

INO_FILE="$1"
CPP_FILE="$2"

if [ ! -f "$INO_FILE" ]; then
    echo "Error: Input file not found: $INO_FILE"
    exit 1
fi

echo "// Converted Arduino code" > "$CPP_FILE"
echo "#include <stdio.h>" >> "$CPP_FILE"

# Arduino stubs
echo "#define INPUT 0" >> "$CPP_FILE"
echo "#define OUTPUT 1" >> "$CPP_FILE"
echo "#define INPUT_PULLUP 2" >> "$CPP_FILE"
echo "#define HIGH 1" >> "$CPP_FILE"
echo "#define LOW 0" >> "$CPP_FILE"
echo "void pinMode(int pin, int mode) {}" >> "$CPP_FILE"
echo "void digitalWrite(int pin, int val) {}" >> "$CPP_FILE"
echo "int analogRead(int pin) { return 0; }" >> "$CPP_FILE"
echo "void ledcWrite(int channel, int duty) {}" >> "$CPP_FILE"
echo "void delay(unsigned long ms) {}" >> "$CPP_FILE"

# Copy Arduino code (skip #include <Arduino.h>)
grep -v "#include <Arduino.h>" "$INO_FILE" >> "$CPP_FILE"

# Add evaluator wrappers
echo "" >> "$CPP_FILE"
echo "// ===== Auto-generated evaluator wrappers =====" >> "$CPP_FILE"
echo 'extern "C" void run_setup() { setup(); }' >> "$CPP_FILE"
echo 'extern "C" void run_loop()  { loop(); }' >> "$CPP_FILE"

echo "Conversion complete: $CPP_FILE"
