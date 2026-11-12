#!/bin/sh
# One container = one ESP32. The flash image lives in the /flash volume, so NVS
# settings, OTA partitions and core dumps survive container restarts exactly
# like a real module keeps its flash across power cycles.
set -eu

if [ "${1:-}" = "ota-server" ]; then
    exec python3 -m http.server "${OTA_PORT:-8070}" --directory /opt/xiaoyi/firmware
fi
MODE=run
if [ "${1:-}" = "provision" ]; then
    MODE=provision   # factory re-flash only, do not boot
elif [ "$#" -gt 0 ]; then
    exec "$@"
fi

: "${DEVICE_ID:?DEVICE_ID is required}"
case "$DEVICE_ID" in
    *[!A-Za-z0-9_.-]*) echo "DEVICE_ID must match [A-Za-z0-9_.-]" >&2; exit 2 ;;
esac

FLASH_DIR="/flash/$DEVICE_ID"
if [ "$MODE" = "provision" ]; then
    exec python3 /opt/xiaoyi/bin/provision.py "$FLASH_DIR"
fi
if [ "${RESET_FLASH:-0}" = "1" ] || [ ! -f "$FLASH_DIR/flash.bin" ]; then
    python3 /opt/xiaoyi/bin/provision.py "$FLASH_DIR"
else
    echo "flash image for $DEVICE_ID kept (set RESET_FLASH=1 to re-provision)"
fi

if [ -n "${NETWORK_FAULT:-}" ] && [ -n "${PROXY_NAME:-}" ]; then
    python3 /opt/xiaoyi/bin/netfault.py apply "$PROXY_NAME" "$NETWORK_FAULT" &
fi

# Espressif QEMU does not come back cleanly from a software CPU reset (the next
# boot faults in esp_timer_init), so -no-reboot makes QEMU exit on any guest
# reset and the loop powers the module up again with fresh peripherals. The
# firmware recovers the reset cause from flash (CONFIG_XIAOYI_EMULATED_POWER_CYCLE).
qemu_pid=
stop() {
    [ -n "$qemu_pid" ] && kill -TERM "$qemu_pid" 2>/dev/null && wait "$qemu_pid" 2>/dev/null
    exit 143
}
trap stop TERM INT
while :; do
    qemu-system-xtensa -nographic -no-reboot -machine esp32 \
        -drive "file=$FLASH_DIR/flash.bin,if=mtd,format=raw" \
        -nic user,model=open_eth &
    qemu_pid=$!
    status=0
    wait "$qemu_pid" || status=$?
    qemu_pid=
    if [ "$status" -ne 0 ]; then
        echo "qemu exited with status $status" >&2
        exit "$status"
    fi
    echo "[xiaoyi] $DEVICE_ID reset, powering the module up again"
done
