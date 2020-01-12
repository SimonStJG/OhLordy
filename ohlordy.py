from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from time import sleep, time

import dataclasses
import json
import logging
import sys
import vlc


@dataclass
class PlaybackState:
    track: int
    time: int


class ButtonState(Enum):
    ON = "ON"
    OFF = "OFF"
    INDETERMINATE = "INDETERMINATE"


is_raspberry_pi = False
time_between_ticks = 0.05
led_blink_speed = 10  # in ticks

# TODO Do this with configparser
if is_raspberry_pi:
    tracks_directory = "/home/pi/OhLordy/tracks"
    log_file_name = "/var/log/ohlordy/ohlordy.log"
    playback_state_file_name = "/home/pi/OhLordy/playback_state"
else:
    tracks_directory = str(Path(__file__).parent / "tracks")
    log_file_name = "ohlordy.log"
    playback_state_file_name = "playback_state"

rpi_led_pin = 17
rpi_handset_pin = 4

tracks = [
    # "0.00.1 Credits.mp3",
    # "0.01.1 Foreword.mp3",
    # "0.02.1 Concerning Hobbits.mp3",
    # "0.02.2 Concerning Pipe-weed.mp3",
    # "0.02.3 Of the Ordering of the Shire.mp3",
    # "0.02.4 Of the Finding of the Ring.mp3",
    # "0.02.5 Note on the Shire Records.mp3",
    "1.01 A Long-expected Party.mp3",
    "1.02 The Shadow of the Past.mp3",
    "1.03 Three is Company.mp3",
    "1.04 A Short Cut to Mushrooms.mp3",
    "1.05 A Conspiracy Unmasked.mp3",
    "1.06 The Old Forest.mp3",
    "1.07 In the House of Tom Bombadil.mp3",
    "1.08 Fog on the Barrow-Downs.mp3",
    "1.09 At the Sign of The Prancing Pon.mp3",
    "1.10 Strider.mp3",
    "1.11 A Knife in the Dark.mp3",
    "1.12 Flight to the Ford.mp3",
    "2.01 Many Meetings.mp3",
    "2.02 The Council of Elrond.mp3",
    "2.03 The Ring Goes South.mp3",
    "2.04 A Jounney in the Dark.mp3",
    "2.05 The Bridge of Khazad-dum.mp3",
    "2.06 Lothlorien.mp3",
    "2.07 The Mirror of Galadriel.mp3",
    "2.08 Farewell to Lorien.mp3",
    "2.09 The Great River.mp3",
    "2.10 The Breaking of the Fellowship.mp3",
    "3.01 The Departure of Boromir.mp3",
    "3.02 The Riders of Rohan.mp3",
    "3.03 The Uruk-Hai.mp3",
    "3.04 Treebeard.mp3",
    "3.05 The White Rider.mp3",
    "3.06 The King of the Golden Hall.mp3",
    "3.07 Helm's Deep.mp3",
    "3.08 The Road to Isengard.mp3",
    "3.09 Flotsam and Jetsam.mp3",
    "3.10 The Voice of Saruman.mp3",
    "3.11 The Palantir.mp3",
    "4.01 The Taming of Smeagol.mp3",
    "4.02 The Passage of the Marshes.mp3",
    "4.03 The Black Gate is Closed.mp3",
    "4.04 Of Herbs and Stewed Rabbit.mp3",
    "4.05 The Window to the West.mp3",
    "4.06 The Forbidden Pool.mp3",
    "4.07 Journey to the Cross-roads.mp3",
    "4.08 The Stairs of Cirith Ungol.mp3",
    "4.09 Shelob's Lair.mp3",
    "4.10 The Choices of Master Samwise.mp3",
    "5.01 Minas Tirith.mp3",
    "5.02 The Passing of the Grey Company.mp3",
    "5.03 The Muster of Rohan.mp3",
    "5.04 The Siege of Gondor.mp3",
    "5.05 The Ride of the Rohirrim.mp3",
    "5.06 The Battle of the Pelennor Fiel.mp3",
    "5.07 The Pyre of Denethor.mp3",
    "5.08 The Houses of Healing.mp3",
    "5.09 The Last Debate.mp3",
    "5.10 The Black Gate Opens.mp3",
    "6.01 The Tower of Cirith Ungol.mp3",
    "6.02 The Land of Shadow.mp3",
    "6.03 Mount Doom.mp3",
    "6.04 The Field of Cormallen.mp3",
    "6.05 The Steward and the King.mp3",
    "6.06 Many Partings.mp3",
    "6.07 Homeward Bound.mp3",
    "6.08 The Scouring of the Shire.mp3",
    "6.09 The Grey Havens.mp3",
    "A.01 Annals of the Kings and Rulers.mp3",
    "A.02 Numenor.mp3",
    "A.03 Eriador, Arnor and the Heirs of.mp3",
    "A.04 Gondor and the Heirs of Anarion.mp3",
    "A.05 Aragorn and Arwen.mp3",
    "A.06 The House of Eorl.mp3",
    "A.07 Durin's Folk.mp3",
]

logger = logging.getLogger(__name__)

starting_playback_state = PlaybackState(track=0, time=0)


@dataclass
class ButtonDebouncer:
    reads = 0b10101010

    def set_raw_state(self, raw_state):
        self.reads = ((self.reads << 1) | (1 if raw_state else 0)) & 0xFF
        logger.debug("set_raw_state: %s", hex(self.reads))

    def get_debounced_state(self):
        logger.debug("get_debounced_state: %s", hex(self.reads))
        if self.reads == 0xFF:
            return ButtonState.ON
        elif self.reads == 0x0:
            return ButtonState.OFF
        else:
            return ButtonState.INDETERMINATE


class BlinkingLed:
    def __init__(self, set_led_state, is_blinking):
        self.set_led_state = set_led_state
        self.led_state = False
        self.tick_count = 0
        self.set_blinking(is_blinking)

    def tick(self):
        if not self.is_blinking:
            return

        self.tick_count += 1
        if self.tick_count > led_blink_speed:
            logger.debug("LED blink %s", self.led_state)
            self.tick_count = 0
            self.led_state = not self.led_state
            self.set_led_state(self.led_state)

    def set_blinking(self, is_blinking):
        self.is_blinking = is_blinking
        if not self.is_blinking:
            self.set_led_state(True)


class StateFile:
    def read(self):
        with open(playback_state_file_name, "r") as f:
            raw = json.load(f)
        return PlaybackState(**raw)

    def write(self, playback_state):
        with open(playback_state_file_name, "w") as f:
            json.dump(dataclasses.asdict(playback_state), f)


class AudioPlayer:
    time_to_start_playing = 0.3

    def __init__(self, playback_state):
        self._track = playback_state.track
        self._paused = True
        try:
            self._player = vlc.MediaPlayer()
        except (NameError, AttributeError) as e:
            raise ValueError(
                "Unable to create VLC Instance - do you have VLC installed?"
            ) from e

        self._player.set_media(self._media(self._track, playback_state.time))

    def play(self):
        self._player.play()
        self._paused = False

        # VLC player takes a while to get going, so wait for is_playing to be true
        await_condition(self._player.is_playing, self.time_to_start_playing)

    def pause(self):
        self._player.pause()
        self._paused = True

    def tick(self):
        if self._paused:
            raise ValueError("Illegal call to tick() when paused")
        # The commands below won't be executed at the same time, so it's important
        # to get them in the right order!
        player_time = self._player.get_time()
        is_playing = self._player.is_playing()
        if not is_playing:
            logger.debug("Track finished")
            self._track = (self._track + 1) % len(tracks)
            self._player.set_media(self._media(self._track, 0))
            self.play()

        return PlaybackState(track=self._track, time=player_time)

    def _media(self, track, time):
        time_secs = float(time) / 1000
        return vlc.Media(
            f"{tracks_directory}/{tracks[track]}", f"start-time={time_secs:0.2f}"
        )


def cli():
    logging.basicConfig(
        format="%(asctime)s|%(levelname)s|%(name)s|%(message)s",
        level=logging.INFO,
        handlers=[
            RotatingFileHandler(
                log_file_name,
                # 10 MiB
                maxBytes=10 * 1024 * 1024,
                backupCount=10,
            )
        ],
    )
    logger.info("Started")

    try:
        state_file = StateFile()

        try:
            playback_state = state_file.read()
        except Exception:
            logger.exception("Unable to read state, using default")
            playback_state = starting_playback_state
        logger.info("State: %s", playback_state)

        audio_player = AudioPlayer(playback_state)

        if is_raspberry_pi:
            io = rpi_io
        else:
            io = keyboard_io

        with io() as (button_pressed, set_led_state):
            main_loop(audio_player, button_pressed, set_led_state, state_file)
    except (KeyboardInterrupt, Exception):
        logger.error("Oh dear", exc_info=True)
        sys.exit(1)


def main_loop(audio_player, button_pressed, set_led_state, state_file):
    logger.info("Entering main loop")

    is_playing = False
    debouncer = ButtonDebouncer()
    blinking_led = BlinkingLed(set_led_state, is_blinking=True)
    
    while True:
        debouncer.set_raw_state(button_pressed())
        debounced_button_state = debouncer.get_debounced_state()
        blinking_led.tick()

        logger.debug("debounced_button_state: %s", debounced_button_state)
        if is_playing:
            playback_state = audio_player.tick()
            logger.debug(playback_state)
            state_file.write(playback_state)

            if debounced_button_state == ButtonState.ON:
                logger.info("Pausing audio")
                audio_player.pause()
                blinking_led.set_blinking(True)
                is_playing = False

        else:
            if debounced_button_state == ButtonState.OFF:
                logger.info("Playing audio")
                audio_player.play()
                blinking_led.set_blinking(False)
                is_playing = True

        sleep(time_between_ticks)


@contextmanager
def keyboard_io():
    import curses

    stdscr = curses.initscr()
    curses.noecho()
    curses.cbreak()
    stdscr.keypad(True)

    # Set getch to be non-blocking
    stdscr.nodelay(True)
    stdscr.clear()

    def is_button_press():
        ch = stdscr.getch()
        logger.debug("ch: %s", ch)
        if ch in [
            ord("p"),
            # space
            32,
        ]:
            return True
        elif ch is not -1:
            logger.info("Unrecognised keypress: %s", ch)
        return False

    def set_led_state(state):
        logger.debug("set_led_state: %s", state)

        stdscr.clear()
        if state:
            stdscr.addstr("ON")
        else:
            stdscr.addstr("OFF")

    yield is_button_press, set_led_state

    curses.nocbreak()
    stdscr.keypad(False)
    stdscr.nodelay(False)
    curses.echo()

    curses.endwin()


@contextmanager
def rpi_io():
    import RPi.GPIO as GPIO

    GPIO.setmode(GPIO.BCM)
    GPIO.setup(rpi_handset_pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(rpi_led_pin, GPIO.OUT)

    def is_button_press():
        raw = GPIO.input(rpi_handset_pin)
        if raw == GPIO.LOW:
            return False
        elif raw == GPIO.HIGH:
            return True
        else:
            raise NotImplementedError()

    def set_led_state(state):
        GPIO.output(rpi_led_pin, state)

    yield is_button_press, set_led_state

    GPIO.cleanup()


def await_condition(condition, timeout_seconds):
    start_time = time()
    while time() - start_time < timeout_seconds:
        if condition():
            return
        sleep(float(timeout_seconds) / 10)
    raise ValueError(f"Timeout waiting for {condition}")
