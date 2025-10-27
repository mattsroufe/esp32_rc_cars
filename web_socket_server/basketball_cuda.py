#!/usr/bin/env python3
"""
Full GPU-accelerated dual-camera motion/object detection.
Compatible with OpenCV 4.13.0-dev CUDA bindings.
"""

import cv2
import numpy as np
import time
import os

# ----------------------------
# Check CUDA
# ----------------------------
cuda_enabled = cv2.cuda.getCudaEnabledDeviceCount() > 0
if not cuda_enabled:
    raise RuntimeError("❌ No CUDA-enabled GPU found.")
cv2.cuda.setDevice(0)
print("✅ CUDA initialized")

# ----------------------------
# Background subtractor
# ----------------------------
try:
    fgbg = cv2.cuda.createBackgroundSubtractorMOG2(
        history=500, varThreshold=16, detectShadows=False
    )
    print("✅ Using cv2.cuda.createBackgroundSubtractorMOG2")
except Exception as e:
    print("⚠️  Could not create CUDA MOG2:", e)
    exit(1)

# ----------------------------
# Dynamically find working cameras
# ----------------------------
def list_cameras(max_test=6):
    cams = []
    for i in range(max_test):
        path = f"/dev/video{i}"
        if not os.path.exists(path):
            continue
        cap = cv2.VideoCapture(path)
        if cap.isOpened():
            print(f"✅ Opened camera {path}")
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FPS, 60)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cams.append(cap)
        else:
            print(f"⚠️  Failed to open {path}")
    return cams

caps = list_cameras()
if not caps:
    raise RuntimeError("❌ No cameras opened successfully.")

scale_percent = 60
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
gpu_kernel = cv2.cuda_GpuMat()
gpu_kernel.upload(kernel)

# ----------------------------
# GPU Frame Processor
# ----------------------------
def process_frame(name, frame):
    start_t = time.time()

    # Upload to GPU
    gpu_frame = cv2.cuda_GpuMat()
    gpu_frame.upload(frame)

    # Resize
    width = int(frame.shape[1] * scale_percent / 100)
    height = int(frame.shape[0] * scale_percent / 100)
    gpu_resized = cv2.cuda.resize(gpu_frame, (width, height))

    # Convert to gray
    gpu_gray = cv2.cuda.cvtColor(gpu_resized, cv2.COLOR_BGR2GRAY)

    # Background subtraction (OpenCV 4.13 CUDA signature)
    learningRate = 0.01
    gpu_fgmask = fgbg.apply(gpu_gray, learningRate)

    # Morphology (GPU)
    gpu_fgmask = cv2.cuda.erode(gpu_fgmask, gpu_kernel)
    gpu_fgmask = cv2.cuda.dilate(gpu_fgmask, gpu_kernel)

    # Download to CPU for contour drawing
    fgmask = gpu_fgmask.download()
    frame_resized = gpu_resized.download()

    # Contours
    contours, _ = cv2.findContours(fgmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        if 200 < cv2.contourArea(c) < 700:
            x, y, w, h = cv2.boundingRect(c)
            cv2.rectangle(frame_resized, (x, y), (x + w, y + h), (0, 255, 0), 2)

    # FPS overlay
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
print("🎥 Press 'q' to quit")
while True:
    for idx, cap in enumerate(caps):
        ret, frame = cap.read()
        if not ret:
            print(f"⚠️ Frame grab failed from Cam {idx}")
            continue
        try:
            process_frame(f"Cam {idx}", frame)
        except cv2.error as e:
            print(f"❌ GPU processing error on Cam {idx}: {e}")
            continue

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

print("🧹 Cleanup...")
for cap in caps:
    cap.release()
cv2.destroyAllWindows()
