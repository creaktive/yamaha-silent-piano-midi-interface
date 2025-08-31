# Yamaha Silent Piano MIDI Interface

## Description

Replacement for the Switch Box Unit of a compatible Yamaha Silent Piano.

## BOM

 - Raspberry Pi Pico
 - 6-pin mini-DIN socket (PED connector)
 - 8-pin mini-DIN socket (KEY connector)
 - H11L1 optoisolator
 - 1N914 diode
 - 1x 10Ω resistor
 - 1x 33Ω resistor
 - 2x 220Ω resistor
 - 1x 470Ω resistor
 - 100nF capacitor

## Schematic

[![schematic](schematic.svg)](https://circuitcanvas.com/p/si5jdw83jvc8eh7wcxc?canvas=layout)

## Deployment

```sh
# Install the CLI utility
brew install mpremote
# Copy the local main.py file to RPi Pico
mpremote fs cp main.py :main.py
```

## References

0. https://www.tomshardware.com/how-to/raspberry-pi-pico-setup
0. https://newbiely.com/tutorials/raspberry-pico/raspberry-pi-pico-potentiometer
0. https://diyelectromusic.com/2021/02/15/midi-in-for-3-3v-microcontrollers/
0. https://diyelectromusic.com/2021/01/23/midi-micropython-and-the-raspberry-pi-pico/
