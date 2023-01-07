#!/usr/bin/env bash
set -e
PLATFORM="$1"
OS="$2"
DISK_DEVICE="$3"
CHANNEL="${4:-stable}"

function prepare_media {
  local BUTANE_CONFIG="$1"
  docker run --pull=always -i --rm quay.io/coreos/butane:release --pretty --strict < "cloud-init/$BUTANE_CONFIG" > cloud-init/ignition.ign
}

function update_flatcar-installer {
wget -O flatcar-install https://raw.githubusercontent.com/flatcar-linux/init/flatcar-master/bin/flatcar-install
chmod +x flatcar-install
}

function setup_efi {
  local efi="$1"
  sudo rm -Rf /tmp/efipartition
  mkdir /tmp/efipartition
  sudo mount ${efi} /tmp/efipartition
  pushd /tmp/efipartition
  version=$(curl --silent "https://api.github.com/repos/pftf/RPi4/releases/latest" | jq -r .tag_name)
  sudo curl -LO https://github.com/pftf/RPi4/releases/download/${version}/RPi4_UEFI_Firmware_${version}.zip
  sudo unzip RPi4_UEFI_Firmware_${version}.zip
  sudo rm RPi4_UEFI_Firmware_${version}.zip
  popd
  sudo umount /tmp/efipartition
  sudo rm -Rf /tmp/efipartition
}

case "$PLATFORM" in
  libvirt)
    qemu-img create disk.img 10G
    sudo losetup -P "$DISK_DEVICE" ./disk.img
    if [[ "$OS" == "flatcar" ]]
    then
      prepare_media "config.yaml"
      update_flatcar-installer
      sudo ./flatcar-install -d "$DISK_DEVICE" -i cloud-init/ignition.ign -C "$CHANNEL"
    elif [[ "$OS" == "coreos" ]]
    then
      prepare_media "config.yaml"
      docker run --pull=always --privileged --rm \
        -v /dev:/dev -v /run/udev:/run/udev -v $(pwd):/data -w /data \
        quay.io/coreos/coreos-installer:release \
        install -i cloud-init/ignition.ign "$DISK_DEVICE"
    fi
    sudo losetup -d "$DISK_DEVICE"
    ;;

  rpi4)
    if [[ "$OS" == "flatcar" ]]
    then
      prepare_media "config_rpi4_flatcar.yaml"
      update_flatcar-installer
      sudo ./flatcar-install -d "$DISK_DEVICE" -i cloud-init/ignition.ign -B arm64-usr -C "$CHANNEL"
      EFI=$(lsblk "$DEVICE" -oLABEL,PATH | awk '$1 == "EFI-SYSTEM" {print $2}')
    elif  [[ "$OS" == "coreos" ]]
    then
      prepare_media "config_rpi4_coreos.yaml"
      docker run --pull=always --privileged --rm \
        -v /dev:/dev -v /run/udev:/run/udev -v $(pwd):/data -w /data \
        quay.io/coreos/coreos-installer:release \
        install -i cloud-init/ignition.ign -a aarch64 "$DISK_DEVICE"
      EFI=$(lsblk $FCOSDISK -J -oLABEL,PATH  | jq -r '.blockdevices[] | select(.label == "EFI-SYSTEM")'.path)
    fi
    setup_efi "$EFI"
    ;;

  *)
    echo "Usage:"
    echo "$0 [libvirt|rpi4] [coreos|flatcar] [device] [CHANNEL:stable|lts]"
    exit 1
    ;;
esac

rm -f flatcar-install
