import torch
import numpy as np
import queue

class State():
    def __init__(self,fps):
        self.fps = fps
        #分心数据
        self.zones = 10 #不改
        self.focusfront_rates = 0.75
        self.longdis_rates = 0.90
        self.shortdis_rates = 0.33
        self.focusfront_len = 2 #2s是否一直注意前方
        self.longdis_len = 2 #3s监测长分心
        self.shortdis_len = 8 #10s监测短分心
        self.focusfront_frames = int(self.focusfront_len * self.focusfront_rates * self.fps)
        self.shortdis_frames = int(self.shortdis_len * self.shortdis_rates * self.fps)
        self.longdis_frames = int(self.longdis_len * self.longdis_rates * self.fps)

        #疲劳数据
        self.fat_len = 2
        self.fat_rate_l1 = 0.20
        self.fat_rate_l2 = 0.35
        self.yawn_len = 3.0
        self.yawn_rate = 0.30
        self.eye_open_thres = 0.18
        self.yawn_thres = 0.45

        self.fat_l1_frames = self.fat_len * self.fat_rate_l1 * self.fps
        self.fat_l2_frames = self.fat_len * self.fat_rate_l2 * self.fps
        self.fat_yawn_frames = self.yawn_len * self.yawn_rate * self.fps

        # 头部姿态异常阈值（国标要求）
        self.head_pitch_down = -30.0   # 低头超过 30°
        self.head_pitch_up = 30.0      # 抬头超过 30°
        self.head_yaw_limit = 45.0     # 左/右转头超过 45°
        self.head_pose_duration = 2.0  # 异常持续 2s 触发告警
        self.head_pose_frames = int(self.head_pose_duration * self.fps)

    def dis_start(self):
        self.dis_queue = queue.Queue(int(self.fps*self.shortdis_len))
        self.longdis_point = int(self.fps*self.longdis_len)
        self.focusfront_point = int(self.fps*self.focusfront_len)
        self.zone_counts = np.zeros(self.zones)
        self.longzone_counts = np.zeros(self.zones)
        self.focuszone_counts = np.zeros(self.zones)

    def eye_start(self):
        self.eye_queue = queue.Queue(self.fat_len*self.fps)
        self.yawn_queue = queue.Queue(self.yawn_len*self.fps)
        self.close_counts = 0
        self.yawn_counts = 0
        self.last_mouth_open_ratio = 0
        self.head_abnormal_count = 0

    def start(self):
        self.timestamp = 0
        self.dis_start()
        self.eye_start()

    def nextFrame(self):
        self.timestamp += 1

    def fat_judge(self,eye_open_ratio, mouth_open_ratio):
        is_eye_close = eye_open_ratio<self.eye_open_thres
        if self.eye_queue.full():
            pop_state = self.eye_queue.get()
            self.close_counts -= int(pop_state)
        self.eye_queue.put(is_eye_close)
        self.close_counts += int(is_eye_close)
        if self.close_counts >= self.fat_l2_frames:
            fat_level = 2
        elif self.close_counts >= self.fat_l1_frames:
            fat_level = 1
        else:
            fat_level = 0

        is_yawn = mouth_open_ratio>self.yawn_thres
        if self.yawn_queue.full():
            pop_state = self.yawn_queue.get()
            self.yawn_counts -= int(pop_state)
        self.yawn_queue.put(is_yawn)
        self.yawn_counts += int(is_yawn)
        if self.yawn_counts >= self.fat_yawn_frames:
            return 2, 1.0
        return fat_level, self.close_counts/self.fat_l2_frames

    def distract_judge(self,gaze_zone,is_longdis,is_shortdis):
        gaze_zone = torch.max(gaze_zone,1)[1].item()
        #弹出
            # 计数专注检测区间
        if len(self.dis_queue.queue) > self.focusfront_point:
            focuspop_zone = self.dis_queue.queue[-self.focusfront_point]
            self.focuszone_counts[focuspop_zone] -= 1
            # 计数长分心检测区间
        if len(self.dis_queue.queue) > self.longdis_point:
            longpop_zone = self.dis_queue.queue[-self.longdis_point]
            self.longzone_counts[longpop_zone] -= 1
            #计数短分心检测区间
        if self.dis_queue.full():
            pop_zone = self.dis_queue.get()
            self.zone_counts[pop_zone] -= 1
        #压入
        self.focuszone_counts[gaze_zone] += 1
        self.zone_counts[gaze_zone] += 1
        self.longzone_counts[gaze_zone] += 1
        self.dis_queue.put(gaze_zone)

        #回正判断：若之前有长期或短期分心，则必须回正2s,否则继续视为分心
        if is_longdis or is_shortdis:
            if self.focuszone_counts[1] + self.focuszone_counts[5] >= self.focusfront_frames:
                self.dis_start()
                return False, False,0,0
            else:
                return is_longdis,is_shortdis,1.0,1.0

        #分心判断
            #专注判断,若过去一段时间内持续专注看向前方，则重置分心判断任务
        if self.focuszone_counts[1] + self.focuszone_counts[5] >= self.focusfront_frames:
            self.dis_start()
            return False,False,0,0

            #长期分心判断
        long_score = 0
        is_longdis = False
        for i in range(self.zones):
            if i==1 or i==5:
                continue
            else:
                if self.longzone_counts[i]/self.longdis_frames>long_score:
                    long_score = self.longzone_counts[i]/self.longdis_frames
            if self.longzone_counts[i] >= self.longdis_frames:
                is_longdis = True



            #短期分心判断
        short_score = 0
        is_shortdis = False
        if self.dis_queue.full():
            short_score = max([self.longzone_counts[0]/self.shortdis_frames,self.longzone_counts[2]/self.shortdis_frames,
                               self.longzone_counts[3]/self.shortdis_frames,self.longzone_counts[8]/self.shortdis_frames,
                               (self.longzone_counts[4] + self.longzone_counts[6] + self.longzone_counts[7] + self.longzone_counts[9])/self.shortdis_frames])
            if self.longzone_counts[0] > self.shortdis_frames or\
                self.longzone_counts[2] > self.shortdis_frames or\
                self.longzone_counts[3] > self.shortdis_frames or \
                self.longzone_counts[8] > self.shortdis_frames:
                is_shortdis = True
            if self.longzone_counts[4] + self.longzone_counts[6] + self.longzone_counts[7] + self.longzone_counts[9] > self.shortdis_frames:
                is_shortdis = True
        return is_longdis,is_shortdis,long_score,short_score

    def head_pose_judge(self, pitch, yaw, roll):
        """判定头部姿态是否异常。
        返回 (is_abnormal: bool, reason: str, score: float)"""
        if pitch is None or yaw is None or roll is None:
            return False, "无法计算", 0.0

        reasons = []
        score = 0.0

        if pitch < self.head_pitch_down:
            reasons.append(f"低头({pitch:.0f}°)")
            score = max(score, abs(pitch / self.head_pitch_down))
        elif pitch > self.head_pitch_up:
            reasons.append(f"抬头({pitch:.0f}°)")
            score = max(score, abs(pitch / self.head_pitch_up))

        if abs(yaw) > self.head_yaw_limit:
            direction = "右转" if yaw > 0 else "左转"
            reasons.append(f"{direction}({yaw:.0f}°)")
            score = max(score, abs(yaw / self.head_yaw_limit))

        if reasons:
            self.head_abnormal_count += 1
            if self.head_abnormal_count >= self.head_pose_frames:
                return True, ", ".join(reasons), min(score, 1.0)
        else:
            self.head_abnormal_count = 0

        return False, "", 0.0





