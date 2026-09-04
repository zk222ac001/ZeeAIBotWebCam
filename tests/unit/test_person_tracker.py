from robotic_classroom.camera.models import BoundingBox, CameraSnapshot, PersonDetection
from robotic_classroom.core.config import TrackingConfig
from robotic_classroom.tracking.models import TrackingState
from robotic_classroom.tracking.tracker import PersonTracker


def snapshot(sequence: int, people: tuple[PersonDetection, ...]) -> CameraSnapshot:
    return CameraSnapshot(
        backend="test",
        connected=True,
        frame_width=1000,
        frame_height=500,
        sequence=sequence,
        people=people,
    )


def person(x: int, y: int, w: int = 200, h: int = 300, confidence: float = 0.9) -> PersonDetection:
    return PersonDetection(
        confidence=confidence,
        box=BoundingBox(x=x, y=y, width=w, height=h),
    )


def test_tracker_acquires_anonymous_target() -> None:
    tracker = PersonTracker(TrackingConfig())

    observation = tracker.update(snapshot(1, (person(400, 100),)), now=10.0)

    assert observation.state is TrackingState.TRACKING
    assert observation.target_id == "Person-01"
    assert observation.center_x == 0.5
    assert observation.error_x == 0.0


def test_tracker_prefers_continuity_over_new_distant_person() -> None:
    tracker = PersonTracker(TrackingConfig(reacquire_distance_ratio=0.35))
    first = tracker.update(snapshot(1, (person(100, 100),)), now=10.0)

    second = tracker.update(
        snapshot(2, (person(130, 100), person(700, 100, confidence=0.99))),
        now=10.1,
    )

    assert first.target_id == "Person-01"
    assert second.target_id == "Person-01"
    assert second.center_x is not None
    assert second.center_x < 0.5


def test_tracker_holds_identity_briefly_then_returns_to_searching() -> None:
    tracker = PersonTracker(TrackingConfig(lost_target_timeout_ms=500))
    tracker.update(snapshot(1, (person(400, 100),)), now=10.0)

    lost = tracker.update(snapshot(2, ()), now=10.2)
    searching = tracker.update(snapshot(3, ()), now=10.7)

    assert lost.state is TrackingState.LOST
    assert lost.target_id == "Person-01"
    assert searching.state is TrackingState.SEARCHING
    assert searching.target_id is None


def test_disabled_tracker_never_acquires_target() -> None:
    tracker = PersonTracker(TrackingConfig(enabled=False))

    observation = tracker.update(snapshot(1, (person(400, 100),)), now=10.0)

    assert observation.state is TrackingState.DISABLED
    assert observation.target_id is None
