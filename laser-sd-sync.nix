{ config, pkgs, ... }:

# Like sd-sync.nix, but for the laser cutter's SD card.  The laser can only
# handle one file, so this copies just the newest *.gcode as go.gcode.
#
# The card's filesystem label must be "lasercut" (e.g. `fatlabel /dev/sdX1
# lasercut`); change the label in the udev rule below if you prefer another.

let
  gcodeDir = "/home/chouser/proj/laser-cut";
  mountPoint = "/mnt/lasercut";
  sounds = "${pkgs.sound-theme-freedesktop}/share/sounds/freedesktop/stereo";
in
{
  environment.systemPackages = with pkgs; [
    libnotify
    sound-theme-freedesktop
    pulseaudio
  ];

  systemd.tmpfiles.rules = [ "d ${mountPoint} 0755 root root -" ];

  services.udev.extraRules = ''
    ACTION=="add", SUBSYSTEM=="block", ENV{ID_FS_LABEL}=="lasercut", \
      TAG+="systemd", ENV{SYSTEMD_WANTS}="lasercut-sync@%k.service"
  '';

  systemd.services."lasercut-sync@" = {
    description = "Copy latest gcode to laser cutter SD card";
    path = with pkgs; [ coreutils util-linux libnotify pulseaudio ];

    # See these logs with: journalctl -u "lasercut-sync@*"
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = false;
      Environment = [ "DEV_SUFFIX=%i" ];
    };

    script = ''
      set -x

      notify() {
        /run/wrappers/bin/sudo -u chouser \
          DISPLAY=:0 \
          DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus" \
          notify-send "Laser SD Sync" "$1" || echo "notify-send failed: $?"
      }

      play() {
        /run/wrappers/bin/sudo -u chouser \
          PULSE_SERVER=/run/user/1000/pulse/native \
          paplay ${sounds}/$1
      }

      handle_error() {
        notify "Failed: $1"
        play dialog-warning.oga
        exit 1
      }

      start_ms=$(date +%s%3N)
      notify "Laser SD card detected"
      play message.oga

      # Wait for device to be ready (up to 1 second)
      DEVICE="/dev/$DEV_SUFFIX"
      ATTEMPTS=10
      while [ ! -b "$DEVICE" ] && [ $ATTEMPTS -gt 0 ]; do
        sleep 0.1
        ATTEMPTS=$((ATTEMPTS - 1))
      done
      [ -b "$DEVICE" ] || handle_error "Timed out awaiting $DEVICE"

      # Newest gcode file by modification time
      latest=$(ls -t ${gcodeDir}/*.gcode 2>/dev/null | head -n 1)
      [ -n "$latest" ] || handle_error "No .gcode files in ${gcodeDir}"

      mount -o uid=1000,gid=1000 "$DEVICE" "${mountPoint}" || handle_error "Mount failed"

      # The laser reads only go.gcode, and wants LF line endings.
      tr -d '\r' < "$latest" > "${mountPoint}/go.gcode" || {
        umount "${mountPoint}"; handle_error "Copy failed"; }
      sync

      umount "${mountPoint}" || handle_error "Unmount failed"

      elapsed_ms=$(( $(date +%s%3N) - start_ms ))
      notify "Copied $(basename "$latest") to go.gcode in $elapsed_ms ms"
      play bell.oga
    '';
  };
}
