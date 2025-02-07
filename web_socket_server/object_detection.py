from collections import defaultdict
import cv2
import numpy as np
import time
import torch
from ultralytics import YOLO

# Select GPU if available
device = "cuda" if torch.cuda.is_available() else "cpu"

# Load YOLOv8n model (no FP16 precision)
model = YOLO("yolov8n.pt").to(device)

# Open webcam (0 = default camera)
cap = cv2.VideoCapture(0)

# Set webcam resolution to 640x480
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# loop through the video frames
while cap.isOpened():
    ret, frame = cap.read()

    if not ret:
        break

    results = model.track(frame, persist=True)
    boxes = results[0].boxes.xywh.cpu()
    annotated_frame = results[0].plot()

    # Show the output
    cv2.imshow("YOLOv8n Webcam Detection (640x480)", annotated_frame)

    # Press 'q' to quit
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

# release the video capture object and close the display window
cap.release()
out.release()
cv2.destroyAllWindows()

