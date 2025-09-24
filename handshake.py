import _thread
import machine
import sys
import time

class LEDBlinker:
    def __init__(self):
        self.led = machine.Pin(25, machine.Pin.OUT)
        self.timer = None

    def blink(self):
        if self.timer:
            self.timer.deinit()

        self.led.value(1)

        # One-shot timer to turn LED off ASAP (1 ms is plenty for a blink cue)
        self.timer = machine.Timer(mode=machine.Timer.ONE_SHOT,
                                   period=1,
                                   callback=lambda t: self.led.value(0))

class MidiIO:
    def __init__(self, led: LEDBlinker):
        self.last = None
        self.led = led
        self.uart = machine.UART(1, 31250, timeout=30_000)

    def _print(self, direction, data):
        self.led.blink()

        now = time.ticks_ms()
        delta = time.ticks_diff(now, self.last if self.last else now)
        self.last = now

        if not data:
            print('{:s}\t{:d}\tEMPTY'.format(direction, delta))
        else:
            printable = ', '.join(['0x{:02X}'.format(c) for c in data])
            print('{:s}\t{:d}\t({:s})'.format(direction, delta, printable))

    def read(self, n: int):
        data = self.uart.read(n)
        self._print('<', data)
        return data

    def write(self, data):
        n = self.uart.write(bytes(data))
        self.uart.flush()
        self._print('>', data)
        return n

# def core0_thread():
#     led = LEDBlinker()
#     midi = MidiIO(led=led)
#
#     while True:
#         char = sys.stdin.read(1)
#         if char == '1':
#             midi.write((0xB0, 0x30, 0x40))
#         elif char == '2':
#             midi.write((0xB0, 0x30, 0x40, 0x40, 0x00))
#         if char == '3':
#             midi.write((0xB0, 0x40, 0x00))
#
# def core1_thread():
#     led = LEDBlinker()
#     midi = MidiIO(led=led)
#
#     while True:
#         midi.read(1)
#
# if __name__ == '__main__':
#     reader = _thread.start_new_thread(core1_thread, ())
#
#     core0_thread()

if __name__ == '__main__':
    led = LEDBlinker()
    midi = MidiIO(led=led)

    midi.write((0xB0, 0x30, 0x40, 0x40, 0x00))

    while True:
        b = midi.read(1)
        # if b:
        #     midi.write(b)
