#!/usr/bin/env python3
"""
Hybrid GPU/CPU dual-camera motion detection.
Uses OpenCV CUDA for heavy ops (resize, color convert, morphology)
and CPU MOG2 for background subtraction.
"""

import cv2
import numpy as np
import time

# --------------------------------------------------
# Check for CUDA support
# --------------------------------------------------
cuda_enabled = cv2.cuda.getCudaEnabledDeviceCount() > 0
print(f"CUDA available: {cuda_enabled}")

# --------------------------------------------------
# Background subtractor (CPU)
# --------------------------------------------------
fgbg = cv2.createBackgroundSubtractorMOG2(
    history=500, varThreshold=16, detectShadows=False
)

# --------------------------------------------------
# Open cameras
# --------------------------------------------------
cam_ids = ["/dev/video2", "/dev/video0"]
caps = [cv2.VideoCapture(i) for i in cam_ids]

for cap in caps:
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FPS, 60)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

scale_percent = 60  # scale down for faster processing

# --------------------------------------------------
# GPU/CPU frame processor
# --------------------------------------------------
def process_frame(name, frame):
    start_t = time.time()

    # Resize
    width = int(frame.shape[1] * scale_percent / 100)
    height = int(frame.shape[0] * scale_percent / 100)
    dim = (width, height)

    if cuda_enabled:
        # Upload to GPU
        gpu_frame = cv2.cuda_GpuMat()
        gpu_frame.upload(frame)

        # Convert to grayscale on GPU
        gpu_gray = cv2.cuda.cvtColor(gpu_frame, cv2.COLOR_BGR2GRAY)

        # Download to CPU for MOG2
        gray = gpu_gray.download()

        # Background subtraction on CPU
        fgmask = fgbg.apply(gray)

        # Upload mask back to GPU for morphology
        gpu_fgmask = cv2.cuda_GpuMat()
        gpu_fgmask.upload(fgmask)

        # Morphological operations on GPU
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        gpu_kernel = cv2.cuda_GpuMat()
        gpu_kernel.upload(kernel)

        gpu_fgmask = cv2.cuda.erode(gpu_fgmask, gpu_kernel, iterations=1)
        gpu_fgmask = cv2.cuda.dilate(gpu_fgmask, gpu_kernel, iterations=1)

        # Download final mask to CPU for contour finding
        fgmask = gpu_fgmask.download()

    else:
        # CPU fallback for all ops
        frame = cv2.resize(frame, dim, interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        fgmask = fgbg.apply(gray)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        fgmask = cv2.erode(fgmask, kernel, iterations=1)
        fgmask = cv2.dilate(fgmask, kernel, iterations=1)

    # Contour detection (CPU)
    contours, _ = cv2.findContours(fgmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        area = cv2.contourArea(contour)
        if 200 < area < 700:
            x, y, w, h = cv2.boundingRect(contour)
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

    # FPS overlay
    fps = 1.0 / (time.time() - start_t + 1e-6)
    cv2.putText(
        frame,
        f"{'Hybrid GPU/CPU' if cuda_enabled else 'CPU'} {fps:.1f} FPS",
        (10, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )

    # Display
    cv2.imshow(name, frame)


# --------------------------------------------------
# Main loop
# --------------------------------------------------
print("Press 'q' to quit.")
while True:
    for idx, cap in enumerate(caps):
        ret, frame = cap.read()
        if ret:
            process_frame(f"Cam {idx}", frame)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

print("Shutting down gracefully.")
for cap in caps:
    cap.release()
cv2.destroyAllWindows()
