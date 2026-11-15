#!/bin/sh
# Start or stop a local Home Assistant OS in QEMU (Apple silicon), for
# testing the add-on under a real Supervisor: http://localhost:18124
#   dev/haos.sh start | stop
# Needs: brew install qemu, and dev/haos/haos.qcow2 (generic-aarch64 image
# from https://github.com/home-assistant/operating-system/releases).
set -eu
cd "$(dirname "$0")/haos"
FIRMWARE=/opt/homebrew/share/qemu
case "${1:-}" in
start)
    [ -f vars.fd ] || cp "$FIRMWARE/edk2-arm-vars.fd" vars.fd
    qemu-system-aarch64 \
        -M virt -accel hvf -cpu host -smp 4 -m 4096 \
        -drive if=pflash,format=raw,readonly=on,file="$FIRMWARE/edk2-aarch64-code.fd" \
        -drive if=pflash,format=raw,file=vars.fd \
        -drive if=virtio,format=qcow2,file=haos.qcow2 \
        -netdev user,id=net0,hostfwd=tcp:127.0.0.1:18124-:80,hostfwd=tcp:127.0.0.1:18222-:22 \
        -device virtio-net-pci,netdev=net0 -device virtio-rng-pci \
        -display none -chardev socket,id=console,path=console.sock,server=on,wait=off,logfile=serial.log -serial chardev:console -daemonize -pidfile qemu.pid
    echo "started; Home Assistant appears at http://localhost:18124 after a few minutes"
    ;;
stop)
    [ -f qemu.pid ] && kill "$(cat qemu.pid)" && rm -f qemu.pid
    ;;
*)
    echo "usage: $0 start|stop" >&2; exit 1 ;;
esac
