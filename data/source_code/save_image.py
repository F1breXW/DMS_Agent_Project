import cv2

def extract_first_frame(video_path, save_path):
    # 打开视频文件
    video_capture = cv2.VideoCapture(video_path)

    # 读取第一帧
    success, frame = video_capture.read()

    if success:
        # 保存第一帧为图像文件
        cv2.imwrite(save_path, frame)
        print("第一帧已保存为:", save_path)
    else:
        print("无法读取视频文件或视频为空")

    # 释放视频流
    video_capture.release()

# 视频文件路径
video_path = "./tests/test1.mp4"
# 保存第一帧图像的路径
save_path = "./saves/img1.png"

# 调用函数提取第一帧并保存
extract_first_frame(video_path, save_path)