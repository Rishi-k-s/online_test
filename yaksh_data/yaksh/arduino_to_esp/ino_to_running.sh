#!/usr/bin/env bash

# Usage: ./ino_to_running.sh <input.ino>
set -e

if [ $# -ne 1 ]; then
	echo "Usage: $0 <input.ino>"
	exit 1
fi

INO_FILE="$1"
TARGET_FILE="$(dirname "$0")/main/main.cpp"

if [ ! -f "$INO_FILE" ]; then
	echo "Input file $INO_FILE does not exist."
	exit 2
fi

{
	echo "//file: main.cpp"
	echo "#include \"Arduino.h\""
	echo "#include \"esp_log.h\""
	echo "static const char *TAG = \"APP\";"
	echo
	cat "$INO_FILE"
} > "$TARGET_FILE"

# Import ESP-IDF environment
if [ -z "$IDF_PATH" ]; then
	if [ -f "$HOME/esp/esp-idf/export.sh" ]; then
		. "$HOME/esp/esp-idf/export.sh"
	elif [ -f "/opt/esp/idf/export.sh" ]; then
		. "/opt/esp/idf/export.sh"
	else
		echo "Could not find esp-idf export.sh. Please set up ESP-IDF environment."
		exit 3
	fi
fi

# Build the project
idf.py build > build.log 2>&1


# Now using esptools to merge the bootloader, partition table, and app binary to a flashable binary
BUILD_DIR="$(dirname "$0")/build"
APP_BIN="build/arduino_to_esp.bin"
BOOTLOADER_BIN="build/bootloader/bootloader.bin"
PARTITION_TABLE_BIN="build/partition_table/partition-table.bin"
FLASHABLE_BIN="build/flash_image.bin"

esptool.py --chip esp32 merge_bin -o "$FLASHABLE_BIN" \
	0x1000 "$BOOTLOADER_BIN" \
	0x8000 "$PARTITION_TABLE_BIN" \
	0x10000 "$APP_BIN" >> build.log 2>&1

# This is optional, but truncating the image into 4MB so it will run without any errors in QEMU
truncate -s 4M "$FLASHABLE_BIN"
echo "Created flashable binary at $FLASHABLE_BIN"


echo "Now emulating it via QEMU..."

# Finally running it in QEMU

set -e

PATTERN="task_wdt: Task watchdog got triggered"
TIME_LIMIT=5

timeout "${TIME_LIMIT}s" qemu-system-xtensa -nographic -machine esp32 \
  -drive file=build/flash_image.bin,if=mtd,format=raw \
  > output.txt 2>&1 &

QEMU_PID=$!
echo "QEMU PID (timeout wrapper): $QEMU_PID"

while read -r line; do
  if [[ "$line" == *"$PATTERN"* ]]; then
    echo "Watchdog triggered, stopping QEMU"
    kill "$QEMU_PID"
    break
  fi
done < <(tail --pid="$QEMU_PID" -Fn0 output.txt)
sed -n '/uart: queue free spaces/,${
/uart: queue free spaces/d
$d
p
}' output.txt > filtered_output.txt


wait "$QEMU_PID" 2>/dev/null