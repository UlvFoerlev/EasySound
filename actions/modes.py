from enum import Enum


class Mode(str, Enum):
    PRESS = "Press"
    RELEASE = "Release"
    HOLD = "Hold"
    TURN_ON = "Turn On"
    TURN_OFF = "Turn OFF"
    PLAY_TILL_TURNED_OFF = "Play until Turned Off"


MODE_LOCALES = {
    Mode.PRESS: "action.play-sound.select_mode.press",
    Mode.RELEASE: "action.play-sound.select_mode.release",
    Mode.HOLD: "action.play-sound.select_mode.hold",
    Mode.TURN_ON: "action.play-sound.select_mode.turn_on",
    Mode.TURN_OFF: "action.play-sound.select_mode.turn_off",
    Mode.PLAY_TILL_TURNED_OFF: "action.play-sound.select_mode.till_turned_off"
}
