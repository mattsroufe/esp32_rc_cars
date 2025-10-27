#!/usr/bin/env python3
"""
WebSocket video streaming client for the async MJPEG server.
Captures frames from a webcam or video file, JPEG-encodes them, and streams them over WebSocket.
Optimized for stable 60 FPS where hardware allows.
"""

import asyncio
import cv2
import websockets
import argparse
import time
import numpy as np

# ----------------------------
# Default configuration
# ----------------------------
DEFAULT_SERVER = "ws://localhost:8080/ws"
TARGET_FPS = 60
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
JPEG_QUALITY = 80

# ----------------------------
# Frame capture and streaming
# ----------------------------
async def stream_video(source: str, server_url: str, target_fps: int):
    print(f"Connecting to {server_url} ...")
    async with websockets.connect(server_url, max_size=None) as ws:
        print("✅ Connected to server.")

        # ----------------------------
        # Capture setup
        # ----------------------------
        if source == "camera":
            cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
            # Request MJPEG mode if supported (helps unlock 60 FPS)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
            cap.set(cv2.CAP_PROP_FPS, target_fps)
        else:
            cap = cv2.VideoCapture(source)

        if not cap.isOpened():
            print(f"❌ Could not open source: {source}")
            return

        actual_fps = cap.get(cv2.CAP_PROP_FPS)
        if not actual_fps or np.isnan(actual_fps):
            actual_fps = target_fps  # fallback if not reported
        print(f"🎥 Camera reports {actual_fps:.1f} FPS")

        # Use measured or target FPS for pacing
        frame_interval = 1.0 / min(actual_fps, target_fps)
        next_frame_time = time.time()

        frame_count = 0
        start_time = time.time()

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("⚠️ End of video or camera read error.")
                    break

                # Encode to JPEG
                ret, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
                if not ret:
                    continue

                # Send binary frame
                await ws.send(jpeg.tobytes())
                frame_count += 1

                # FPS pacing
                next_frame_time += frame_interval
                delay = next_frame_time - time.time()
                if delay > 0:
                    await asyncio.sleep(delay)
                else:
                    next_frame_time = time.time()

                # Display local FPS every few seconds
                if frame_count % int(actual_fps) == 0:
                    elapsed = time.time() - start_time
                    fps_measured = frame_count / elapsed
                    print(f"📈 Streaming at ~{fps_measured:.1f} FPS")
                    frame_count = 0
                    start_time = time.time()

        except KeyboardInterrupt:
            print("🛑 Stream stopped by user.")
        finally:
            cap.release()
            await ws.close()
            print("🔒 Connection closed.")

# ----------------------------
# CLI entry
# ----------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stream webcam or video to async MJPEG server via WebSocket.")
    parser.add_argument("--source", default="camera", help="Video source (default: webcam, or path to video file)")
    parser.add_argument("--server", default=DEFAULT_SERVER, help="WebSocket server URL (default: ws://localhost:8080/ws)")
    parser.add_argument("--fps", type=int, default=TARGET_FPS, help="Target FPS (default: 60)")
    args = parser.parse_args()

    asyncio.run(stream_video(args.source, args.server, args.fps))

