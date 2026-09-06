#!/usr/bin/env bash
set -eu

RULE_FILE="/etc/udev/rules.d/99-respeaker-xvf3800.rules"
RULE='SUBSYSTEM=="usb", ATTR{idVendor}=="2886", ATTR{idProduct}=="001a", MODE="0666"'

printf '%s\n' 'Installing udev permission rule for ReSpeaker XVF3800 (2886:001a)...'
printf '%s\n' "$RULE" | sudo tee "$RULE_FILE" >/dev/null
sudo udevadm control --reload-rules
sudo udevadm trigger

printf '%s\n' 'Rule installed.'
printf '%s\n' 'Now unplug/replug the ReSpeaker USB cable, or reboot the Raspberry Pi.'
printf '%s\n' 'Then restart ZeeAIBotWebCam and retry active-speaker calibration.'
