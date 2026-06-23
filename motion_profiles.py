from __future__ import annotations

MOVEMENT_LABELS = ["Base", "Agarre de barril", "Agarre esférico", "Agarre de llave", "Agarre de pinza"]
MOVEMENT_AXIS_LABELS = ["0", "1", "2", "3", "4"]
FINGER_LABELS = ["Meñique", "Anular", "Medio", "Índice", "Pulgar"]
MOTOR_GROUP_LABELS = ["Extensión/Flexión", "Abducción/Aducción"]

MOVEMENT_TABLE = [
    [ 0,   0,   0,   0,   0,   20, 15, 15, 20, 90],
    [150, 150, 165, 150, 100,  20, 15, 15, 20,  0],
    [40,   40,  55,  40, 100,  20, 15, 20, 25,  0],
    [180, 170, 150, 100, 125,  20, 15, 15, 25, 95],
    [180, 180, 140,  90, 130,  20, 15, 15, 15, 45]
]

SERVO_INVERTED = [
    True, True, False, False, True, False, False, False, False, False,
]

SERVO_COLORS = ["#0969da", "#e36209", "#1a7f37", "#8250df", "#d1242f"]
SERVO_NAMES = ["Servo 1", "Servo 2", "Servo 3", "Servo 4", "Servo 5"]
FINGER_PAIRS = [(0, 5), (1, 6), (2, 7), (3, 8), (4, 9)]
FINGER_COLORS = SERVO_COLORS
FINGER_NAMES = ["Finger 1", "Finger 2", "Finger 3", "Finger 4", "Finger 5"]

PWM_MIN = 75
PWM_MAX = 562
ANGLE_MIN = 0
ANGLE_MAX = 180


def logical_angle(servo_index: int, angle: int) -> int:
    return 180 - angle if SERVO_INVERTED[servo_index] else angle


def physical_angle(servo_index: int, angle: int) -> int:
    return logical_angle(servo_index, angle)


def pwm_from_angle(angle: int) -> int:
    scaled = PWM_MIN + (angle - ANGLE_MIN) * (PWM_MAX - PWM_MIN) / (ANGLE_MAX - ANGLE_MIN)
    return int(round(scaled))


def pwm_series_for_servo(servo_index: int) -> list[int]:
    return [
        pwm_from_angle(physical_angle(servo_index, movement[servo_index]))
        for movement in MOVEMENT_TABLE
    ]


def finger_angle_series(pair_index: int) -> list[float]:
    servo_a, servo_b = FINGER_PAIRS[pair_index]
    return [
        (physical_angle(servo_a, movement[servo_a]) + physical_angle(servo_b, movement[servo_b])) / 2
        for movement in MOVEMENT_TABLE
    ]


def finger_motor_series(movement: list[int]) -> tuple[list[float], list[float]]:
    extension_flextion = [
        physical_angle(servo_index, movement[servo_index])
        for servo_index in range(5)
    ]
    abduction_adduction = [
        physical_angle(servo_index, movement[servo_index])
        for servo_index in range(5, 10)
    ]
    return extension_flextion, abduction_adduction
