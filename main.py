import machine
import math
import sys
import utime

# ========= Config =========
DEBUG = False                # Human-readable MIDI octets (but breaks ttymidi!!!)
MIDI_CH = 1                  # 1..16
CC_SUSTAIN = 64              # Damper pedal
CC_SOFT = 67                 # Soft pedal
SUSTAIN_HYSTERESIS = 4       # Min change to emit CC
ADC_PIN = 26                 # GP26 -> ADC0
SOFT_PEDAL_PIN = 0           # Digital input, pull-up
LED_PIN = 25                 # On-board LED
MIDI_UART_ID = 1             # UART for MIDI IN/OUT
MIDI_BAUD = 31250
PEDAL_PERIOD_MS = 20         # Polling period
MOVAVG_WINDOW = 16           # Use power of 2 for fast shifts
MOVAVG_SEED = 0

# Where to send outgoing MIDI bytes:
# - If False: write to sys.stdout
# - If True:  write to UART(MIDI_UART_ID) at 31250 baud
USE_UART_OUT = True
# ==========================

class LEDBlinker:
    def __init__(self, pin_no: int):
        self.led = machine.Pin(pin_no, machine.Pin.OUT)
        self.timer = None

    def blink(self):
        if self.timer:
            self.timer.deinit()
        self.led.value(1)
        # One-shot timer to turn LED off ASAP (1 ms is plenty for a blink cue)
        self.timer = machine.Timer(mode=machine.Timer.ONE_SHOT,
                                   period=1,
                                   callback=lambda t: self.led.value(0))

class MovingAverageInt:
    """Integer moving average (EMA-like) per Daycounter trick.

    _ma_star holds N * avg, so update is:
        ma* = ma* + x - floor(ma*/N)
    If N is power of 2, uses shift for speed.
    """
    def __init__(self, N: int, seed: int = 0):
        if N <= 0:
            raise ValueError("N must be >= 1")
        self.N = N
        # compute shift if power of two without floating-point log
        self._shift = None
        if (N & (N - 1)) == 0:
            # e.g., 16 -> shift 4
            s = 0
            tmp = N
            while tmp > 1:
                tmp >>= 1
                s += 1
            self._shift = s
        self._ma_star = seed * N

    def update(self, x: int) -> int:
        if self._shift is not None:
            self._ma_star = self._ma_star + x - (self._ma_star >> self._shift)
            return self._ma_star >> self._shift
        else:
            self._ma_star = self._ma_star + x - (self._ma_star // self.N)
            return self._ma_star // self.N

    def value(self) -> int:
        if self._shift is not None:
            return self._ma_star >> self._shift
        return self._ma_star // self.N

    def reset(self, seed: int = 0):
        self._ma_star = seed * self.N

class MidiIO:
    """MIDI input (UART) + output (UART or stdout) + Running Status decoder."""
    def __init__(self, uart_in: machine.UART, use_uart_out: bool, led: LEDBlinker):
        self.uart_in = uart_in
        self.led = led
        self.use_uart_out = use_uart_out
        self.uart_out = uart_in if use_uart_out else None

        # Running status state
        self.running_status = 0
        self.note_tmp = 0
        self.level_tmp = 0

        # Precompute channelized statuses
        ch = (MIDI_CH - 1) & 0x0F
        self._status_note_on = 0x90 | ch
        self._status_note_off = 0x80 | ch
        self._status_cc = 0xB0 | ch

    def _write3(self, b0, b1, b2):
        self.led.blink()
        if self.use_uart_out:
            self.uart_out.write(bytes((b0, b1, b2)))
        if DEBUG:
            print("{:02X} {:02X} {:02X}".format(b0, b1, b2))
        else:
            # Write raw bytes over stdout
            # (MicroPython usually supports this)
            sys.stdout.write(chr(b0) + chr(b1) + chr(b2))

    # Public helpers
    def send_cc(self, cc_num: int, value: int):
        self._write3(self._status_cc, cc_num, value)

    def note_on(self, note: int, vel: int):
        self._write3(self._status_note_on, note, vel)

    def note_off(self, note: int, vel: int):
        self._write3(self._status_note_off, note, vel)

    # MIDI byte-by-byte decoder with running status
    def feed(self, mb: int):
        if 0x80 <= mb <= 0xEF:
            # Voice Category: store running status, clear temp
            self.running_status = mb
            self.note_tmp = 0
            self.level_tmp = 0
            return
        if 0xF0 <= mb <= 0xF7:
            # System Common: clear running status
            self.running_status = 0
            return
        if 0xF8 <= mb <= 0xFF:
            # Real-time: ignore here (could be handled separately)
            return

        # Data byte:
        if self.running_status == 0:
            return # unknown state; ignore

        if self.running_status == self._status_note_off:
            if self.note_tmp == 0:
                self.note_tmp = mb
            else:
                self.level_tmp = mb
                self.note_off(self.note_tmp, self.level_tmp)
                self.note_tmp = 0
                self.level_tmp = 0
        elif self.running_status == self._status_note_on:
            if self.note_tmp == 0:
                self.note_tmp = mb
            else:
                self.level_tmp = mb
                if self.level_tmp == 0:
                    self.note_off(self.note_tmp, 0)
                else:
                    self.note_on(self.note_tmp, self.level_tmp)
                self.note_tmp = 0
                self.level_tmp = 0
        elif self.running_status == self._status_cc:
            if self.note_tmp == 0:
                self.note_tmp = mb
            else:
                self.level_tmp = mb
                if self.note_tmp == 0x30 and self.level_tmp == 0x40:
                    self.uart_out.write(bytes((0xb0, 0x30, 0x40)))
                else:
                    self.send_cc(self.note_tmp, self.level_tmp)
                self.note_tmp = 0
                self.level_tmp = 0
        else:
            # Other statuses not handled here
            pass

class PedalController:
    """Reads sustain from ADC (smoothed) and soft pedal from digital pin."""
    def __init__(self, adc_pin: int, soft_pin: int, movavg: MovingAverageInt,
                 midi: MidiIO, sustain_hyst: int, period_ms: int):
        self.adc = machine.ADC(machine.Pin(adc_pin))
        self.soft = machine.Pin(soft_pin, machine.Pin.IN, machine.Pin.PULL_UP)
        self.movavg = movavg
        self.midi = midi
        self.sustain_hyst = max(0, sustain_hyst)
        self.timer = machine.Timer(period=period_ms,
                                   mode=machine.Timer.PERIODIC,
                                   callback=self._on_tick)
        # State
        self._last_sustain = 0
        self._last_soft = None # force first emit

    def _read_adc_7bit(self) -> int:
        # Convert 16-bit reading to 7-bit 0..127
        return (self.adc.read_u16() >> 9) & 0x7F

    def _read_soft(self) -> int:
        # Active-high input
        return 127 if self.soft.value() else 0

    def _on_tick(self, t):
        # Sustain (ADC smoothed)
        sustain_raw = self._read_adc_7bit()
        sustain = self.movavg.update(sustain_raw)
        if abs(sustain - self._last_sustain) >= self.sustain_hyst:
            self._last_sustain = sustain
            self.midi.send_cc(CC_SUSTAIN, sustain)

        # Soft pedal (digital)
        soft_val = self._read_soft()
        if soft_val != self._last_soft:
            self._last_soft = soft_val
            self.midi.send_cc(CC_SOFT, soft_val)

def main():
    # Hardware setup
    led = LEDBlinker(LED_PIN)

    uart = machine.UART(MIDI_UART_ID, MIDI_BAUD)
    midi = MidiIO(uart_in=uart, use_uart_out=USE_UART_OUT, led=led)

    movavg = MovingAverageInt(MOVAVG_WINDOW, seed=MOVAVG_SEED)
    _pedals = PedalController(
        adc_pin=ADC_PIN,
        soft_pin=SOFT_PEDAL_PIN,
        movavg=movavg,
        midi=midi,
        sustain_hyst=SUSTAIN_HYSTERESIS,
        period_ms=PEDAL_PERIOD_MS,
    )

    # Main MIDI IN loop
    while True:
        if uart.any():
            b = uart.read(1)
            if b:
                midi.feed(b[0])

# -------- Entry --------
if __name__ == "__main__":
    main()

