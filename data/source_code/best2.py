import cv2
import os
import torch
import dlib
import sys
import pygame
import time
import threading
from models.retinaface import Retinaface
from extract_eye import detectEyeAndMouthState
from state import State
from ultralytics import YOLO

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# 配置参数
YOLO_INTERVAL = 0.1
CHECK_INTERVAL = 5
WARN_INTERVAL = 5
FATIGUE_TRIGGER_COUNT = 3

# 全局状态变量
last_check_time = 0
last_phone_warn_time = 0
last_smoke_warn_time = 0
fatigue_buffer = 0
phone_detected = False
smoke_detected = False
stop_threads = False
yolo_frame = None
yolo_lock = threading.Lock()

def detect_yolo_objects(model, frame):
    resized = cv2.resize(frame, (320, 320))  # 平衡速度与精度
    results = model(resized, imgsz=320, verbose=False)
    return any(float(box.conf[0]) > 0.65 for box in results[0].boxes)

def phone_worker(model):
    global phone_detected, yolo_frame, stop_threads
    while not stop_threads:
        with yolo_lock:
            frame = yolo_frame.copy() if yolo_frame is not None else None
        if frame is not None:
            phone_detected = detect_yolo_objects(model, frame)
        time.sleep(YOLO_INTERVAL)

def smoke_worker(model):
    global smoke_detected, yolo_frame, stop_threads
    while not stop_threads:
        with yolo_lock:
            frame = yolo_frame.copy() if yolo_frame is not None else None
        if frame is not None:
            smoke_detected = detect_yolo_objects(model, frame)
        time.sleep(YOLO_INTERVAL)

def play_warning_sound(filename):
    if pygame.mixer.music.get_busy():
        pygame.mixer.music.stop()
    pygame.mixer.music.load(filename)
    pygame.mixer.music.play()

def display(is_fatigue, fat_score, phone, smoke):
    global last_check_time, last_phone_warn_time, last_smoke_warn_time
    now = time.time()

    if now - last_check_time >= CHECK_INTERVAL and is_fatigue:
        last_check_time = now
        print("\n【疲劳警告】检测到连续疲劳，请注意休息！")
        play_warning_sound(resource_path("severefatigue.mp3"))

    print("状态:", "疲劳" if is_fatigue else "正常")

    if phone:
        print("⚠ 检测到打电话")
        if now - last_phone_warn_time >= WARN_INTERVAL:
            play_warning_sound(resource_path("NoPhone.mp3"))
            last_phone_warn_time = now

    if smoke:
        print("⚠ 检测到吸烟")
        if now - last_smoke_warn_time >= WARN_INTERVAL:
            play_warning_sound(resource_path("NoSmoking.mp3"))
            last_smoke_warn_time = now

    print(f"疲劳分数: {fat_score:.2f}")
    print("-" * 30)

def main():
    global yolo_frame, stop_threads, fatigue_buffer

    pygame.mixer.init()
    capture = cv2.VideoCapture(0)
    if not capture.isOpened():
        raise ValueError("无法打开摄像头")

    resize_resolution = (224, 224)
    retinaface = Retinaface(cuda=False)
    eye_predictor = dlib.shape_predictor(resource_path("assets/shape_predictor_face_landmarks.dat"))
    phone_model = YOLO(resource_path("assets/phone_best.pt"))
    smoke_model = YOLO(resource_path("assets/cigarette_best.pt"))

    phone_thread = threading.Thread(target=phone_worker, args=(phone_model,))
    smoke_thread = threading.Thread(target=smoke_worker, args=(smoke_model,))
    phone_thread.start()
    smoke_thread.start()

    state = State(fps=5.0)
    state.start()

    print("开始处理摄像头画面...")
    while True:
        state.nextFrame()
        ret, frame = capture.read()
        if not ret:
            print("无法获取摄像头画面")
            break

        # 提供帧给 YOLO 子线程
        with yolo_lock:
            yolo_frame = frame.copy()
            current_phone = phone_detected
            current_smoke = smoke_detected

        # RetinaFace + 疲劳检测
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_tensor = torch.from_numpy(rgb).permute(2, 0, 1).float().unsqueeze(0)
        resized_tensor = torch.nn.functional.interpolate(frame_tensor, size=resize_resolution, mode='bilinear', align_corners=False)

        face_frame, bbox = retinaface.detect_faces_and_crop_batch(resized_tensor)
        if face_frame is None:
            print("未检测到人脸")
            continue

        _, fat_score = state.fat_judge(*detectEyeAndMouthState(face_frame, eye_predictor))

        if fat_score >= 1.0:
            fatigue_buffer += 1
        else:
            fatigue_buffer = 0

        is_fatigue = fatigue_buffer >= FATIGUE_TRIGGER_COUNT
        display(is_fatigue, fat_score, current_phone, current_smoke)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    stop_threads = True
    phone_thread.join()
    smoke_thread.join()
    capture.release()
    cv2.destroyAllWindows()
    print("程序结束")

if __name__ == '__main__':
    main()
