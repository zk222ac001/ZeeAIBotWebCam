# Phase 2 — Physical Hardware Validation

> Status: **validation plan and test tooling generated; physical validation still required on the robot.**
>
> Safety rule: Phase 2 validates one component at a time. Autonomous movement, WebRTC control, AI-driven movement, and full-chassis navigation remain disabled.

## 1. Hardware evaluation from the assembled robot

The current physical build is a strong match for the ZeeAIBotWebCam architecture.

| Component | Observation | Phase 2 conclusion |
|---|---|---|
| Mecanum chassis | Four yellow/black Mecanum wheels and four DC geared motors are installed | Suitable for omnidirectional telepresence; motor numbering and polarity must be mapped experimentally |
| Hiwonder controller stack | Hiwonder expansion/controller electronics are mounted above the Raspberry Pi | Validate `/dev/ttyAMA0`, board reception, battery telemetry and controller communication before any actuator test |
| Battery system | Dual 18650 holder is fitted; a visible cell is marked 3.7 V / 2200 mAh | Treat voltage/wiring as unverified until measured/read from the controller; confirm both cells are matched, correctly installed and charged |
| Ultrasonic distance sensor | Front-facing two-transducer Hiwonder ultrasonic module is mounted | Vendor `Sonar` driver uses I2C bus 1, address `0x77`, and `getDistance()` |
| IR line sensor | Four-channel downward-facing Hiwonder line sensor board is installed underneath the front of the chassis; board connector is labelled 5V/GND/SDA/SCL | Vendor `FourInfrared` driver uses I2C bus 1, address `0x78`; `readData()` returns four booleans |
| Pan/tilt camera mount | Mechanical camera bracket/servo assembly is installed | Validate servo IDs and neutral position before mounting/energising tracking movement |
| Raspberry Pi AI Camera | Camera module is present separately; the ribbon is visible at the robot but the camera is not shown mounted in the bracket | Installation and cable orientation must be checked before software testing |
| Sony IMX500 | The shown Raspberry Pi AI Camera is the IMX500-based AI Camera | Use Raspberry Pi camera stack/Picamera2; validate normal video before neural inference |
| Microphone array | Seeed Studio ReSpeaker XVF3800 USB 4-Mic Array with Case is available | Excellent fit: USB audio plus AEC, AGC, beamforming, noise suppression, VAD and DoA; validate USB/audio first, DoA later |
| Speaker | Compact external speaker module and USB cable are present | Determine whether USB is audio or power only; enumerate playback devices before selecting the output path |

### Important visual finding

The AI Camera is shown separately from the robot and the camera ribbon is standing free at the pan/tilt assembly. Do **not** run camera tests until the module is correctly mounted and the ribbon is connected to the Raspberry Pi camera connector with the correct orientation.

The Raspberry Pi model cannot be confirmed from the photographs alone. Phase 2 therefore detects it using `/proc/device-tree/model` instead of assuming a model.

---

## 2. Verified Hiwonder interfaces used by Phase 2

Phase 2 only uses interfaces confirmed in the upstream `Hiwonder/TurboPi` repository.

### Controller

```python
import HiwonderSDK.ros_robot_controller_sdk as rrc

board = rrc.Board(device="/dev/ttyAMA0")
board.enable_reception()
voltage_mv = board.get_battery()
```

`Board` opens the serial controller when constructed. The real hardware modules therefore remain lazy-loaded and are never imported by normal mock-mode application startup.

### Ultrasonic sensor

```python
from HiwonderSDK.Sonar import Sonar

sonar = Sonar()
distance = sonar.getDistance()
```

Verified upstream defaults:

- I2C bus: `1`
- I2C address: `0x77`
- `getDistance()` returns the raw distance value used by TurboPi; the existing Avoidance example divides it by 10 to display centimetres.

### Four-channel infrared line sensor

```python
from HiwonderSDK.FourInfrared import FourInfrared

line = FourInfrared()
states = line.readData()
```

Verified upstream defaults:

- I2C bus: `1`
- I2C address: `0x78`
- four Boolean outputs
- vendor example documents `True` as black-line detected

### Motor output

```python
board.set_motor_duty([[motor_id, duty]])
```

The upstream Hiwonder hardware test uses motors `1..4`. Phase 2 does **not** copy the vendor's direction signs as our robot mapping. Each wheel must be observed and recorded independently.

### PWM servo output

```python
board.pwm_servo_set_position(duration, [[servo_id, pulse]])
```

The upstream hardware test exercises PWM servo IDs 1 and 2 around pulse 1500. Phase 2 begins at the neutral pulse only and then uses a deliberately narrow validation range.

---

## 3. Safety preparation before testing

Before any test:

1. Put the robot on a stable workbench.
2. For motor testing, **lift the chassis so all four wheels are completely clear of the table**.
3. Keep hands, cables and the AI Camera ribbon away from wheels and gears.
4. Keep immediate access to the robot power switch/battery disconnect.
5. Do not charge the battery while running motor tests.
6. Do not test all motors together until each motor has passed individually.
7. Do not enable autonomous or remote movement.
8. Keep application configuration `safety.motion_enabled: false`.
9. If a motor/servo behaves unexpectedly, remove power before investigating wiring.
10. Do not use a guessed servo range; establish centre and safe limits experimentally.

Recommended improvement before later phases: add a readily reachable physical emergency-stop or motor-power cut-off.

---

## 4. Validation order

Run Phase 2 in this exact order.

```text
2.1  System / Raspberry Pi identity
       ↓
2.2  Linux devices + I2C discovery
       ↓
2.3  Hiwonder serial controller
       ↓
2.4  Battery telemetry
       ↓
2.5  Ultrasonic sensor
       ↓
2.6  IR line sensor
       ↓
2.7  AI Camera basic video
       ↓
2.8  IMX500 software availability
       ↓
2.9  ReSpeaker USB/audio discovery
       ↓
2.10 Speaker discovery/playback
       ↓
2.11 Servo neutral validation
       ↓
2.12 Individual motor validation
       ↓
2.13 Motor mapping table
       ↓
2.14 Mecanum direction validation (Phase 3 prerequisite)
```

No step should be skipped merely because the vendor demonstration previously worked.

---

## 5. Prepare the Raspberry Pi

From the repository root:

```bash
cd ~/ZeeAIBotWebCam
source .venv/bin/activate
```

Install Phase 2 inspection tools if not already present:

```bash
sudo apt update
sudo apt install -y i2c-tools usbutils python3-smbus alsa-utils
```

Ensure the vendor repository exists:

```bash
ls vendor/TurboPi/HiwonderSDK
```

If it does not:

```bash
git clone https://github.com/Hiwonder/TurboPi.git vendor/TurboPi
```

---

## 6. Step 2.1 — system identity

Run:

```bash
python scripts/phase2_readonly_check.py --system
```

Also record:

```bash
cat /proc/device-tree/model ; echo
python3 --version
uname -a
```

Pass criteria:

- Raspberry Pi model is identified.
- OS boots normally.
- Python environment works.
- project virtual environment is active.

---

## 7. Step 2.2 — Linux device and I2C discovery

Run:

```bash
python scripts/phase2_readonly_check.py --i2c
```

Expected Hiwonder devices when wired and powered:

- ultrasonic sensor: `0x77`
- four-channel line sensor: `0x78`

Also check serial:

```bash
ls -l /dev/ttyAMA0
```

Do not continue to actuator tests if the controller serial device is missing.

---

## 8. Step 2.3–2.4 — Hiwonder controller and battery

Run:

```bash
python scripts/phase2_readonly_check.py --controller
```

This opens the real Hiwonder Board, enables reception, samples battery telemetry, disables reception and closes the serial port. It sends no motor command.

Record at least:

- serial device
- whether Board construction succeeded
- battery millivolts/volts
- whether repeated samples are stable

Do not infer the battery pack voltage only from the cell markings in the photograph.

---

## 9. Step 2.5 — ultrasonic distance sensor

Run:

```bash
python scripts/phase2_readonly_check.py --sonar
```

Then place a large flat object approximately:

- 20 cm
- 50 cm
- 100 cm

in front of the sensor and repeat the test.

Acceptance target: readings should increase/decrease consistently with target distance and must not remain fixed at the driver's maximum value.

This sensor becomes a critical input to the future Safety Supervisor.

---

## 10. Step 2.6 — infrared line sensor

Run:

```bash
python scripts/phase2_readonly_check.py --ir
```

Test each of the four sensors separately using:

1. a light/white surface;
2. a dark/black tape line.

Record the order physically as:

```text
IR1  IR2  IR3  IR4
```

Do not assume code order equals left-to-right chassis order until observed on the actual robot.

---

## 11. Step 2.7–2.8 — Raspberry Pi AI Camera / Sony IMX500

The Raspberry Pi AI Camera uses the Sony IMX500 sensor and integrates with Raspberry Pi's camera stack and Picamera2.

Official documentation:

- https://www.raspberrypi.com/documentation/accessories/ai-camera.html

### Physical setup

Power the Pi down before changing the ribbon cable:

```bash
sudo poweroff
```

Then:

1. mount the AI Camera securely in the pan/tilt camera holder;
2. confirm the correct Raspberry Pi camera connector and ribbon type;
3. confirm connector orientation at both ends;
4. make sure the ribbon has enough slack for pan/tilt motion but cannot enter the wheels;
5. power on.

### Software test

```bash
rpicam-hello --list-cameras
```

Then basic preview:

```bash
rpicam-hello -t 5000
```

Check Python camera stack:

```bash
python -c "from picamera2 import Picamera2; print('Picamera2 OK')"
python -c "from picamera2.devices.imx500 import IMX500; print('IMX500 Python support OK')"
```

Pass basic video before attempting person-detection inference.

---

## 12. Step 2.9 — ReSpeaker XVF3800

The owned microphone array is the **Seeed Studio ReSpeaker XVF3800 USB 4-Mic Array with Case**.

Official documentation:

- https://wiki.seeedstudio.com/respeaker_xvf3800_introduction/

This is especially valuable for the project because the XVF3800 supports:

- 4-microphone circular capture;
- acoustic echo cancellation (AEC);
- automatic gain control (AGC);
- beamforming;
- noise suppression and dereverberation;
- voice activity detection (VAD);
- direction of arrival (DoA).

These capabilities align directly with the future active-speaker-tracking design.

Connect it by USB and run:

```bash
python scripts/phase2_readonly_check.py --audio
```

Manual checks:

```bash
lsusb
arecord -l
arecord -L
```

Do not flash ReSpeaker firmware simply because a tutorial mentions it. First determine the current firmware/mode and verify normal USB audio. Firmware changes should become a documented, reversible step only if required for DoA/VAD access.

---

## 13. Step 2.10 — speaker

The photograph confirms a compact speaker is available, but the image alone does not prove whether its USB cable transports audio or only power.

Run:

```bash
python scripts/phase2_readonly_check.py --audio
```

and inspect:

```bash
aplay -l
aplay -L
```

Once the correct output device is known, use a low-volume test signal. Avoid feedback by keeping the ReSpeaker away from the speaker during the first test.

Pass criteria:

- playback device/path is known;
- intelligible audio is produced;
- volume can be controlled;
- no severe feedback loop occurs.

---

## 14. Step 2.11 — pan/tilt servo validation

**Keep the AI Camera/ribbon mechanically clear before moving a servo.**

Start only at the presumed neutral pulse:

```bash
python scripts/phase2_actuator_test.py servo --id 1 --pulse 1500 --confirm-motion
```

Then servo 2:

```bash
python scripts/phase2_actuator_test.py servo --id 2 --pulse 1500 --confirm-motion
```

The Phase 2 script restricts servo testing to a deliberately narrow pulse band. Record which ID is pan and which is tilt, the actual centre, and safe mechanical minimum/maximum. These values will become configuration in Phase 3.

---

## 15. Step 2.12 — individual motor validation

**Lift the robot so every wheel is off the surface.**

Test one motor at a time with low duty and a short pulse:

```bash
python scripts/phase2_actuator_test.py motor --id 1 --duty 15 --duration 0.25 --confirm-motion
```

Repeat motor IDs 2, 3 and 4.

Then repeat with negative duty:

```bash
python scripts/phase2_actuator_test.py motor --id 1 --duty -15 --duration 0.25 --confirm-motion
```

The script always attempts to stop all four motors in a `finally` block.

### Motor mapping worksheet

Fill this table from observation:

| Motor ID | Physical wheel | + duty wheel rotation | - duty wheel rotation | Verified |
|---|---|---|---|---|
| 1 | TBD | TBD | TBD | ☐ |
| 2 | TBD | TBD | TBD | ☐ |
| 3 | TBD | TBD | TBD | ☐ |
| 4 | TBD | TBD | TBD | ☐ |

Do not proceed to full Mecanum movement until this table is complete.

---

## 16. Phase 2 pass/fail checklist

### Compute / OS

- [ ] Raspberry Pi model recorded
- [ ] Raspberry Pi OS version recorded
- [ ] Python version recorded
- [ ] `/dev/ttyAMA0` exists
- [ ] I2C bus 1 accessible

### Hiwonder controller

- [ ] `Board()` opens successfully
- [ ] reception can be enabled
- [ ] battery telemetry returns plausible/stable values
- [ ] serial port closes cleanly

### Sensors

- [ ] ultrasonic `0x77` visible/responding
- [ ] ultrasonic readings verified at several distances
- [ ] IR `0x78` visible/responding
- [ ] four IR channels individually mapped

### Camera

- [ ] AI Camera physically mounted
- [ ] ribbon orientation checked
- [ ] ribbon protected through pan/tilt range
- [ ] `rpicam-hello --list-cameras` detects camera
- [ ] basic image/preview works
- [ ] Picamera2 import works
- [ ] IMX500 support import works

### Audio

- [ ] ReSpeaker detected by USB
- [ ] ReSpeaker appears as capture device
- [ ] audio recording works
- [ ] speaker output path identified
- [ ] playback works at safe volume
- [ ] initial echo/feedback behaviour observed

### Actuators

- [ ] servo 1 identity and neutral verified
- [ ] servo 2 identity and neutral verified
- [ ] camera mount safe limits recorded
- [ ] motor 1 mapped
- [ ] motor 2 mapped
- [ ] motor 3 mapped
- [ ] motor 4 mapped
- [ ] positive/negative polarity recorded for every motor

### Safety gate

- [ ] no AI movement enabled
- [ ] no remote movement API enabled
- [ ] `safety.motion_enabled` remains false
- [ ] physical power cut-off is immediately accessible during tests

---

## 17. Phase 2 definition of done

Phase 2 is complete only when every physical device is known, detected, independently tested, and documented. Completion does **not** mean the robot is autonomous.

The validated output of Phase 2 becomes the input to **Phase 3 — TurboPi Hardware Adapter and Safety-Controlled Motion**, where raw vendor APIs will be wrapped behind typed interfaces, calibrated motor/servo mappings, sensor freshness checks, dead-man stopping and the central Safety Supervisor.
