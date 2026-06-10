import dlib
import numpy as np
import math
import time
import cv2
import dlib

def euclidean_distance(point1, point2):
    x1, y1 = point1
    x2, y2 = point2
    distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
    return distance


def detectEyeAndMouthState(img, predictor):
    close_thres = 0.19
    mouth_thres = 0.65
    im = img[0].permute(1,2,0).cpu().numpy().astype('uint8')
    rect = dlib.rectangle(left=1, top=1, right=img.shape[3]-1, bottom=img.shape[2]-1)
    landmarks = np.matrix([[p.x, p.y] for p in predictor(im, rect).parts()])
    '''
    shape = predictor(im, rect)
    win = dlib.image_window()
    win.clear_overlay()
    win.set_image(im)
    win.add_overlay(shape)
    dlib.hit_enter_to_continue()
    '''
    p41 = (landmarks.item(41,0),landmarks.item(41,1))
    p37 = (landmarks.item(37,0),landmarks.item(37,1))
    p40 = (landmarks.item(40, 0), landmarks.item(40, 1))
    p38 = (landmarks.item(38, 0), landmarks.item(38, 1))
    p39 = (landmarks.item(39, 0), landmarks.item(39, 1))
    p36 = (landmarks.item(36, 0), landmarks.item(36, 1))
    p47 = (landmarks.item(47, 0), landmarks.item(47, 1))
    p46 = (landmarks.item(46, 0), landmarks.item(46, 1))
    p43 = (landmarks.item(43, 0), landmarks.item(43, 1))
    p44 = (landmarks.item(44, 0), landmarks.item(44, 1))
    p45 = (landmarks.item(45, 0), landmarks.item(45, 1))
    p42 = (landmarks.item(42, 0), landmarks.item(42, 1))
    #for mouth
    p48 = (landmarks.item(48, 0), landmarks.item(48, 1))
    p54 = (landmarks.item(54, 0), landmarks.item(54, 1))
    p57 = (landmarks.item(57, 0), landmarks.item(57, 1))
    p51 = (landmarks.item(51, 0), landmarks.item(51, 1))

    righteye_openratio = (euclidean_distance(p41,p37)+euclidean_distance(p40,p38)) / (
                euclidean_distance(p39,p36)) / 2
    lefteye_openratio = (euclidean_distance(p46,p44)+euclidean_distance(p47,p43)) / (
                euclidean_distance(p45,p42)) / 2
    mouth_openratio = (euclidean_distance(p57,p51)) / (
                euclidean_distance(p54,p48)) / 2
    print("%.2f %.2f"%(righteye_openratio,lefteye_openratio),end=' ')
    print("%.2f"%(mouth_openratio),end=' ')
    return (righteye_openratio+lefteye_openratio)/2, mouth_openratio


# 3D 参考点（通用人脸模型，单位 mm）
_HEAD_POSE_3D = np.array([
    (0.0, 0.0, 0.0),         # 鼻尖 (30)
    (0.0, -330.0, -65.0),    # 下巴 (8)
    (-225.0, 170.0, -135.0), # 左眼左角 (36)
    (225.0, 170.0, -135.0),  # 右眼右角 (45)
    (-150.0, -150.0, -125.0),# 左嘴角 (48)
    (150.0, -150.0, -125.0)  # 右嘴角 (54)
], dtype=np.float64)

def detectHeadPose(img, predictor):
    """基于 dlib 68 关键点 + solvePnP 计算头部姿态。
    返回 (pitch, yaw, roll) 单位：度。
    pitch > 0 抬头, yaw > 0 右转, roll > 0 右偏。
    若计算失败返回 None。"""
    im = img[0].permute(1, 2, 0).cpu().numpy().astype('uint8')
    h, w = im.shape[:2]
    rect = dlib.rectangle(left=1, top=1, right=w-1, bottom=h-1)
    landmarks = np.matrix([[p.x, p.y] for p in predictor(im, rect).parts()])

    # 2D 关键点
    image_points = np.array([
        (landmarks.item(30, 0), landmarks.item(30, 1)),  # 鼻尖
        (landmarks.item(8, 0),  landmarks.item(8, 1)),   # 下巴
        (landmarks.item(36, 0), landmarks.item(36, 1)),  # 左眼左角
        (landmarks.item(45, 0), landmarks.item(45, 1)),  # 右眼右角
        (landmarks.item(48, 0), landmarks.item(48, 1)),  # 左嘴角
        (landmarks.item(54, 0), landmarks.item(54, 1)),  # 右嘴角
    ], dtype=np.float64)

    focal = w
    center = (w / 2.0, h / 2.0)
    camera_matrix = np.array([
        [focal, 0, center[0]],
        [0, focal, center[1]],
        [0, 0, 1]
    ], dtype=np.float64)
    dist_coeffs = np.zeros((4, 1))

    success, rotation_vec, _ = cv2.solvePnP(
        _HEAD_POSE_3D, image_points, camera_matrix, dist_coeffs
    )
    if not success:
        return None

    rot_mat, _ = cv2.Rodrigues(rotation_vec)
    proj_mat = np.hstack((rot_mat, np.zeros((3, 1), dtype=np.float64)))
    _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(proj_mat)

    pitch = euler_angles[0][0]  # X 轴
    yaw   = euler_angles[1][0]  # Y 轴
    roll  = euler_angles[2][0]  # Z 轴

    return pitch, yaw, roll



