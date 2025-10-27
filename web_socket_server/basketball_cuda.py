#!/usr/bin/env python3
"""
GPU-accelerated dual-camera motion/object detection.
- Combines both frames side-by-side into a single GPU stream
- Uses CUDA MOG2 background subtraction
- Falls back to CPU if CUDA unavailable
"""

import cv2
import numpy as np
import time

# ----------------------------
# Check CUDA availability
# ----------------------------
cuda_enabled = cv2.cuda.getCudaEnabledDeviceCount() > 0
print(f"CUDA available: {cuda_enabled}")

# ----------------------------
# Background subtractor
# ----------------------------
if cuda_enabled:
    fgbg = cv2.cuda.createBackgroundSubtractorMOG2(
        history=500, varThreshold=16, detectShadows=False
    )
else:
    fgbg = cv2.createBackgroundSubtractorMOG2(
        history=500, varThreshold=16, detectShadows=False
    )

# ----------------------------
# Open cameras
# ----------------------------
cam_ids = ["/dev/video0", "/dev/video2"]
caps = [cv2.VideoCapture(i) for i in cam_ids]

for cap in caps:
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FPS, 60)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

scale_percent = 60  # downscale to reduce GPU load
learning_rate = 0.01

# Prebuild kernel once
kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

if cuda_enabled:
    gpu_kernel = cv2.cuda_GpuMat()
    gpu_kernel.upload(kernel)

# ----------------------------
# Frame Processor
# ----------------------------
def process_combined(frameL, frameR):
    start_t = time.time()

    # Resize
    width = int(frameL.shape[1] * scale_percent / 100)
    height = int(frameL.shape[0] * scale_percent / 100)
    dim = (width, height)
    frameL = cv2.resize(frameL, dim, interpolation=cv2.INTER_AREA)
    frameR = cv2.resize(frameR, dim, interpolation=cv2.INTER_AREA)

    # Combine side-by-side
    combined = np.hstack((frameL, frameR))

    if cuda_enabled:
        gpu_frame = cv2.cuda_GpuMat()
        gpu_frame.upload(combined)

        # Grayscale + Background subtraction
        gpu_gray = cv2.cuda.cvtColor(gpu_frame, cv2.COLOR_BGR2GRAY)
        gpu_fgmask = fgbg.apply(gpu_gray, None, learning_rate)

        # Morphological filtering
        gpu_fgmask = cv2.cuda.erode(gpu_fgmask, gpu_kernel)
        gpu_fgmask = cv2.cuda.dilate(gpu_fgmask, gpu_kernel)

        # Download for contour detection
        fgmask = gpu_fgmask.download()
        frame = gpu_frame.download()

    else:
        gray = cv2.cvtColor(combined, cv2.COLOR_BGR2GRAY)
        fgmask = fgbg.apply(gray)
        fgmask = cv2.erode(fgmask, kernel, iterations=1)
        fgmask = cv2.dilate(fgmask, kernel, iterations=1)
        frame = combined

    # Contour detection
    contours, _ = cv2.findContours(fgmask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        area = cv2.contourArea(contour)
        if 200 < area < 1000:
            x, y, w, h = cv2.boundingRect(contour)
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

    # FPS
    fps = 1.0 / (time.time() - start_t + 1e-6)
    cv2.putText(
        frame,
        f"{'GPU' if cuda_enabled else 'CPU'} {fps:.1f} FPS",
        (10, 25),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 255),
        2,
        cv2.LINE_AA,
    )

    cv2.imshow("Combined Motion View", frame)


# ----------------------------
# Main Loop
# ----------------------------
print("Press 'q' to quit.")
while True:
    rets_frames = [cap.read() for cap in caps]
    if all(rf[0] for rf in rets_frames):
        process_combined(rets_frames[0][1], rets_frames[1][1])

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

print("Shutting down gracefully...")
for cap in caps:
    cap.release()
cv2.destroyAllWindows()
