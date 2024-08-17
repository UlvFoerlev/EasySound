from enum import Enum


class Mode(str, Enum):
    PRESS = "Press"
    RELEASE = "Release"
    HOLD = "Hold"


# MODES = [
#     Mode.PRESS,
#     Mode.RELEASE,
#     # Mode.PRESS | Mode.HOLD,
#     # Mode.HOLD | Mode.RELEASE,
#     Mode.PRESS | Mode.RELEASE,
#     # Mode.PRESS | Mode.HOLD | Mode.RELEASE,
# ]
