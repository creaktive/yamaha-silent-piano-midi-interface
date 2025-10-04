import analogio
import board
import busio
import digitalio
import time
import usb_midi

class Logger:
    last_event = None
    led = None

    @classmethod
    def update(self):
        if not self.led:
            self.led = digitalio.DigitalInOut(board.LED)
            self.led.direction = digitalio.Direction.OUTPUT

        if self.led.value and time.monotonic() >= self.last_event + 0.001:
            self.led.value = False

    @classmethod
    def print(self, direction, data, as_is=False):
        self.update()

        now = time.monotonic()
        delta = int((now - self.last_event) * 1000) if self.last_event else 0
        self.last_event = now

        self.led.value = True

        if as_is:
            print('{:s}\t{:d}\t{:s}'.format(direction, delta, data))
        else:
            buf = ', '.join(['0x{:02X}'.format(c) for c in data])
            print('{:s}\t{:d}\t({:s})'.format(direction, delta, buf))

class Keyboard:
    def __init__(self):
        self.uart = busio.UART(tx=board.GP4, rx=board.GP5, baudrate=31250, timeout=1.0)

    def read(self, n: int):
        data = self.uart.read(n)
        if data:
            Logger.print('<', data)
        else:
            Logger.print('<', '*EMPTY*', True)
        return data

    def write(self, data):
        n = self.uart.write(data)
        Logger.print('>', data)
        return n

    def update(self, expect=3):
        n = self.uart.in_waiting
        if n < expect:
            return None

        return self.read(n)

class Pedals:
    next_update = None
    soft_state = None
    sust_state = None

    def __init__(self):
        self.soft = digitalio.DigitalInOut(board.GP0)
        self.soft.switch_to_input(pull=digitalio.Pull.UP)
        self.sust = analogio.AnalogIn(board.A0)

    def _update(self):
        now = time.monotonic()
        if self.next_update == None or self.next_update <= now:
            self.next_update = now + 0.01
            return True
        return False

    def update_soft(self):
        if not self._update():
            return None

        soft = 0x7F if self.soft.value else 0x00
        if self.soft_state == soft:
            return None

        self.soft_state = soft
        return soft

    def update_sust(self):
        if not self._update():
            return None

        # Convert 16-bit reading to 7-bit 0..127
        sust = (self.sust.value >> 9) & 0x7F

        # Sensitivity threshold
        if sust <= 2:
            sust = 0

        if self.sust_state == sust:
            return None

        self.sust_state = sust
        return sust

if __name__ == '__main__':
    keyboard = Keyboard()
    pedals = Pedals()
    usb = usb_midi.ports[1]

    # handshake
    keyboard.read(12)
    keyboard.write(bytes((0xB0, 0x30, 0x40)))

    while True:
        msg = keyboard.update()
        if msg != None:
            usb.write(msg)

        sust = pedals.update_sust()
        if sust != None:
            msg = bytes((0xB0, 0x40, sust))
            keyboard.write(msg)

        soft = pedals.update_soft()
        if soft != None:
            msg = bytes((0xB0, 0x43, soft))
            keyboard.write(msg)

        Logger.update()
