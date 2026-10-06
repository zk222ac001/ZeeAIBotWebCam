from types import SimpleNamespace
from unittest.mock import MagicMock

from robotic_classroom.autonomy.models import AutonomyState
from robotic_classroom.autonomy.service import AutonomyService
from robotic_classroom.control.commands import MotionCommand
from robotic_classroom.core.config import AutonomyConfig, AxisConfig


def make_service(config: AutonomyConfig) -> tuple[AutonomyService, MagicMock]:
    safety = MagicMock()
    safety.settings = SimpleNamespace(
        safety=SimpleNamespace(minimum_obstacle_distance_cm=30.0)
    )
    safety.leases.validate.return_value = True
    safety.heartbeat.return_value = True

    service = AutonomyService(
        config,
        AxisConfig(
            channel=1,
            center=1500,
            minimum=1350,
            maximum=1650,
            inverted=False,
        ),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        safety,
    )
    return service, safety


def test_execute_mode_requires_pilot_validation_before_arming() -> None:
    service, safety = make_service(
        AutonomyConfig(
            enabled=True,
            mode="execute",
            require_pilot_validation=True,
            pilot_validated=False,
        )
    )

    armed, reason = service.arm("1234567890abcdef")

    assert armed is False
    assert "pilot validation required" in reason
    safety.leases.validate.assert_not_called()


def test_plan_only_arm_updates_status_immediately() -> None:
    service, _ = make_service(AutonomyConfig(enabled=True, mode="plan_only"))

    armed, _ = service.arm()

    assert armed is True
    assert service.status().armed is True
    assert service.status().motion_executed is False


def test_disarm_updates_status_immediately_and_requests_stop() -> None:
    service, safety = make_service(AutonomyConfig(enabled=True, mode="plan_only"))
    service.arm()

    service.disarm()

    assert service.status().armed is False
    assert service.status().planned_command.is_stop
    safety.submit_motion.assert_called()


def test_rotation_only_policy_rejects_translation() -> None:
    service, _ = make_service(
        AutonomyConfig(enabled=True, execution_policy="rotation_only")
    )

    allowed, reason = service._execution_policy_allows(MotionCommand(forward=0.1))
    rotate_allowed, _ = service._execution_policy_allows(MotionCommand(rotation=0.1))

    assert allowed is False
    assert "blocked translation" in reason
    assert rotate_allowed is True


def test_target_stability_requires_consecutive_same_target() -> None:
    service, _ = make_service(
        AutonomyConfig(enabled=True, target_stability_cycles=3)
    )

    assert service._update_target_stability(AutonomyState.TRACKING, "Person-01") == 1
    assert service._update_target_stability(AutonomyState.TRACKING, "Person-01") == 2
    assert service._update_target_stability(AutonomyState.TRACKING, "Person-02") == 1
    assert service._update_target_stability(AutonomyState.TARGET_LOST, None) == 0
