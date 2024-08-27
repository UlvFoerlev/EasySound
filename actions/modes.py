from enum import Enum


class Mode(str, Enum):
    PRESS = "Press"
    RELEASE = "Release"
    HOLD = "Hold"
    PLAY_TILL_STOPPED = "Play till Stopped"


# MODES = [
#     Mode.PRESS,
#     Mode.RELEASE,
#     # Mode.PRESS | Mode.HOLD,
#     # Mode.HOLD | Mode.RELEASE,
#     Mode.PRESS | Mode.RELEASE,
#     # Mode.PRESS | Mode.HOLD | Mode.RELEASE,
# ]
