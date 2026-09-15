from robotic_classroom.control.commands import MotionCommand
from robotic_classroom.hardware.turbopi_adapter import TurboPiAdapter


def test_forward_pattern_matches_hiwonder_mecanum() -> None:
    assert TurboPiAdapter._motor_duties(MotionCommand(forward=1.0)) == [
        [1, -30],
        [2, 30],
        [3, -30],
        [4, 30],
    ]


def test_backward_pattern_matches_hiwonder_mecanum() -> None:
    assert TurboPiAdapter._motor_duties(MotionCommand(forward=-1.0)) == [
        [1, 30],
        [2, -30],
        [3, 30],
        [4, -30],
    ]


def test_right_strafe_pattern_matches_hiwonder_mecanum() -> None:
    assert TurboPiAdapter._motor_duties(MotionCommand(sideways=1.0)) == [
        [1, -30],
        [2, -30],
        [3, 30],
        [4, 30],
    ]


def test_left_strafe_pattern_matches_hiwonder_mecanum() -> None:
    assert TurboPiAdapter._motor_duties(MotionCommand(sideways=-1.0)) == [
        [1, 30],
        [2, 30],
        [3, -30],
        [4, -30],
    ]


def test_rotation_patterns_match_hiwonder_mecanum() -> None:
    assert TurboPiAdapter._motor_duties(MotionCommand(rotation=1.0)) == [
        [1, -30],
        [2, -30],
        [3, -30],
        [4, -30],
    ]
    assert TurboPiAdapter._motor_duties(MotionCommand(rotation=-1.0)) == [
        [1, 30],
        [2, 30],
        [3, 30],
        [4, 30],
    ]
