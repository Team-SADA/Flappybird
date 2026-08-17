import os
os.environ["GLOG_minloglevel"] = "2"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import pygame
import random
import sys
import cv2
import mediapipe as mp
from collections import deque

pygame.init()

# =====================
# 카메라 번호 설정
# =====================
# 보통 노트북 기본 카메라가 0, 외장 웹캠이 1
# 반대로 나오면 0과 1을 바꾸면 됨
P1_CAMERA_INDEX = 0
# =====================
# 화면 설정
# =====================
# 9번 기능 제외: 창모드/전체화면 선택 옵션 없이 기존 코드처럼 전체화면 고정
info = pygame.display.Info()
WIDTH, HEIGHT = info.current_w, info.current_h

screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
pygame.display.set_caption("Camera Flappy Bird 1P")

clock = pygame.time.Clock()

PANEL_W = WIDTH
PANEL_H = HEIGHT

mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils

# =====================
# 에셋 설정
# =====================
# True = assets/sprites 안의 플래피버드 에셋 사용
# False = 코드로 직접 그린 새/배경/파이프 사용
USE_FLAPPY_ASSETS = True

# 새 색상: "yellow", "blue", "red"
P1_BIRD_COLOR = "yellow"
P2_BIRD_COLOR = "red"

# 파이프 색상: "green" 또는 "red"
PIPE_COLOR = "green"

# 배경: "day" 또는 "night"
BG_TIME = "day"

# 새 스프라이트 크기 배율
BIRD_SPRITE_SCALE = 1.8

ASSETS_DIR = "assets/sprites"

# 기존 커스텀 bird.png도 쓰고 싶으면 True
USE_BIRD_IMAGE = False
BIRD_IMAGE_PATH = "bird.png"

# =====================
# 점프/중력 튜닝
# =====================
JUMP_POWER = -350
GRAVITY = 1100


def remove_border_black_background(surface):
    """
    이미지 바깥쪽과 연결된 검은 배경만 투명하게 만든다.
    새의 눈처럼 내부에 있는 검은색은 최대한 유지된다.
    """
    surface = surface.convert_alpha()
    w, h = surface.get_size()

    visited = set()
    q = deque()

    def is_black_pixel(x, y):
        r, g, b, a = surface.get_at((x, y))
        return a > 0 and r < 15 and g < 15 and b < 15

    for x in range(w):
        if is_black_pixel(x, 0):
            q.append((x, 0))
            visited.add((x, 0))

        if is_black_pixel(x, h - 1):
            q.append((x, h - 1))
            visited.add((x, h - 1))

    for y in range(h):
        if is_black_pixel(0, y):
            q.append((0, y))
            visited.add((0, y))

        if is_black_pixel(w - 1, y):
            q.append((w - 1, y))
            visited.add((w - 1, y))

    while q:
        x, y = q.popleft()
        surface.set_at((x, y), (0, 0, 0, 0))

        for nx, ny in [
            (x + 1, y),
            (x - 1, y),
            (x, y + 1),
            (x, y - 1)
        ]:
            if 0 <= nx < w and 0 <= ny < h:
                if (nx, ny) not in visited and is_black_pixel(nx, ny):
                    visited.add((nx, ny))
                    q.append((nx, ny))

    return surface


if USE_BIRD_IMAGE:
    try:
        bird_source_image = pygame.image.load(BIRD_IMAGE_PATH).convert_alpha()
        bird_source_image = remove_border_black_background(bird_source_image)

        bird_box = bird_source_image.get_bounding_rect()
        bird_source_image = bird_source_image.subsurface(bird_box).copy()

    except Exception:
        bird_source_image = None
else:
    bird_source_image = None


# =====================
# 플래피버드 에셋 로드
# =====================
FLAPPY_ASSETS = {
    "pipe": None,
    "background": None,
    "base": None,
    "numbers": None,
    "gameover": None,
    "message": None,
}

FLAPPY_BIRD_FRAMES = {
    "yellow": None,
    "blue": None,
    "red": None,
}


def load_flappy_assets():
    if not USE_FLAPPY_ASSETS:
        return

    try:
        for color in ["yellow", "blue", "red"]:
            FLAPPY_BIRD_FRAMES[color] = [
                pygame.image.load(f"{ASSETS_DIR}/{color}bird-upflap.png").convert_alpha(),
                pygame.image.load(f"{ASSETS_DIR}/{color}bird-midflap.png").convert_alpha(),
                pygame.image.load(f"{ASSETS_DIR}/{color}bird-downflap.png").convert_alpha(),
            ]

        FLAPPY_ASSETS["pipe"] = pygame.image.load(f"{ASSETS_DIR}/pipe-{PIPE_COLOR}.png").convert_alpha()
        FLAPPY_ASSETS["background"] = pygame.image.load(f"{ASSETS_DIR}/background-{BG_TIME}.png").convert_alpha()
        FLAPPY_ASSETS["base"] = pygame.image.load(f"{ASSETS_DIR}/base.png").convert_alpha()
        FLAPPY_ASSETS["numbers"] = [
            pygame.image.load(f"{ASSETS_DIR}/{i}.png").convert_alpha()
            for i in range(10)
        ]

        try:
            FLAPPY_ASSETS["gameover"] = pygame.image.load(f"{ASSETS_DIR}/gameover.png").convert_alpha()
        except Exception:
            FLAPPY_ASSETS["gameover"] = None

        try:
            FLAPPY_ASSETS["message"] = pygame.image.load(f"{ASSETS_DIR}/message.png").convert_alpha()
        except Exception:
            FLAPPY_ASSETS["message"] = None

        print("[INFO] Flappy Bird assets loaded successfully.")

    except Exception as e:
        print(f"[WARNING] Failed to load flappy assets: {e}")
        print("[WARNING] Falling back to code-drawn graphics.")

        for key in FLAPPY_ASSETS:
            FLAPPY_ASSETS[key] = None

        for color in FLAPPY_BIRD_FRAMES:
            FLAPPY_BIRD_FRAMES[color] = None


load_flappy_assets()


class PlayerGame:
    def __init__(self, name, camera_index, panel_x, seed, bird_color="yellow"):
        self.name = name
        self.camera_index = camera_index
        self.panel_x = panel_x
        self.panel_y = 0
        self.w = PANEL_W
        self.h = PANEL_H
        self.bird_color = bird_color

        self.scale = min(self.w / 800, self.h / 720)

        self.ground_height = int(90 * self.scale)
        self.ground_y = self.h - self.ground_height

        self.font = pygame.font.SysFont("arial", int(52 * self.scale), bold=True)
        self.small_font = pygame.font.SysFont("arial", int(24 * self.scale), bold=True)
        self.tiny_font = pygame.font.SysFont("arial", int(19 * self.scale), bold=True)

        self.bird_x = int(165 * self.scale)
        self.bird_y = self.h // 2
        self.bird_radius = int(22 * self.scale)
        self.bird_velocity = 0

        self.gravity = GRAVITY * self.scale
        self.jump_power = JUMP_POWER * self.scale

        self.pipe_width = int(90 * self.scale)

        # 시작 난이도
        self.base_pipe_gap = int(250 * self.scale)
        self.base_pipe_speed = 210 * self.scale
        self.base_spawn_interval = 1.35

        # 최대 난이도 제한
        self.min_pipe_gap = int(175 * self.scale)
        self.max_pipe_speed = 310 * self.scale
        self.min_spawn_interval = 0.90

        self.pipes = []

        self.score = 0
        self.distance = 0
        self.game_over = False
        self.game_over_timer = 0
        self.game_over_freeze_time = 1.5

        self.spawn_timer = 0
        self.ground_scroll = 0

        self.ready_arm = None
        self.jump_cooldown = 0

        self.camera_status = "No body detected"
        self.last_camera_frame = None

        self.random_seed = seed
        self.rng = random.Random(seed)

        print(f"[INFO] {name}: Opening camera {camera_index}...")
        self.cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        if not self.cap.isOpened():
            print(f"[WARNING] {name}: Camera {camera_index} NOT FOUND! Webcam control will not work.")
        else:
            print(f"[INFO] {name}: Camera {camera_index} opened successfully.")

        self.pose = mp_pose.Pose(
            model_complexity=0,
            min_detection_confidence=0.35,
            min_tracking_confidence=0.35
        )

        self.cam_preview_w = int(230 * self.scale)
        self.cam_preview_h = int(170 * self.scale)
        self.cam_margin = int(18 * self.scale)

        self.clouds = [
            {"x": int(100 * self.scale), "y": int(90 * self.scale), "scale": 1.0 * self.scale},
            {"x": int(360 * self.scale), "y": int(140 * self.scale), "scale": 0.8 * self.scale},
            {"x": int(650 * self.scale), "y": int(80 * self.scale), "scale": 1.1 * self.scale},
        ]

        if bird_source_image is not None:
            bird_target_width = int(82 * self.scale)
            bird_target_height = int(
                bird_target_width * bird_source_image.get_height() / bird_source_image.get_width()
            )

            self.bird_image_base = pygame.transform.scale(
                bird_source_image,
                (bird_target_width, bird_target_height)
            )
        else:
            self.bird_image_base = None

        # 플래피버드 에셋 프리렌더
        self.flappy_bird_frames = None
        self.flappy_pipe_body = None
        self.flappy_pipe_body_flipped = None
        self.flappy_background = None
        self.flappy_base = None
        self.flappy_numbers = None
        self.flappy_gameover = None

        color_frames = FLAPPY_BIRD_FRAMES.get(self.bird_color)

        if USE_FLAPPY_ASSETS and color_frames is not None and FLAPPY_ASSETS["pipe"] is not None:
            bird_scale = BIRD_SPRITE_SCALE * self.scale

            self.flappy_bird_frames = [
                pygame.transform.scale(
                    frame,
                    (
                        int(frame.get_width() * bird_scale),
                        int(frame.get_height() * bird_scale)
                    )
                )
                for frame in color_frames
            ]

            pipe = FLAPPY_ASSETS["pipe"]
            pipe_scale_x = self.pipe_width / pipe.get_width()
            pipe_new_h = int(pipe.get_height() * pipe_scale_x)
            self.flappy_pipe_body = pygame.transform.scale(
                pipe,
                (self.pipe_width, pipe_new_h)
            )
            self.flappy_pipe_body_flipped = pygame.transform.flip(
                self.flappy_pipe_body,
                False,
                True
            )

            bg = FLAPPY_ASSETS["background"]
            bg_scale = self.ground_y / bg.get_height()
            self.flappy_background = pygame.transform.scale(
                bg,
                (int(bg.get_width() * bg_scale), self.ground_y)
            )

            base = FLAPPY_ASSETS["base"]
            base_scale = self.ground_height / base.get_height()
            self.flappy_base = pygame.transform.scale(
                base,
                (int(base.get_width() * base_scale), self.ground_height)
            )

            if FLAPPY_ASSETS["numbers"] is not None:
                num_scale = 1.5 * self.scale
                self.flappy_numbers = [
                    pygame.transform.scale(
                        num,
                        (
                            int(num.get_width() * num_scale),
                            int(num.get_height() * num_scale)
                        )
                    )
                    for num in FLAPPY_ASSETS["numbers"]
                ]

            if FLAPPY_ASSETS["gameover"] is not None:
                go = FLAPPY_ASSETS["gameover"]
                go_scale = 2.0 * self.scale
                self.flappy_gameover = pygame.transform.scale(
                    go,
                    (
                        int(go.get_width() * go_scale),
                        int(go.get_height() * go_scale)
                    )
                )

        # 날개짓 애니메이션
        self.bird_anim_time = 0.0
        self.bird_anim_speed = 8.0

        # 죽음 낙하/회전 애니메이션
        self.death_spin_angle = 0.0
        self.death_spin_speed = 540.0

        self.reset()

    def reset(self):
        self.bird_y = self.h // 2
        self.bird_velocity = 0

        self.pipes = []
        self.score = 0
        self.distance = 0

        self.game_over = False
        self.game_over_timer = 0

        self.spawn_timer = 0
        self.ground_scroll = 0

        self.ready_arm = None
        self.jump_cooldown = 0

        self.death_spin_angle = 0.0

        self.rng = random.Random(self.random_seed)

        self.spawn_pipe()

    def close(self):
        self.cap.release()
        self.pose.close()

    def get_difficulty_values(self):
        difficulty_level = min(self.score, 30)

        current_pipe_gap = self.base_pipe_gap - int(difficulty_level * 2.5 * self.scale)
        current_pipe_gap = max(self.min_pipe_gap, current_pipe_gap)

        current_pipe_speed = self.base_pipe_speed + difficulty_level * 4.0 * self.scale
        current_pipe_speed = min(self.max_pipe_speed, current_pipe_speed)

        current_spawn_interval = self.base_spawn_interval - difficulty_level * 0.015
        current_spawn_interval = max(self.min_spawn_interval, current_spawn_interval)

        return current_pipe_gap, current_pipe_speed, current_spawn_interval, difficulty_level

    def spawn_pipe(self):
        current_pipe_gap, _, _, _ = self.get_difficulty_values()

        # 구멍 위치 범위 조절
        # 숫자가 작을수록 위/아래 끝까지 많이 나옴
        # 숫자가 클수록 구멍 위치 범위가 좁아짐
        margin = int(65 * self.scale)

        min_gap_y = current_pipe_gap // 2 + margin
        max_gap_y = self.ground_y - current_pipe_gap // 2 - margin

        if max_gap_y <= min_gap_y:
            gap_y = self.h // 2
        else:
            total_range = max_gap_y - min_gap_y

            zone = self.rng.choice(["top", "top", "middle", "bottom", "bottom"])

            if zone == "top":
                low = min_gap_y
                high = min_gap_y + total_range // 3

            elif zone == "middle":
                low = min_gap_y + total_range // 3
                high = min_gap_y + total_range * 2 // 3

            else:
                low = min_gap_y + total_range * 2 // 3
                high = max_gap_y

            gap_y = self.rng.randint(low, high)

        self.pipes.append({
            "x": self.w + int(40 * self.scale),
            "gap_y": gap_y,
            "gap": current_pipe_gap,
            "passed": False
        })

    def detect_body_jump(self, dt):
        """
        팔을 올리면 준비 상태로 저장하고,
        그 팔이 다시 내려오면 점프한다.

        중간에 웹캠 인식이 잠깐 끊겨도 ready 상태를 유지해서
        동작 인식이 덜 씹히게 한다.
        """
        if self.jump_cooldown > 0:
            self.jump_cooldown -= dt

        success, frame = self.cap.read()

        if not success:
            self.camera_status = f"Camera {self.camera_index} not found"
            return False

        frame = cv2.flip(frame, 1)

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self.pose.process(rgb)

        jump = False
        self.camera_status = "No body detected"

        if result.pose_landmarks:
            mp_drawing.draw_landmarks(
                frame,
                result.pose_landmarks,
                mp_pose.POSE_CONNECTIONS
            )

            landmarks = result.pose_landmarks.landmark

            left_shoulder = landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER]
            right_shoulder = landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER]
            left_wrist = landmarks[mp_pose.PoseLandmark.LEFT_WRIST]
            right_wrist = landmarks[mp_pose.PoseLandmark.RIGHT_WRIST]

            # 팔 올림 판정은 살짝 쉽게
            UP_MARGIN = 0.02

            # 팔 내림 판정은 확실하게
            DOWN_MARGIN = 0.04

            # 관절 신뢰도
            MIN_VISIBILITY = 0.35

            left_valid = (
                left_shoulder.visibility > MIN_VISIBILITY
                and left_wrist.visibility > MIN_VISIBILITY
            )

            right_valid = (
                right_shoulder.visibility > MIN_VISIBILITY
                and right_wrist.visibility > MIN_VISIBILITY
            )

            left_arm_up = (
                left_valid
                and left_wrist.y < left_shoulder.y - UP_MARGIN
            )

            right_arm_up = (
                right_valid
                and right_wrist.y < right_shoulder.y - UP_MARGIN
            )

            left_arm_down = (
                left_valid
                and left_wrist.y > left_shoulder.y + DOWN_MARGIN
            )

            right_arm_down = (
                right_valid
                and right_wrist.y > right_shoulder.y + DOWN_MARGIN
            )

            # 팔을 올리면 준비 상태 저장
            if left_arm_up:
                self.ready_arm = "left"

            elif right_arm_up:
                self.ready_arm = "right"

            # 준비했던 팔이 내려오면 점프
            if self.ready_arm == "left" and left_arm_down and self.jump_cooldown <= 0:
                jump = True
                self.jump_cooldown = 0.12
                self.ready_arm = None

            elif self.ready_arm == "right" and right_arm_down and self.jump_cooldown <= 0:
                jump = True
                self.jump_cooldown = 0.12
                self.ready_arm = None

            if self.ready_arm is not None:
                self.camera_status = f"Ready: {self.ready_arm} arm"
            else:
                self.camera_status = "Arm down"

        else:
            # 여기서 ready_arm을 지우면 인식이 끊긴 순간 동작이 씹힘
            # 그래서 일부러 self.ready_arm = None 안 함
            self.camera_status = "No body detected"

        cv2.putText(
            frame,
            f"{self.name}  {self.camera_status}",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

        self.last_camera_frame = frame

        return jump

    def update(self, dt, jump_detected):
        if self.game_over:
            # 죽음 낙하 + 회전 애니메이션
            if self.bird_y < self.h + int(80 * self.scale):
                self.bird_velocity += self.gravity * dt
                self.bird_y += self.bird_velocity * dt
                self.death_spin_angle += self.death_spin_speed * dt

            if self.game_over_timer > 0:
                self.game_over_timer -= dt

                if self.game_over_timer < 0:
                    self.game_over_timer = 0

            return

        _, current_pipe_speed, current_spawn_interval, _ = self.get_difficulty_values()

        if jump_detected:
            self.bird_velocity = self.jump_power

        self.bird_velocity += self.gravity * dt
        self.bird_y += self.bird_velocity * dt

        self.distance += current_pipe_speed * dt / self.scale

        for pipe in self.pipes:
            pipe["x"] -= current_pipe_speed * dt

        self.pipes = [
            pipe for pipe in self.pipes
            if pipe["x"] + self.pipe_width > 0
        ]

        self.spawn_timer += dt

        if self.spawn_timer >= current_spawn_interval:
            self.spawn_pipe()
            self.spawn_timer = 0

        for pipe in self.pipes:
            if not pipe["passed"] and pipe["x"] + self.pipe_width < self.bird_x:
                pipe["passed"] = True
                self.score += 1

        if self.check_collision():
            self.game_over = True
            self.game_over_timer = self.game_over_freeze_time

            # 죽는 순간 살짝 튀어오른 뒤 낙하
            self.bird_velocity = -220 * self.scale
            self.death_spin_angle = 0.0

    def check_collision(self):
        bird_rect = pygame.Rect(
            self.bird_x - self.bird_radius,
            self.bird_y - self.bird_radius,
            self.bird_radius * 2,
            self.bird_radius * 2
        )

        if self.bird_y - self.bird_radius <= 0:
            return True

        if self.bird_y + self.bird_radius >= self.ground_y:
            return True

        for pipe in self.pipes:
            x = int(pipe["x"])
            gap_y = pipe["gap_y"]
            gap = pipe["gap"]

            top_rect = pygame.Rect(
                x,
                0,
                self.pipe_width,
                gap_y - gap // 2
            )

            bottom_rect = pygame.Rect(
                x,
                gap_y + gap // 2,
                self.pipe_width,
                self.ground_y - (gap_y + gap // 2)
            )

            if bird_rect.colliderect(top_rect) or bird_rect.colliderect(bottom_rect):
                return True

        return False

    def draw_cloud(self, surface, x, y, scale):
        color = (255, 255, 255)
        shadow = (220, 240, 245)

        parts = [
            (0, 15, 28),
            (28, 0, 36),
            (65, 15, 30),
            (35, 20, 38),
        ]

        for px, py, r in parts:
            pygame.draw.circle(
                surface,
                shadow,
                (int(x + px * scale), int(y + py * scale + 4 * scale)),
                int(r * scale)
            )

        for px, py, r in parts:
            pygame.draw.circle(
                surface,
                color,
                (int(x + px * scale), int(y + py * scale)),
                int(r * scale)
            )

    def draw_background(self, surface, dt):
        _, current_pipe_speed, _, _ = self.get_difficulty_values()

        motion_dt = 0 if self.game_over else dt

        # 플래피버드 에셋 배경 사용
        if self.flappy_background is not None and self.flappy_base is not None:
            surface.fill((78, 192, 202))

            bg_w = self.flappy_background.get_width()
            for x in range(0, self.w + bg_w, bg_w):
                surface.blit(self.flappy_background, (x, 0))

            base_w = self.flappy_base.get_width()
            self.ground_scroll = (
                self.ground_scroll + current_pipe_speed * motion_dt
            ) % base_w

            for x in range(-base_w, self.w + base_w, base_w):
                surface.blit(
                    self.flappy_base,
                    (x - int(self.ground_scroll), self.ground_y)
                )

            return

        # 폴백: 코드로 직접 그린 배경
        surface.fill((100, 205, 235))

        pygame.draw.circle(
            surface,
            (120, 220, 120),
            (int(100 * self.scale), self.ground_y + int(70 * self.scale)),
            int(180 * self.scale)
        )
        pygame.draw.circle(
            surface,
            (105, 205, 105),
            (int(360 * self.scale), self.ground_y + int(80 * self.scale)),
            int(210 * self.scale)
        )
        pygame.draw.circle(
            surface,
            (115, 215, 115),
            (int(650 * self.scale), self.ground_y + int(60 * self.scale)),
            int(190 * self.scale)
        )

        for cloud in self.clouds:
            cloud["x"] -= 25 * self.scale * motion_dt

            if cloud["x"] < -int(160 * self.scale):
                cloud["x"] = self.w + self.rng.randint(
                    int(40 * self.scale),
                    int(240 * self.scale)
                )
                cloud["y"] = self.rng.randint(
                    int(60 * self.scale),
                    int(180 * self.scale)
                )

            self.draw_cloud(surface, cloud["x"], cloud["y"], cloud["scale"])

        self.ground_scroll = (
            self.ground_scroll + current_pipe_speed * motion_dt
        ) % int(40 * self.scale)

        pygame.draw.rect(
            surface,
            (235, 210, 120),
            (0, self.ground_y, self.w, self.ground_height)
        )
        pygame.draw.rect(
            surface,
            (105, 205, 75),
            (0, self.ground_y, self.w, int(18 * self.scale))
        )

        step = int(40 * self.scale)

        for x in range(-step, self.w + step, step):
            sx = x - int(self.ground_scroll)

            pygame.draw.polygon(
                surface,
                (215, 185, 95),
                [
                    (sx, self.ground_y + int(35 * self.scale)),
                    (sx + int(20 * self.scale), self.ground_y + int(55 * self.scale)),
                    (sx + int(40 * self.scale), self.ground_y + int(35 * self.scale)),
                ]
            )

    def draw_pipe_rect(self, surface, rect):
        pygame.draw.rect(surface, (60, 190, 70), rect)

        pygame.draw.rect(
            surface,
            (35, 140, 55),
            (
                rect.right - int(18 * self.scale),
                rect.top,
                int(18 * self.scale),
                rect.height
            )
        )

        pygame.draw.rect(
            surface,
            (110, 235, 95),
            (
                rect.left + int(10 * self.scale),
                rect.top,
                int(12 * self.scale),
                rect.height
            )
        )

        pygame.draw.rect(
            surface,
            (20, 95, 35),
            rect,
            max(2, int(4 * self.scale))
        )

    def draw_pipe_cap(self, surface, x, y, width, height):
        cap_rect = pygame.Rect(x, y, width, height)

        pygame.draw.rect(surface, (70, 205, 75), cap_rect)

        pygame.draw.rect(
            surface,
            (35, 145, 55),
            (
                cap_rect.right - int(18 * self.scale),
                cap_rect.top,
                int(18 * self.scale),
                cap_rect.height
            )
        )

        pygame.draw.rect(
            surface,
            (130, 245, 105),
            (
                cap_rect.left + int(10 * self.scale),
                cap_rect.top + int(5 * self.scale),
                int(14 * self.scale),
                cap_rect.height - int(10 * self.scale)
            )
        )

        pygame.draw.rect(
            surface,
            (20, 95, 35),
            cap_rect,
            max(2, int(4 * self.scale))
        )

    def draw_pipes(self, surface):
        # 플래피버드 에셋 파이프 사용
        if self.flappy_pipe_body is not None and self.flappy_pipe_body_flipped is not None:
            pipe_h = self.flappy_pipe_body.get_height()

            for pipe in self.pipes:
                x = int(pipe["x"])
                gap_y = pipe["gap_y"]
                gap = pipe["gap"]

                top_bottom = gap_y - gap // 2
                bottom_top = gap_y + gap // 2

                surface.blit(self.flappy_pipe_body_flipped, (x, top_bottom - pipe_h))
                surface.blit(self.flappy_pipe_body, (x, bottom_top))

            return

        # 폴백: 코드로 직접 그린 파이프
        cap_height = int(30 * self.scale)
        cap_extra = int(18 * self.scale)

        for pipe in self.pipes:
            x = int(pipe["x"])
            gap_y = pipe["gap_y"]
            gap = pipe["gap"]

            top_bottom = gap_y - gap // 2
            bottom_top = gap_y + gap // 2

            top_body = pygame.Rect(
                x,
                0,
                self.pipe_width,
                top_bottom
            )

            bottom_body = pygame.Rect(
                x,
                bottom_top,
                self.pipe_width,
                self.ground_y - bottom_top
            )

            self.draw_pipe_rect(surface, top_body)
            self.draw_pipe_rect(surface, bottom_body)

            self.draw_pipe_cap(
                surface,
                x - cap_extra // 2,
                top_bottom - cap_height,
                self.pipe_width + cap_extra,
                cap_height
            )

            self.draw_pipe_cap(
                surface,
                x - cap_extra // 2,
                bottom_top,
                self.pipe_width + cap_extra,
                cap_height
            )

    def draw_bird(self, surface):
        if self.bird_y > self.h + int(60 * self.scale):
            return

        if self.game_over:
            angle = -self.death_spin_angle
        else:
            angle = max(-35, min(70, -self.bird_velocity * 0.08 / self.scale))

        # 플래피버드 에셋 새 + 날갯짓 애니메이션
        if self.flappy_bird_frames is not None:
            if self.game_over:
                frame = self.flappy_bird_frames[1]
            else:
                frame_seq = [0, 1, 2, 1]
                idx = int(self.bird_anim_time * self.bird_anim_speed) % len(frame_seq)
                frame = self.flappy_bird_frames[frame_seq[idx]]

            rotated = pygame.transform.rotate(frame, -angle)
            rect = rotated.get_rect(center=(self.bird_x, int(self.bird_y)))
            surface.blit(rotated, rect)
            return

        if self.bird_image_base is not None:
            rotated = pygame.transform.rotate(self.bird_image_base, angle)
            rect = rotated.get_rect(center=(self.bird_x, int(self.bird_y)))
            surface.blit(rotated, rect)
            return

        # 폴백: 코드로 직접 그린 새
        s = self.scale
        size = int(70 * s)

        bird_surf = pygame.Surface((size, size), pygame.SRCALPHA)
        cx, cy = size // 2, size // 2

        YELLOW = (253, 216, 53)
        YELLOW_DARK = (222, 173, 24)
        WHITE = (255, 255, 255)
        BELLY = (255, 245, 200)
        ORANGE = (247, 139, 41)
        ORANGE_DARK = (194, 87, 21)
        BLACK = (30, 30, 30)

        r_body = int(24 * s)

        body_rect = pygame.Rect(cx - r_body, cy - int(20 * s), r_body * 2, int(40 * s))
        pygame.draw.ellipse(bird_surf, YELLOW, body_rect)

        belly_rect = pygame.Rect(cx - int(14 * s), cy + int(0 * s), int(24 * s), int(18 * s))
        pygame.draw.ellipse(bird_surf, BELLY, belly_rect)

        pygame.draw.ellipse(bird_surf, BLACK, body_rect, max(2, int(2 * s)))

        wing_rect = pygame.Rect(cx - int(18 * s), cy - int(2 * s), int(20 * s), int(14 * s))
        pygame.draw.ellipse(bird_surf, YELLOW_DARK, wing_rect)
        pygame.draw.ellipse(bird_surf, BLACK, wing_rect, max(2, int(2 * s)))

        eye_center = (cx + int(9 * s), cy - int(9 * s))
        pygame.draw.circle(bird_surf, WHITE, eye_center, int(9 * s))
        pygame.draw.circle(bird_surf, BLACK, eye_center, int(9 * s), max(2, int(2 * s)))

        pygame.draw.circle(
            bird_surf,
            BLACK,
            (eye_center[0] + int(2 * s), eye_center[1]),
            int(4 * s)
        )
        pygame.draw.circle(
            bird_surf,
            WHITE,
            (eye_center[0] + int(3 * s), eye_center[1] - int(1 * s)),
            max(1, int(1.5 * s))
        )

        beak_top = [
            (cx + int(14 * s), cy - int(4 * s)),
            (cx + int(34 * s), cy - int(2 * s)),
            (cx + int(34 * s), cy + int(4 * s)),
            (cx + int(14 * s), cy + int(2 * s)),
        ]
        pygame.draw.polygon(bird_surf, ORANGE, beak_top)
        pygame.draw.polygon(bird_surf, BLACK, beak_top, max(2, int(2 * s)))

        beak_bottom = [
            (cx + int(14 * s), cy + int(2 * s)),
            (cx + int(34 * s), cy + int(4 * s)),
            (cx + int(32 * s), cy + int(10 * s)),
            (cx + int(14 * s), cy + int(8 * s)),
        ]
        pygame.draw.polygon(bird_surf, ORANGE_DARK, beak_bottom)
        pygame.draw.polygon(bird_surf, BLACK, beak_bottom, max(2, int(2 * s)))

        rotated = pygame.transform.rotate(bird_surf, angle)
        rect = rotated.get_rect(center=(self.bird_x, int(self.bird_y)))
        surface.blit(rotated, rect)

    def draw_outlined_text(self, surface, text, font_obj, x, y, main_color, outline_color):
        base = font_obj.render(text, True, main_color)
        outline = font_obj.render(text, True, outline_color)

        offset = max(2, int(3 * self.scale))

        for dx, dy in [
            (-offset, 0),
            (offset, 0),
            (0, -offset),
            (0, offset),
            (-offset, -offset),
            (offset, offset),
            (-offset, offset),
            (offset, -offset)
        ]:
            surface.blit(outline, (x + dx, y + dy))

        surface.blit(base, (x, y))

    def draw_camera_preview(self, surface):
        if self.last_camera_frame is None:
            return

        preview = cv2.resize(
            self.last_camera_frame,
            (self.cam_preview_w, self.cam_preview_h)
        )
        preview = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)

        camera_surface = pygame.surfarray.make_surface(preview.swapaxes(0, 1))

        x = self.w - self.cam_preview_w - self.cam_margin
        y = self.h - self.cam_preview_h - self.cam_margin

        border = pygame.Rect(
            x - int(6 * self.scale),
            y - int(6 * self.scale),
            self.cam_preview_w + int(12 * self.scale),
            self.cam_preview_h + int(12 * self.scale)
        )

        pygame.draw.rect(
            surface,
            (255, 245, 180),
            border,
            border_radius=int(12 * self.scale)
        )
        pygame.draw.rect(
            surface,
            (90, 60, 35),
            border,
            max(2, int(4 * self.scale)),
            border_radius=int(12 * self.scale)
        )

        surface.blit(camera_surface, (x, y))

    def draw_text(self, surface):
        _, _, _, difficulty_level = self.get_difficulty_values()

        name_text = self.small_font.render(
            f"{self.name}   Cam {self.camera_index}",
            True,
            (255, 255, 255)
        )
        surface.blit(name_text, (int(18 * self.scale), int(16 * self.scale)))

        # 점수 표시
        score_str = str(self.score)

        if self.flappy_numbers is not None:
            digits = [self.flappy_numbers[int(c)] for c in score_str]
            total_w = sum(d.get_width() for d in digits) + (len(digits) - 1) * int(4 * self.scale)

            cx = self.w // 2 - total_w // 2
            cy = int(38 * self.scale)

            for digit in digits:
                surface.blit(digit, (cx, cy))
                cx += digit.get_width() + int(4 * self.scale)

        else:
            score_img = self.font.render(score_str, True, (255, 255, 255))
            score_x = self.w // 2 - score_img.get_width() // 2

            self.draw_outlined_text(
                surface,
                score_str,
                self.font,
                score_x,
                int(38 * self.scale),
                (255, 255, 255),
                (60, 60, 60)
            )

        distance_text = self.tiny_font.render(
            f"Distance: {int(self.distance)}   Lv. {difficulty_level + 1}",
            True,
            (255, 255, 255)
        )
        surface.blit(
            distance_text,
            (int(18 * self.scale), int(52 * self.scale))
        )

        status_text = self.tiny_font.render(
            self.camera_status,
            True,
            (255, 255, 255)
        )

        status_x = self.w - self.cam_preview_w - self.cam_margin
        status_y = self.h - self.cam_preview_h - self.cam_margin - int(34 * self.scale)

        surface.blit(status_text, (status_x, status_y))

        # 개별 FINISHED 박스는 제거
        # 둘 다 끝났을 때 중앙 매치 결과만 표시

    def draw(self, dt):
        if not self.game_over:
            self.bird_anim_time += dt

        surface = pygame.Surface((self.w, self.h))

        self.draw_background(surface, dt)
        self.draw_pipes(surface)
        self.draw_bird(surface)
        self.draw_camera_preview(surface)
        self.draw_text(surface)

        screen.blit(surface, (self.panel_x, self.panel_y))


def cleanup_and_exit(players):
    for player in players:
        player.close()

    pygame.quit()
    sys.exit()


def draw_match_result(p1, p2):
    if not (p1.game_over and p2.game_over):
        return

    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 130))
    screen.blit(overlay, (0, 0))

    scale = min(WIDTH / 1600, HEIGHT / 900)

    title_font = pygame.font.SysFont("arial", int(80 * scale), bold=True)
    small_font = pygame.font.SysFont("arial", int(34 * scale), bold=True)

    if p1.distance > p2.distance + 1:
        winner = "P1 WINS"
    elif p2.distance > p1.distance + 1:
        winner = "P2 WINS"
    else:
        winner = "DRAW"

    # 승자 텍스트
    title_main = title_font.render(winner, True, (255, 240, 120))
    title_out = title_font.render(winner, True, (60, 40, 10))

    tx = WIDTH // 2 - title_main.get_width() // 2
    ty = HEIGHT // 2 - int(120 * scale)
    off = max(2, int(4 * scale))

    for dx, dy in [
        (-off, 0),
        (off, 0),
        (0, -off),
        (0, off)
    ]:
        screen.blit(title_out, (tx + dx, ty + dy))

    screen.blit(title_main, (tx, ty))

    result = small_font.render(
        f"P1 Distance: {int(p1.distance)}     P2 Distance: {int(p2.distance)}",
        True,
        (255, 255, 255)
    )
    screen.blit(
        result,
        (
            WIDTH // 2 - result.get_width() // 2,
            HEIGHT // 2 - int(30 * scale)
        )
    )

    if p1.game_over_timer > 0 or p2.game_over_timer > 0:
        wait_time = max(p1.game_over_timer, p2.game_over_timer)
        restart_message = f"Wait {wait_time:.1f}s"
    else:
        restart_message = "Raise arm then lower it, or press R to restart"

    restart = small_font.render(
        restart_message,
        True,
        (255, 255, 255)
    )
    screen.blit(
        restart,
        (
            WIDTH // 2 - restart.get_width() // 2,
            HEIGHT // 2 + int(35 * scale)
        )
    )


# =====================
# 플레이어 생성
# =====================
player = PlayerGame("1P", P1_CAMERA_INDEX, 0, seed=12345, bird_color=P1_BIRD_COLOR)

players = [player]


def freeze_player_for_start(player):
    """
    READY 상태에서 새/파이프/배경이 움직이지 않도록 고정한다.
    """
    player.bird_y = player.h // 2
    player.bird_velocity = 0
    player.spawn_timer = 0
    player.death_spin_angle = 0.0


def draw_single_game_over_result(player):
    """
    1인용 게임오버 화면.
    죽은 뒤 자동 재시작하지 않고, R 키를 누를 때까지 점수와 거리를 계속 보여준다.
    """
    if not player.game_over:
        return

    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 140))
    screen.blit(overlay, (0, 0))

    scale = min(WIDTH / 1600, HEIGHT / 900)

    title_font = pygame.font.SysFont("arial", int(90 * scale), bold=True)
    score_font = pygame.font.SysFont("arial", int(46 * scale), bold=True)
    small_font = pygame.font.SysFont("arial", int(34 * scale), bold=True)

    title = "GAME OVER"
    title_main = title_font.render(title, True, (255, 240, 120))
    title_out = title_font.render(title, True, (60, 40, 10))

    tx = WIDTH // 2 - title_main.get_width() // 2
    ty = HEIGHT // 2 - int(170 * scale)
    off = max(2, int(4 * scale))

    for dx, dy in [
        (-off, 0),
        (off, 0),
        (0, -off),
        (0, off),
        (-off, -off),
        (off, off),
        (-off, off),
        (off, -off),
    ]:
        screen.blit(title_out, (tx + dx, ty + dy))

    screen.blit(title_main, (tx, ty))

    score_text = score_font.render(
        f"Score: {player.score}     Distance: {int(player.distance)}",
        True,
        (255, 255, 255)
    )
    screen.blit(
        score_text,
        (
            WIDTH // 2 - score_text.get_width() // 2,
            HEIGHT // 2 - int(45 * scale)
        )
    )

    restart_text = small_font.render(
        "Press R, then flap with webcam to restart",
        True,
        (255, 255, 255)
    )
    screen.blit(
        restart_text,
        (
            WIDTH // 2 - restart_text.get_width() // 2,
            HEIGHT // 2 + int(35 * scale)
        )
    )

    exit_text = small_font.render(
        "Press ESC to quit",
        True,
        (230, 230, 230)
    )
    screen.blit(
        exit_text,
        (
            WIDTH // 2 - exit_text.get_width() // 2,
            HEIGHT // 2 + int(85 * scale)
        )
    )


def draw_ready_to_start(ready_delay):
    """
    시작 대기 화면.
    R을 누른 직후 바로 시작되는 문제를 막기 위해 짧은 잠금 시간을 둔다.
    이후 웹캠으로 팔을 올렸다가 내리는 동작이 감지되어야 시작한다.
    """
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 115))
    screen.blit(overlay, (0, 0))

    scale = min(WIDTH / 1600, HEIGHT / 900)

    title_font = pygame.font.SysFont("arial", int(86 * scale), bold=True)
    small_font = pygame.font.SysFont("arial", int(36 * scale), bold=True)
    tiny_font = pygame.font.SysFont("arial", int(28 * scale), bold=True)

    title = "READY"
    title_main = title_font.render(title, True, (255, 240, 120))
    title_out = title_font.render(title, True, (60, 40, 10))

    tx = WIDTH // 2 - title_main.get_width() // 2
    ty = HEIGHT // 2 - int(150 * scale)
    off = max(2, int(4 * scale))

    for dx, dy in [
        (-off, 0),
        (off, 0),
        (0, -off),
        (0, off),
        (-off, -off),
        (off, off),
        (-off, off),
        (off, -off),
    ]:
        screen.blit(title_out, (tx + dx, ty + dy))

    screen.blit(title_main, (tx, ty))

    if ready_delay > 0:
        main_message = "Get ready..."
    else:
        main_message = "Raise your arm, then lower it to start"

    msg1 = small_font.render(
        main_message,
        True,
        (255, 255, 255)
    )
    screen.blit(
        msg1,
        (
            WIDTH // 2 - msg1.get_width() // 2,
            HEIGHT // 2 - int(25 * scale)
        )
    )

    msg2 = tiny_font.render(
        "Gameplay uses webcam only",
        True,
        (230, 230, 230)
    )
    screen.blit(
        msg2,
        (
            WIDTH // 2 - msg2.get_width() // 2,
            HEIGHT // 2 + int(35 * scale)
        )
    )


# =====================
# 게임 루프
# =====================
# 처음 실행할 때도 바로 시작하지 않고 웹캠 날갯짓으로 시작
waiting_to_start = True

# R을 누른 직후, 이전 동작 인식값 때문에 바로 시작되는 문제를 막는 잠금 시간
ready_start_delay = 0.6
READY_DELAY_AFTER_RESET = 0.6

# 첫 시작 전 화면을 고정
freeze_player_for_start(player)

while True:
    dt = clock.tick(60) / 1000

    # 웹캠 동작은 항상 읽어서 카메라 미리보기와 팔 상태를 갱신한다.
    jump_detected = player.detect_body_jump(dt)
    restart_pressed = False

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            cleanup_and_exit(players)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                cleanup_and_exit(players)

            # 점프 조작은 웹캠 팔 동작만 사용한다.
            # A/SPACE 같은 키보드 점프는 사용하지 않는다.

            # 게임오버 상태에서 R을 누르면 READY 상태로만 이동한다.
            # R을 누른 순간에는 절대 바로 시작하지 않는다.
            if player.game_over and event.key == pygame.K_r:
                restart_pressed = True

            # READY 상태에서 R을 누르면 대기 상태를 다시 초기화한다.
            if waiting_to_start and event.key == pygame.K_r:
                restart_pressed = True

    if restart_pressed:
        player.reset()
        freeze_player_for_start(player)

        # 이전 프레임에서 감지된 팔 동작이 남아 바로 시작되는 것을 막는다.
        player.ready_arm = None
        player.jump_cooldown = 0
        jump_detected = False

        waiting_to_start = True
        ready_start_delay = READY_DELAY_AFTER_RESET

    elif waiting_to_start:
        freeze_player_for_start(player)

        if ready_start_delay > 0:
            ready_start_delay -= dt

            # 잠금 시간 동안에는 감지된 점프를 무조건 버린다.
            player.ready_arm = None
            jump_detected = False

        else:
            # 잠금 시간이 끝난 뒤 새로 팔을 올렸다가 내려야 시작한다.
            if jump_detected:
                waiting_to_start = False
                player.update(dt, True)

    else:
        if player.game_over:
            # 죽은 뒤에는 새가 떨어지는 연출과 점수 화면만 유지.
            # 팔 동작으로는 재시작하지 않는다.
            player.update(dt, False)
        else:
            player.update(dt, jump_detected)

    if waiting_to_start:
        player.draw(0)
        draw_ready_to_start(ready_start_delay)
    else:
        player.draw(dt)
        draw_single_game_over_result(player)

    pygame.display.update()