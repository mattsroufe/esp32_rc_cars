import cv2
import torch
from ultralytics import YOLO
import time

# Select GPU if available
device = "cuda" if torch.cuda.is_available() else "cpu"

# Load YOLOv8n model (no FP16 precision)
model = YOLO("yolov8n.pt").to(device)

# Open webcam (0 = default camera)
cap = cv2.VideoCapture(0)

# Set webcam resolution to 640x480
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# Initialize FPS calculation variables
prev_time = 0

# Loop through the video frames
while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    # Convert the frame from BGR to RGB for YOLO inference
    img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # Run YOLO inference on the frame
    results = model(img_rgb)  # Pass the RGB frame directly, YOLO handles normalization

    # Extract detection boxes (xywh format) and annotated frame
    annotated_frame = results[0].plot()

    # Calculate FPS
    curr_time = time.time()
    fps = 1 / (curr_time - prev_time)
    prev_time = curr_time

    # Display FPS and annotated frame
    cv2.putText(annotated_frame, f"FPS: {fps:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    # Convert annotated frame back to BGR for display
    annotated_frame_bgr = cv2.cvtColor(annotated_frame, cv2.COLOR_RGB2BGR)

    # Show the output
    cv2.imshow("YOLOv8n Webcam Detection (640x480)", annotated_frame_bgr)

    # Press 'q' to quit
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

# Release the video capture object and close the display window
cap.release()
cv2.destroyAllWindows()

