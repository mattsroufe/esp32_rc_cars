from collections import defaultdict
import cv2
import numpy as np
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

track_history = defaultdict(lambda: [])
# get the video properties
fps = int(cap.get(cv2.CAP_PROP_FPS))
frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
# define the codec and create VideoWriter object
output_path = "output_tracked_video.mp4"  # Output video file path
out = cv2.VideoWriter(
    output_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (frame_width, frame_height)
)
# loop through the video frames
while cap.isOpened():
    ret, frame = cap.read()

    if not ret:
        break

    results = model.track(frame, persist=True)
    boxes = results[0].boxes.xywh.cpu()
    track_ids = (
        results[0].boxes.id.int().cpu().tolist()
        if results[0].boxes.id is not None
        else None
    )
    annotated_frame = results[0].plot()
    # plot the tracks
    if track_ids:
        for box, track_id in zip(boxes, track_ids):
            x, y, w, h = box
            track = track_history[track_id]
            track.append((float(x), float(y)))  # x, y center point
            if len(track) > 30:  # retain 30 tracks for 30 frames
                track.pop(0)
            # draw the tracking lines
            points = np.array(track).astype(np.int32).reshape((-1, 1, 2))
            cv2.polylines(
                annotated_frame,
                [points],
                isClosed=False,
                color=(230, 230, 230),
                thickness=2,
            )

    # Show the output
    cv2.imshow("YOLOv8n Webcam Detection (640x480)", annotated_frame)

    # Press 'q' to quit
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

# release the video capture object and close the display window
cap.release()
out.release()
cv2.destroyAllWindows()

