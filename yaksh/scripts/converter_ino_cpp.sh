#!/bin/sh
# Convert Arduino .ino → C++ for Yaksh evaluator
# Adds generic wrappers for setup() / loop()

set -e
INO_FILE="$1"
CPP_FILE="$2"

if [ ! -f "$INO_FILE" ]; then
    echo "Input file not found: $INO_FILE"
    exit 1
fi

cat > "$CPP_FILE" << 'HEADER'
// ===== Auto-generated from Arduino .ino =====
#include <stdio.h>

#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
#define HIGH 1
#define LOW 0

// Arduino API functions are provided by the test harness
HEADER

# Copy Arduino code safely (line by line)
while IFS= read -r line; do
    if [ "$line" = "#include <Arduino.h>" ]; then
        echo "// Arduino.h removed" >> "$CPP_FILE"
    else
        echo "$line" >> "$CPP_FILE"
    fi
done < "$INO_FILE"

cat >> "$CPP_FILE" << 'FOOTER'
// Yaksh evaluator wrappers 
#ifdef __cplusplus
extern "C" {
#endif

void run_setup() { setup(); }
void run_loop()  { loop(); }

#ifdef __cplusplus
}
#endif
FOOTER
echo "Conversion complete: $CPP_FILE"
: $CPP_FILE"
