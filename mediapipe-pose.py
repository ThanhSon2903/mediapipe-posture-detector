import cv2
import mediapipe as mp
import math
import logging as logg
import time
import winsound
import requests
from collections import deque

front_cam = cv2.VideoCapture(0)
side_cam = cv2.VideoCapture(1)

#Initalize Mediapipe-pose
mpPose = mp.solutions.pose #lấy module Pose từ MediaPipe
pose_front = mpPose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
pose_side = mpPose.Pose(min_detection_confidence=0.5, min_tracking_confidence=0.5)
mpDraw = mp.solutions.drawing_utils #Khởi tạo lớp vẽ của Mediapipe

last_alert = 0
alert_sent = False


list = []
shouder_history = deque(maxlen = 15) #Luu toi da 15 phan tu
torso_history = deque(maxlen = 15)
neck_history = deque(maxlen = 15)


last_sent_status = None
status_start_time = None # Timer cho STATUS_DELAY (gửi snapshot)
bad_start_time = None # Timer riêng cho ALERT_DELAY (beep/alert)
STATUS_DELAY = 5
WARNING_DELAY = 6
BAD_DELAY = 7
ALERT_DELAY = 30
token  = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0aGFuaG5ndXllbnNvbmpxa0BnbWFpbC5jb20iLCJyb2xlIjoiVVNFUiIsImlhdCI6MTc4MjEzMDM3MSwiZXhwIjoxNzgyMTMxMjcxfQ.8K0qSObiZcAl0vnsR93ufFwiA1-EWDU-UeveHEdBAvk"
SESSION_ID = 4



def make_lm_timestaps(res): #Chứa toạ độ các điểm trên khung xương
    lm_list = []
    id = 0
    for lm in res.pose_landmarks.landmark:
        lm_list.append(f"idx:{id},x:{lm.x},y:{lm.y},z:{lm.z}")
        id+=1
    return lm_list 

# def draw_lm_on_img(mpDraw,res,frame):
#     mpDraw.draw_landmarks(frame,res.pose_landmarks,mpPose.POSE_CONNECTIONS) #Vẽ các đường nối
#     id = 0
#     #Vẽ các điểm nút
#     for lm in res.pose_landmarks.landmark:
#         h,w,c = frame.shape
#         # print(id,lm)
#         id+=1
#         cx,cy = int(lm.x * w),int(lm.y * h)
#         cv2.circle(frame,(cx,cy),5,(0,255,0),cv2.FILLED)
#     return frame

def is_visibility(lm1,lm2):
    return lm1.visibility > 0.5 and lm2.visibility > 0.5


#Kiem tra ngồi lệch vai
def compare_Diff_Shoulder(res,frame):
    if not res.pose_landmarks:
        logg.error("Not found skeleton!")
        return None;
    lm = res.pose_landmarks.landmark
    h,w,c = frame.shape

    if not is_visibility(lm[11],lm[12]):
        return None

    left_shoulder_x,left_shoulder_y = int(lm[11].x * w),int(lm[11].y * h) #Toa do vai trai tren man anh
    right_shoulder_x,right_shoulder_y = int(lm[12].x * w),int(lm[12].y * h) #Toa do vai phai tren man anh
    diff_y = abs(left_shoulder_y- right_shoulder_y)
    diff_x = abs(left_shoulder_x - right_shoulder_x)
    if diff_x == 0: return None
    angle = math.degrees(math.atan2(abs(diff_y),abs(diff_x)))
    # ratio = diff_y / diff_x #Tinh ti le
    shouder_history.append(angle) #Save variable old
    smooth_ratio = sum(shouder_history) / len(shouder_history)
    return smooth_ratio

#Kiem tra ngoi gu lung
def torso_angle(res):
    if not res.pose_landmarks:
        logg.error("Not found skeleton!")
        return None
    lm = res.pose_landmarks.landmark
    shoulder_x,shoulder_y= (lm[11].x + lm[12].x) / 2,(lm[11].y + lm[12].y) / 2
    hip_x, hip_y= (lm[23].x + lm[24].x) / 2, (lm[23].y + lm[24].y) / 2
    delta_x, delta_y = shoulder_x - hip_x, shoulder_y - hip_y #Lấy hông làm gốc
    angle = math.degrees(math.atan2(abs(delta_x),abs(delta_y))) # Góc lệch so với phương thẳng đứng
    torso_history.append(angle)
    smooth_angle = sum(torso_history) / len(torso_history)
    return smooth_angle

#Kiem tra ngoi cúi đầu
def neck_angle(res):
    if not res.pose_landmarks:
        logg.error("Not found skeleton!")
        return None
    lm = res.pose_landmarks.landmark

    nose_x,nose_y = lm[0].x,lm[0].y

    shoulder_x = (lm[11].x + lm[12].x) / 2
    shoulder_y = (lm[11].y + lm[12].y) / 2
    
    hip_x = (lm[23].x + lm[24].x) / 2
    hip_y = (lm[23].y + lm[24].y) / 2
    
    v1_x,v1_y = nose_x - shoulder_x, nose_y - shoulder_y #vector shoulder,nose
    v2_x,v2_y = hip_x - shoulder_x,hip_y - shoulder_y #vector shoulder,hip

    scalar_product = v1_x * v2_x + v1_y * v2_y #a*b = x1x2 + y1y2
    len_v1,len_v2 = math.sqrt(v1_x**2 + v1_y**2),math.sqrt(v2_x**2 + v2_y**2) #Tinh do dai vector

    if len_v1 == 0 or len_v2 == 0:
        return None

    angle_cos = max(-1,min(1,scalar_product / (len_v1 * len_v2) ))


    angle_result = math.degrees(math.acos(angle_cos)) #Tinh goc 2 vector

    # Chuyển về độ lệch cổ
    neck_devitaion = abs(180 - angle_result)
    neck_history.append(neck_devitaion)
    smooth_neck = sum(neck_history) / len(neck_history)
    return smooth_neck

def send_snapshot(token,session_id,shouder_r,torso_a,neck_a,status):
    try:
        http_res = requests.post("http://localhost:8080/api/posture-snapshots/create",
                            headers={
                                "Content-Type": "application/json",
                                "Authorization": f"Bearer {token}"
                            },
                            
                            json={
                                "sessionId": session_id,
                                "shoulderRatio": shouder_r,
                                "torsoAngle": torso_a,
                                "neckAngle": neck_a,
                                "postureStatus": status
                            }
                        )
        print(f"Snapshot sent [{status}]: {http_res.status_code}")
    except Exception as e:
        logg.error(f"Failed to send snapshot: {e}")

def send_message(token,status):
    try:
        http_res = requests.post("http://localhost:8080/api/mqtt/alert",
                            headers={
                                "Content-Type": "application/json",
                                "Authorization": f"Bearer {token}"
                            },
                            json={
                                "status":status,
                            }      
                        )
        print(f"Message sent [{status}]: {http_res.status_code}")
    except Exception as e:
        logg.error(f"Failed to send message: {e}")



def send_alert(token,session_id,status):
    try:
        http_res = requests.post("http://localhost:8080/api/alert/create",
                                headers={
                                    "Content-Type": "application/json",
                                    "Authorization": f"Bearer {token}"
                                },
                                json={
                                    "sessionId": session_id,
                                    "postureStatus": status,
                                    "message": "Bạn ngồi sai tư thế liên tục quá 30s"
                                }
                    )
        print(f"Alert sent: {http_res.status_code}")
    except Exception as e:
        logg.error(f"Failed to send alert: {e}")


while True:
    ret_front, frame_front = front_cam.read()
    ret_side, frame_side = side_cam.read()
    h_f, w_f, _ = frame_front.shape
    shouder_ang = None
    torso_ang = None
    neck_ang = None


    if ret_front:
        frame_front = cv2.flip(frame_front,1)
        front_rgb = cv2.cvtColor(frame_front,cv2.COLOR_BGR2RGB)    
        res_front = pose_front.process(front_rgb) #Đưa ảnh vào cho AI phân tích
        if res_front.pose_landmarks:

            mpDraw.draw_landmarks(frame_front, res_front.pose_landmarks, mpPose.POSE_CONNECTIONS)
            #Kiểm tra ngồi lệch vai
            shouder_ang = compare_Diff_Shoulder(res_front,frame_front)


    if ret_side:
        size_rgb = cv2.cvtColor(frame_side,cv2.COLOR_BGR2RGB)
        res_side = pose_side.process(size_rgb)
        if res_side.pose_landmarks:
            mpDraw.draw_landmarks(frame_side, res_side.pose_landmarks, mpPose.POSE_CONNECTIONS)
            torso_ang = torso_angle(res_side)
            neck_ang = neck_angle(res_side)
    warning_count = 0 #Đếm cảnh báo
    bad_count = 0 #Đếm cảnh báo tệ

    if shouder_ang is not None:
        if shouder_ang < 5:      s_text, s_col = "GOOD", (0, 255, 0)
        elif shouder_ang < 10:   s_text, s_col = "WARNING", (0, 255, 255); warning_count += 1
        else:                   s_text, s_col = "BAD", (0, 0, 255); bad_count += 1
        if ret_front: cv2.putText(frame_front, f"Shoulder: {shouder_ang:.1f} ({s_text})", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, s_col, 2)

    # Đánh giá lưng (từ Side Cam)
    if torso_ang is not None:
        if torso_ang < 8:        t_text, t_col = "GOOD", (0, 255, 0)
        elif torso_ang < 15:     t_text, t_col = "WARNING", (0, 255, 255); warning_count += 1
        else:                   t_text, t_col = "BAD", (0, 0, 255); bad_count += 1
        if ret_side: cv2.putText(frame_side, f"Torso: {torso_ang:.1f} ({t_text})", (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, t_col, 2)    
    

    # Đánh giá cổ (từ Side Cam)
    if neck_ang is not None:
        if neck_ang < 15:        n_text, n_col = "GOOD", (0, 255, 0)
        elif neck_ang < 25:      n_text, n_col = "WARNING", (0, 255, 255); warning_count += 1
        else:                   n_text, n_col = "BAD", (0, 0, 255); bad_count += 1
        if ret_side: cv2.putText(frame_side, f"Neck: {neck_ang:.1f} ({n_text})", (30, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, n_col, 2)


    # Quyết định trạng thái cuối cùng
    if bad_count > 0:       final_text, final_color = "BAD_POSTURE", (0, 0, 255)
    elif warning_count > 0: final_text, final_color = "WARNING_POSTURE", (0, 255, 255)
    else:                   final_text, final_color = "GOOD_POSTURE", (0, 255, 0)

    # Hiển thị trạng thái lên màn hình Front Cam
    if ret_front:
        cv2.putText(frame_front, final_text, (30, h_f - 40), cv2.FONT_HERSHEY_COMPLEX, 1, final_color, 2)


    if  final_text == "GOOD_POSTURE":
            status_start_time = None  # Reset bộ đếm trì hoãn khi tư thế tốt
            
            # Nếu trạng thái chuyển từ Xấu/Cảnh báo -> Tốt: Gửi ngay lập tức snapshot thông báo phục hồi
            if final_text != last_sent_status:
                send_snapshot(token, SESSION_ID, shouder_ang, torso_ang, neck_ang, final_text)
                send_message(token, final_text)
                last_sent_status = final_text
                
            # Reset trạng thái cảnh báo nguy hiểm liên tục 30s
            bad_start_time = None
            alert_sent = False


    else: # WARNING_POSTURE hoặc BAD_POSTURE
        if final_text != last_sent_status:
            if status_start_time is None:
                status_start_time = time.time()
                
            posture_duration = time.time() - status_start_time
            if ret_front:
                cv2.putText(frame_front, f"Pending Send: {int(posture_duration)}s", (30, h_f - 80), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
            
            if final_text == "WARNING_POSTURE" and posture_duration >= WARNING_DELAY:
                send_snapshot(token, SESSION_ID, shouder_ang, torso_ang, neck_ang, final_text)
                send_message(token, final_text)
                last_sent_status = final_text
                status_start_time = None
            elif final_text == "BAD_POSTURE" and posture_duration >= BAD_DELAY:
                send_snapshot(token, SESSION_ID, shouder_ang, torso_ang, neck_ang, final_text)
                send_message(token, final_text)
                last_sent_status = final_text
                status_start_time = None

        else:
            status_start_time = None

        # 2. Hệ thống cảnh báo khẩn cấp sau 30s khi ngồi BAD liên tục
        if final_text == "BAD_POSTURE":
            if bad_start_time is None:
                bad_start_time = time.time()
            bad_duration = time.time() - bad_start_time
            
            if ret_front:
                cv2.putText(frame_front, f"BAD Time: {int(bad_duration)}s", (30, h_f - 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                
            if bad_duration >= ALERT_DELAY and not alert_sent:
                print("⚠️ CẢNH BÁO: Vui lòng ngồi đúng tư thế!")
                send_alert(token, SESSION_ID, final_text)
                alert_sent = True
        else:
            bad_start_time = None
            alert_sent = False

    if ret_front: cv2.imshow("Front Cam - Shoulder", frame_front)
    if ret_side: cv2.imshow("Side Cam - Torso & Neck", frame_side)



    if cv2.waitKey(1) == ord('q'):
        break


front_cam.release()
side_cam.release()
cv2.destroyAllWindows()