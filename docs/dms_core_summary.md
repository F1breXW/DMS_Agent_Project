# DMS 核心代码摘要（source_code）

## 1) 总体流程（离线视频与实时摄像头）
- 离线视频主流程：读取视频帧 -> 人脸检测与裁剪 -> 眼口状态检测 -> 疲劳/分心判定 -> 输出指标与告警信息。
- 实时摄像头主流程：读取摄像头帧 -> 人脸检测与疲劳评估 -> YOLO 多线程检测手机/吸烟 -> 语音告警与状态输出。

## 2) 关键模块职责
- 人脸检测：RetinaFace 负责检测人脸并裁剪出人脸区域，作为后续眼口检测与注视区域判断的输入。
- 眼口状态：基于 dlib 关键点计算眼睛闭合比例与打哈欠比例，为疲劳判定提供信号。
- 视线/注视：ShuffleNetV2 输出注视区域类别（gaze zone），用于分心判断。
- 状态与阈值：State 中包含疲劳/分心判定的核心时间窗与阈值逻辑。
- 车内违规检测：YOLO 多线程检测打电话/吸烟，触发语音告警。

## 3) 核心阈值与时间窗（来自 State）
- 分心监测：
  - focusfront_len = 2s（要求持续专注前方）
  - longdis_len = 2s（长期分心）
  - shortdis_len = 8s（短时分心）
  - 相关比例阈值：focusfront_rates=0.75, longdis_rates=0.90, shortdis_rates=0.33
- 疲劳监测：
  - fat_len = 2s
  - fat_rate_l1 = 0.20, fat_rate_l2 = 0.35
  - yawn_len = 1.0s, yawn_rate = 0.30
  - eye_open_thres = 0.18, yawn_thres = 0.45

## 4) 主要输入与输出
- 输入：视频文件或摄像头帧；模型权重与配置（RetinaFace、gaze 模型、YOLO）。
- 输出：疲劳等级/分数、分心状态/分数、打电话与吸烟检测结果、语音告警。

## 5) 重点文件清单（优先阅读）
- 离线视频主流程：data/source_code/process_video.py
- 实时摄像头主流程：data/source_code/best2.py
- 状态判定逻辑：data/source_code/state.py
- 眼口特征提取：data/source_code/extract_eye.py
- 人脸检测与裁剪：data/source_code/models/retinaface.py
- 注视区域模型：data/source_code/models/shufflenet_v2.py

## 6) 辅助与训练相关
- utils/* 与 models/utils/* 多为训练或预处理辅助，不是 DMS 业务主线，但用于模型细节定位。
- save_image.py 仅用于保存视频首帧，属于工具脚本。
