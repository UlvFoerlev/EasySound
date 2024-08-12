from enum import Flag


class Mode(Flag):
    PRESS = "Press"
    RELEASE = "Release"
    # HOLD = "Hold"


MODES = [
    Mode.PRESS,
    Mode.RELEASE,
    # Mode.PRESS | Mode.HOLD,
    # Mode.HOLD | Mode.RELEASE,
    Mode.PRESS | Mode.RELEASE,
    # Mode.PRESS | Mode.HOLD | Mode.RELEASE,
]
