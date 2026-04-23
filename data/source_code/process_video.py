import cv2
import os
import torch
import argparse
import dlib
import sys
from models.retinaface import Retinaface
from models.mtcnn import MTCNN
from extract_eye import detectEyeAndMouthState
from state import State
from nets import mobilenetv2
from models.shufflenet_v2 import ShuffleNetV2
sys.path.append('/E:/DMS/detect/models')



def display(video_resolution, resize_resolution, bbox, img_array, fat_level, is_longdis, is_shortdis, save, out, dist_score, fat_score):
    # 只输出数据，不显示视频
    print(f"疲劳等级: {fat_level}")
    print(f"疲劳分数: {fat_score:.2f}")
    print(f"分心分数: {dist_score:.2f}")
    print(f"短时分心: {is_shortdis}")
    print(f"长时分心: {is_longdis}")
    print("-" * 50)


def main(args):
    #准备数据
    video_path = args.video_path
    if not os.path.exists(video_path):
        raise ValueError(f"视频文件不存在: {video_path}")
        
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
        raise ValueError(f"无法打开视频文件: {video_path}")
        
    # 获取视频的原始分辨率
    video_resolution = (int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)), 
                       int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)))
    resize_resolution = (224,224)

    #准备模型
    #face_detector = MTCNN()
    eye_predictor = dlib.shape_predictor("./assets/shape_predictor_face_landmarks.dat")
    retinaface = Retinaface(cuda=False)  # 设置为使用CPU
    gazenet = ShuffleNetV2(9,0.50)  # 移除.cuda()
    gazenet.load_state_dict(torch.load(args.gazenet_path, map_location='cpu', weights_only=True))  # 添加weights_only=True
    gazenet = gazenet.eval()  # 设置评估模式

    #检查帧读取
    ref, frame = capture.read()
    if not ref:
        raise ValueError("未能正确读取视频文件")

    #开始读取
    state = State(fps=capture.get(cv2.CAP_PROP_FPS))
    state.start()
    is_longdis, is_shortdis = False,False
    print("开始处理视频...")
    while(True):
        state.nextFrame()
        # 读取某一帧
        ref, frame = capture.read()
        if not ref:
            print("视频处理完成")
            break
        # 格式转变，BGR to RGB to Tensor
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame_tensor = torch.from_numpy(frame).permute(2,0,1).to(torch.float32).unsqueeze(0)  # 移除.cuda()

        #提取人脸检测注视区域
        resizeframe = torch.nn.functional.interpolate(frame_tensor, size=resize_resolution, mode='bilinear', align_corners=False)
        face_frame, bbox = retinaface.detect_faces_and_crop_batch(resizeframe)
        if face_frame is None:
            print("未检测到人脸")
            continue

        gaze_zone = gazenet(resizeframe/255.)

        #提取人眼检测开闭
        eye_open_ratio, mouth_open_ratio = detectEyeAndMouthState(face_frame,eye_predictor)
        #判断疲劳等级
        fat_level, fat_score = state.fat_judge(eye_open_ratio, mouth_open_ratio)
        #判断分心等级
        is_longdis, is_shortdis, long_score, short_score = state.distract_judge(gaze_zone,is_longdis,is_shortdis)

        #输出数据
        display(video_resolution,resize_resolution,bbox, frame,fat_level,is_longdis,is_shortdis,args.save,None,
                max([long_score,short_score]), min([fat_score,1.0]))
            
    capture.release()
    print("程序结束")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Training script')
    parser.add_argument(
        '--video_path', type=str, default='./tests/test2.mp4',
        help='path to the video'
    )
    parser.add_argument(
        '--gazenet_path', type=str, default='./assets/gaze.pth',
        help='path to the gazenet'
    )
    parser.add_argument(
        '--output_video_file', type=str, default='./saves/',
        help='path to the gazenet'
    )
    parser.add_argument('--pfld_onnx_model', default="./assets/PFLD_112_1_opt_sim.onnx", type=str)
    parser.add_argument('--save', default=False, type=bool)
    args = parser.parse_args()
    main(args)