# Anticipy one-owner pairing and recovery

This runbook applies to the live optional-D7 button + D0 haptic candidate built with
`candidate_live_button_haptic.conf` and `overlay/xiao_ble_sense_no_sd.overlay`.
That image contains no microSD or QSPI audio backlog.

## Provision a new unit

1. Fully erase/provision the new board in a private test area, then power it.
2. A unit with no stored owner automatically advertises for 120 seconds. Pair
   it from the intended investor iPhone during that window. Do not expose an
   unowned powered unit in a public RF environment.
3. The first persistent bond becomes the sole owner. The controller filter
   accept list rejects connection requests from every other BLE identity on
   this and later boots.
4. Power-cycle once and verify that the same iPhone reconnects without opening
   another provisioning window.

If D7 is fitted, a three-second boot hold also opens the same 120-second window
when the unit has no stored owner. It is not required for first commissioning.

The three-second boot hold is provisioning only. A normal three-second press
after boot still runs the existing power-off action and never erases a bond.

## Deliberate owner reset

1. Power the unit off.
2. Hold D7 while applying power. Keep holding through the boot LEDs, through
   the blue provisioning indication, and for ten seconds after the button is
   initialized.
3. Release after the red confirmation blink.
4. The old bond is erased and a fresh 120-second provisioning window opens.

In a future storage-enabled owner build, this same reset also advances/clears
the persistent backlog before a new owner is accepted. If that durable clear
fails, firmware stays locked rather than exposing the prior owner's audio.

## SWD recovery

If D7 is damaged, the owner phone is lost, or settings are corrupt, use the
known-good SWD probe to perform a full device erase and then restore the
approved bootloader and application image. Copying only a UF2 application may
leave the settings partition—and therefore the old owner bond—intact. Treat
SWD recovery as a controlled service operation and repeat every provisioning
and battery physical-qualification test afterward.

## Two-phone release test

- Phone A provisions, subscribes to audio/button events, and commands haptic.
- Phone B cannot connect after Phone A's bond commits.
- After a reboot, Phone A reconnects and Phone B still cannot connect.
- The application DFU trigger accepts Phone A and rejects an unapproved
  encrypted peer. The inherited bootloader is separately unqualified; do not
  call this secure owner-only OTA.
- A ten-second boot hold removes Phone A, then Phone B can become the new owner.
- No zero-length encoded frame reaches BLE or any future persistent backlog.
- Power-off stops PDM, drains the accepted live queue, then disables Bluetooth.

## Security boundary

Pairing is LE Secure Connections Just Works: it encrypts the link but does not
cryptographically authenticate the person or phone during the 120-second
physical window. Provision in a private RF environment because a nearby device
could race the intended iPhone during that window. A customer release should
add an app-level random setup secret or authenticated numeric/OOB pairing.
