import cv2
import torch
from ultralytics import YOLO
import numpy as np

# Select GPU if available
device = "cuda" if torch.cuda.is_available() else "cpu"

# Load YOLOv8n model (no FP16 precision)
model = YOLO("yolov8n.pt").to(device)

# Open webcam (0 = default camera)
cap = cv2.VideoCapture(0)

# Set webcam resolution to 640x480
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    # Convert frame to RGB format (YOLO requirement)
    img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # Normalize the image and convert to a PyTorch tensor
    img_tensor = torch.from_numpy(img).float() / 255.0  # Normalize to [0, 1]
    img_tensor = img_tensor.permute(2, 0, 1)  # Change shape to (C, H, W)
    img_tensor = img_tensor.unsqueeze(0)  # Add batch dimension

    # Move tensor to the correct device (GPU or CPU)
    img_tensor = img_tensor.to(device)  # No need to convert to FP16

    # Run YOLO inference
    results = model(img_tensor)  # Pass the tensor as input

    # Loop through the results list
    for result in results:
        result.plot()  # Call the plot method on each result object

    # Show the output
    cv2.imshow("YOLOv8n Webcam Detection (640x480)", frame)

    # Press 'q' to quit
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()

