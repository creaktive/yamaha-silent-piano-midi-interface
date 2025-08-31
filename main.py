import machine
import math
import sys
import utime
import ustruct

DEBUG = False
#DEBUG = True

pin = machine.Pin(25, machine.Pin.OUT)
pinIn = machine.Pin(0, machine.Pin.IN, machine.Pin.PULL_UP)
uart = machine.UART(1, 31250)
adc = machine.ADC(machine.Pin(26)) # Corresponds to GP26, which is ADC0 on the Pico

timerLED = None
def blinkLED():
    global timerLED

    if timerLED:
        timerLED.deinit()

    pin.value(1)
    timerLED = machine.Timer(mode=machine.Timer.ONE_SHOT, period=1, callback=lambda t: pin.value(0))

def sendMidi(status, data1, data2):
    blinkLED()
    if DEBUG:
        print("{0:02X} {1:02X} {2:02X}".format(status, data1, data2))
    else:
        sys.stdout.buffer.write("".join(chr(b) for b in [status, data1, data2]))

# Basic MIDI handling commands
def doMidiNoteOn(note,vel):
    sendMidi(MIDIRunningStatus, note, vel)

def doMidiNoteOff(note,vel):
    sendMidi(MIDIRunningStatus, note, vel)

# Implement a simple MIDI decoder.
#
# MIDI supports the idea of Running Status.
#
# If the command is the same as the previous one,
# then the status (command) byte doesn't need to be sent again.
#
# The basis for handling this can be found here:
#  http://midi.teragonaudio.com/tech/midispec/run.htm
# Namely:
#   Buffer is cleared (ie, set to 0) at power up.
#   Buffer stores the status when a Voice Category Status (ie, 0x80 to 0xEF) is received.
#   Buffer is cleared when a System Common Category Status (ie, 0xF0 to 0xF7) is received.
#   Nothing is done to the buffer when a RealTime Category message is received.
#   Any data bytes are ignored when the buffer is 0.
#
MIDICH = 1
MIDIRunningStatus = 0
MIDINote = 0
MIDILevel = 0
def doMidi(mb):
    global MIDIRunningStatus
    global MIDINote
    global MIDILevel
    if ((mb >= 0x80) and (mb <= 0xEF)):
        # MIDI Voice Category Message.
        # Action: Start handling Running Status
        MIDIRunningStatus = mb
        MIDINote = 0
        MIDILevel = 0
    elif ((mb >= 0xF0) and (mb <= 0xF7)):
        # MIDI System Common Category Message.
        # Action: Reset Running Status.
        MIDIRunningStatus = 0
    elif ((mb >= 0xF8) and (mb <= 0xFF)):
        # System Real-Time Message.
        # Action: Ignore these.
        pass
    else:
        # MIDI Data
        if (MIDIRunningStatus == 0):
            # No record of what state we're in, so can go no further
            return
        if (MIDIRunningStatus == (0x80|(MIDICH-1))):
            # Note OFF Received
            if (MIDINote == 0):
                # Store the note number
                MIDINote = mb
            else:
                # Already have the note, so store the level
                MIDILevel = mb
                doMidiNoteOff (MIDINote, MIDILevel)
                MIDINote = 0
                MIDILevel = 0
        elif (MIDIRunningStatus == (0x90|(MIDICH-1))):
            # Note ON Received
            if (MIDINote == 0):
                # Store the note number
                MIDINote = mb
            else:
                # Already have the note, so store the level
                MIDILevel = mb
                if (MIDILevel == 0):
                    doMidiNoteOff (MIDINote, MIDILevel)
                else:
                    doMidiNoteOn (MIDINote, MIDILevel)
                MIDINote = 0
                MIDILevel = 0
        else:
            # This is a MIDI command we aren't handling right now
            pass

class MovingAverageInt:
    def __init__(self, N: int, seed: int = 0):
        """
        N: averaging window (use a power of two for fast shifts).
        seed: initial average value.
        """
        if N <= 0:
            raise ValueError("N must be >= 1")
        self.N = N
        # check if N is power of two
        self._shift = None
        if (N & (N - 1)) == 0:
            self._shift = int(math.log(N, 2))

        # accumulator MA* = N * average
        self._ma_star = seed * N

    def update(self, x: int) -> int:
        """Feed one integer sample and return the current average."""
        if self._shift is not None:
            # N is power of two → fast shift
            self._ma_star = self._ma_star + x - (self._ma_star >> self._shift)
            return self._ma_star >> self._shift
        else:
            # generic case → integer division
            self._ma_star = self._ma_star + x - (self._ma_star // self.N)
            return self._ma_star // self.N

    def value(self) -> int:
        """Return the current average without updating."""
        if self._shift is not None:
            return self._ma_star >> self._shift
        else:
            return self._ma_star // self.N

    def reset(self, seed: int = 0):
        """Reset the filter to a given average value."""
        self._ma_star = seed * self.N

lastSustainPedal = 0
lastSoftPedal = None
ma = MovingAverageInt(16, seed=0)
def pedalInput(t):
    global lastSustainPedal
    global lastSoftPedal

    # Retrieve analog value from pin A0:
    adcValue = adc.read_u16() >> 9 # Convert 16-bit to 7-bit by right shifting 9 bits

    # Use Moving Average to filter out ADC noise
    sustainPedal = ma.update(adcValue)
    if abs(lastSustainPedal - sustainPedal) >= 4:
        lastSustainPedal = sustainPedal
        sendMidi(0xB0|(MIDICH-1), 64, sustainPedal)

    softPedal = 0 if pinIn.value() else 127
    if lastSoftPedal != softPedal:
        lastSoftPedal = softPedal
        sendMidi(0xB0|(MIDICH-1), 67, softPedal)

timerPedal = machine.Timer(mode=machine.Timer.PERIODIC, period=100, callback=pedalInput)

# Infinite loop
while True:
    if uart.any():
        octet = uart.read(1)[0]
        doMidi(octet)
