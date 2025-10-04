import usb_cdc, usb_hid, usb_midi

usb_cdc.disable()
usb_cdc.enable(console=True, data=False)

usb_hid.disable()
usb_midi.enable()
