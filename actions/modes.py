from enum import Enum


class Mode(str, Enum):
    PRESS = "Press"
    RELEASE = "Release"
    HOLD = "Hold"
    TURN_ON = "Turn On"
    TURN_OFF = "Turn OFF"
    PLAY_TILL_TURNED_OFF = "Play until Turned Off"
