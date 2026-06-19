import cv2
import os
import time
import hand as hnd

pTime = 0
cap = cv2.VideoCapture(0)
path = "finger"
lst = os.listdir(path)
# for i in lst:
#     print
lst_2 = []
for i in lst:
    img = cv2.imread(f"{path}/{i}")
    lst_2.append(img)

#Tao ra 1 cai obj detector
detector = hnd.handDetector(detectionCon=0.55)

fingerId = [4,8,12,16,20]
while True:
    ret,frame = cap.read()
    if not ret: continue
    frame = detector.findHands(frame)
    landmark_list = detector.findPosition(frame,draw=False)
    # print(landmark_list)

    fin = []
    
    if(len(landmark_list) != 0):
        #Dem ngon cai
        if landmark_list[fingerId[0]][2] < landmark_list[fingerId[0] - 1][2]:
            fin.append(1)
        else: fin.append(0)

        #Dem 4 ngon dai
        for id in range(1,5):
            if landmark_list[fingerId[id]][2] < landmark_list[fingerId[id] - 2][2]:
                fin.append(1)
            else: fin.append(0)
        # print(fin)
    numOfFin = fin.count(1)
    cv2.rectangle(frame,(0,200),(100,400),(0,255,0),-1)
    cv2.putText(frame,str(numOfFin),(300,90),cv2.FONT_HERSHEY_COMPLEX,2.5,(0,255,0),2) 


    if numOfFin > 0:
        h,w,c = lst_2[numOfFin - 1].shape
        frame[0:h,0:w] = lst_2[numOfFin - 1]
    else:
        h,w,c = lst_2[5].shape
        frame[0:h,0:w] = lst_2[5]

    cTime = time.time() #Trả về số giây, gọi là thời điểm bắt đầu thời gian
    time_diff = cTime - pTime #Thời gian xử lý 1 khung hình (giây)
    fps = 1 / time_diff #Công thức fps frames per second
    pTime = cTime
    # print(f"Gia tri FPS: {fps}")
    cv2.putText(frame,f"FPS: {int(fps)}",(150,70),cv2.FONT_HERSHEY_SIMPLEX,3,(255,123,234),1)
    cv2.imshow("finger",frame)

    if cv2.waitKey(1) == ord("q"):
        break
cap.release()
cv2.destroyAllWindows()

