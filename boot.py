import board
import digitalio
import storage
import usb_cdc, usb_hid, usb_midi

usb_cdc.disable()
usb_hid.disable()
usb_midi.enable()

# keep soft pedal pressed during boot to enable USB drive & debug console
soft = digitalio.DigitalInOut(board.GP0)
soft.switch_to_input(pull=digitalio.Pull.UP)
if soft.value:
    usb_cdc.enable(console=True, data=False)
else:
    storage.disable_usb_drive()
