#!/usr/bin/env python3
"""
Full GPU-accelerated dual-camera motion/object detection.
- Uses OpenCV CUDA for background subtraction, grayscale, and morphology.
- Automatically detects working cameras and handles frame failures gracefully.
"""

import cv2
import numpy as np
import time

# ----------------------------
# Check for CUDA support
# ----------------------------
cuda_enabled = cv2.cuda.getCudaEnabledDeviceCount() > 0
if not cuda_enabled:
    raise RuntimeError("❌ No CUDA-enabled device found. Install CUDA or GPU drivers.")

print(f"✅ CUDA available: {cuda_enabled}")
cv2.cuda.setDevice(0)

# ----------------------------
# Choose background subtractor
# ----------------------------
try:
    fgbg = cv2.cuda.createBackgroundSubtractorMOG2(
        history=500, varThreshold=16, detectShadows=False
    )
    print("✅ Using cv2.cuda.createBackgroundSubtractorMOG2")
except Exception as e:
    print("⚠️ MOG2 unavailable, falling back to cv2.cuda.createBackgroundSubtractorMOG")
    fgbg = cv2.cuda.createBackgroundSubtractorMOG()

# ----------------------------
# Detect and open working cameras
# ----------------------------
potential_cams = ["/dev/video0", "/dev/video1", "/dev/video2", "/dev/video3"]
caps = []

print("\n🔍 Checking available cameras...")
for cam_id in potential_cams:
    cap = cv2.VideoCapture(cam_id)
    if cap.isOpened():
        print(f"✅ Opened camera {cam_id}")
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FPS, 60)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        caps.append(cap)
    else:
        print(f"⚠️  Failed to open camera {cam_id}")

if not caps:
    raise RuntimeError("❌ No cameras opened successfully. Check /dev/video* devices.")

scale_percent = 60  # percent of original size

# Pre-upload morphological kernel
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

    # Resize on GPU
    width = int(frame.shape[1] * scale_percent / 100)
    height = int(frame.shape[0] * scale_percent / 100)
    gpu_resized = cv2.cuda.resize(gpu_frame, (width, height))

    # Grayscale conversion (GPU)
    gpu_gray = cv2.cuda.cvtColor(gpu_resized, cv2.COLOR_BGR2GRAY)

    # Background subtraction
    learning_rate = 0.01
    gpu_fgmask = fgbg.apply(gpu_gray, None, learning_rate)

    # Morphological operations (GPU)
    gpu_fgmask = cv2.cuda.erode(gpu_fgmask, gpu_kernel)
    gpu_fgmask = cv2.cuda.dilate(gpu_fgmask, gpu_kernel)

    # Download mask for contour detection
    fgmask = gpu_fgmask.download()
    frame_resized = gpu_resized.download()

    # Contour detection on CPU
    contours, _ = cv2.findContours(fgmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        area = cv2.contourArea(contour)
        if 200 < area < 700:
            x, y, w, h = cv2.boundingRect(contour)
            cv2.rectangle(frame_resized, (x, y), (x + w, y + h), (0, 255, 0), 2)

    # FPS overlay
    end_t = time.time()
    fps = 1.0 / (end_t - start_t + 1e-6)
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

    # Display
    cv2.imshow(name, frame_resized)


# ----------------------------
# Main loop
# ----------------------------
print("\n🎥 Press 'q' to quit.")
while True:
    for idx, cap in enumerate(caps):
        ret, frame = cap.read()
        if not ret or frame is None:
            print(f"⚠️  Frame grab failed from Cam {idx}")
            continue
        try:
            process_frame(f"Cam {idx}", frame)
        except cv2.error as e:
            print(f"❌ OpenCV GPU error from Cam {idx}: {e}")
            continue

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

print("🧹 Shutting down gracefully...")
for cap in caps:
    cap.release()
cv2.destroyAllWindows()
