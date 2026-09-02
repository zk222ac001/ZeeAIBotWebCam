# Verified Hiwonder TurboPi Hardware API Inventory

This document records API names inspected in the upstream `Hiwonder/TurboPi` repository. Production code must not invent or guess vendor method names.

| Capability | Upstream symbol | Project treatment |
|---|---|---|
| Controller | `HiwonderSDK.ros_robot_controller_sdk.Board()` | Reuse behind adapter |
| Reception | `board.enable_reception()` | Reuse behind adapter |
| Battery | `board.get_battery()` | Reuse behind adapter |
| Motor duty | `board.set_motor_duty(...)` | Phase 3 only, behind safety |
| PWM servo position | `board.pwm_servo_set_position(duration, positions)` | Phase 3 only, behind safety |
| RGB | `board.set_rgb(...)` | Reuse behind adapter |
| Buzzer | `board.set_buzzer(freq, on_time, off_time, repeat)` | Reuse behind adapter |
| Mecanum controller | `HiwonderSDK.mecanum.MecanumChassis()` | Reuse/wrap |
| Velocity | `car.set_velocity(velocity, direction, angular_rate)` | Phase 3 only, safety-gated |
| Translation | `car.translation(velocity_x, velocity_y)` | Phase 3 only, safety-gated |
| Ultrasonic | `HiwonderSDK.Sonar.Sonar().getDistance()` | Reuse behind sensor service |
| USB camera wrapper | `Camera.Camera()` / `camera.frame` | Legacy/fallback only |

## Important side effect

The upstream controller `Board` opens its serial port in construction. The upstream `mecanum.py` also creates a `Board` object at module scope. For this reason:

- mock mode must not import the real backend;
- real vendor modules are loaded lazily;
- production application modules must not casually import `HiwonderSDK.mecanum`;
- a controlled `TurboPiAdapter` will own the vendor objects in Phase 3.

## Upstream behavioral examples

`Functions/FaceTracking.py` and `Functions/Avoidance.py` demonstrate useful control ideas, but they directly issue motor/servo commands. They are algorithm references only for this project. Their hardware-command architecture will not be copied.

## Units requiring Phase 2 confirmation

Even where an upstream example implies a unit, physical validation remains required for:

- battery voltage scaling;
- ultrasonic distance units;
- motor polarity/direction;
- chassis coordinate conventions;
- pan/tilt servo channels;
- center pulse values;
- safe min/max pulse values.
