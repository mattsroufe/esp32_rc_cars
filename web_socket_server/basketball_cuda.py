#!/usr/bin/env python3
"""
Full GPU-accelerated dual-camera motion/object detection.
Handles missing cameras gracefully.
"""

import cv2
import numpy as np
import time
import os

# ----------------------------
# Initialize CUDA
# ----------------------------
cuda_enabled = cv2.cuda.getCudaEnabledDeviceCount() > 0
if not cuda_enabled:
    raise RuntimeError("❌ No CUDA-enabled GPU found.")
cv2.cuda.setDevice(0)
print("✅ CUDA initialized")

# ----------------------------
# Background subtractor
# ----------------------------
fgbg = cv2.cuda.createBackgroundSubtractorMOG2(
    history=500, varThreshold=16, detectShadows=False
)

# ----------------------------
# Find working cameras
# ----------------------------
def open_cameras(max_test=6):
    cameras = []
    for i in range(max_test):
        path = f"/dev/video{i}"
        if not os.path.exists(path):
            continue
        cap = cv2.VideoCapture(path)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FPS, 60)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cameras.append((i, cap))
            print(f"✅ Camera {i} opened ({path})")
        else:
            cap.release()
            print(f"⚠️ Camera {i} failed to open ({path})")
    return cameras


cameras = open_cameras()
if not cameras:
    raise RuntimeError("❌ No active cameras found!")

print(f"🎥 Active cameras: {[i for i, _ in cameras]}")

# ----------------------------
# GPU setup
# ----------------------------
scale_percent = 60
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
gpu_kernel = cv2.cuda_GpuMat()
gpu_kernel.upload(kernel)

# ----------------------------
# GPU frame processor
# ----------------------------
def process_frame(name, frame):
    if frame is None or frame.size == 0:
        raise ValueError("Invalid frame data")

    start_t = time.time()

    # Upload frame
    gpu_frame = cv2.cuda_GpuMat()
    gpu_frame.upload(frame)

    # Resize
    width = int(frame.shape[1] * scale_percent / 100)
    height = int(frame.shape[0] * scale_percent / 100)
    gpu_resized = cv2.cuda.resize(gpu_frame, (width, height))

    # Convert to grayscale
    gpu_gray = cv2.cuda.cvtColor(gpu_resized, cv2.COLOR_BGR2GRAY)

    # Background subtraction (older CUDA API requires learningRate)
    learning_rate = 0.01
    gpu_fgmask = fgbg.apply(gpu_gray, learning_rate)

    # Morphology
    gpu_fgmask = cv2.cuda.erode(gpu_fgmask, gpu_kernel)
    gpu_fgmask = cv2.cuda.dilate(gpu_fgmask, gpu_kernel)

    # Download
    fgmask = gpu_fgmask.download()
    frame_resized = gpu_resized.download()

    # Contours
    contours, _ = cv2.findContours(fgmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        if 200 < cv2.contourArea(c) < 700:
            x, y, w, h = cv2.boundingRect(c)
            cv2.rectangle(frame_resized, (x, y), (x + w, y + h), (0, 255, 0), 2)

    fps = 1.0 / (time.time() - start_t + 1e-6)
    cv2.putText(
        frame_resized,
        f"GPU {fps:.1f} FPS",
        (10, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )

    cv2.imshow(name, frame_resized)


# ----------------------------
# Main loop
# ----------------------------
print("🟢 Press 'q' to quit")

while True:
    for idx, cap in cameras:
        ret, frame = cap.read()
        if not ret or frame is None or frame.size == 0:
            print(f"⚠️  Skipping invalid frame from camera {idx}")
            continue

        try:
            process_frame(f"Cam {idx}", frame)
        except cv2.error as e:
            print(f"❌ GPU processing error on Cam {idx}: {e}")
        except ValueError as ve:
            print(f"⚠️ {ve}")

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

print("🧹 Cleanup...")
for _, cap in cameras:
    cap.release()
cv2.destroyAllWindows()
