#!/bin/bash
# OpenCV CUDA Build Script for Ubuntu (RTX 1650, No cuDNN)
# WARNING: This will install packages, GCC 12, and build OpenCV from source.

set -e

# ---------------------------
# 1️⃣ Update and Install Dependencies
# ---------------------------
sudo apt update
sudo apt install -y build-essential cmake git pkg-config \
    libgtk-3-dev libavcodec-dev libavformat-dev libswscale-dev \
    libv4l-dev libxvidcore-dev libx264-dev libjpeg-dev libpng-dev libtiff-dev \
    gfortran openexr libatlas-base-dev python3-dev python3-numpy \
    libtbbmalloc2 libtbb-dev libdc1394-dev

# ---------------------------
# 2️⃣ Install GCC/G++ 12
# ---------------------------
sudo apt install -y gcc-12 g++-12

export CC=/usr/bin/gcc-12
export CXX=/usr/bin/g++-12

# ---------------------------
# 3️⃣ Verify CUDA
# ---------------------------
if ! command -v nvcc &> /dev/null
then
    echo "CUDA not found! Please install CUDA before running this script."
    exit 1
fi
nvcc -V
nvidia-smi

# ---------------------------
# 4️⃣ Clone OpenCV repositories
# ---------------------------
mkdir -p ~/opencv_build && cd ~/opencv_build
if [ ! -d "opencv" ]; then
    git clone https://github.com/opencv/opencv.git
fi
if [ ! -d "opencv_contrib" ]; then
    git clone https://github.com/opencv/opencv_contrib.git
fi

cd opencv
git checkout 4.10.0
cd ../opencv_contrib
git checkout 4.10.0
cd ../

# ---------------------------
# 5️⃣ Create build directory
# ---------------------------
mkdir -p build && cd build

# ---------------------------
# 6️⃣ Configure OpenCV with CMake (GPU only, no DNN CUDA)
# ---------------------------
cmake -D CMAKE_BUILD_TYPE=RELEASE \
      -D CMAKE_INSTALL_PREFIX=/usr/local \
      -D PYTHON3_EXECUTABLE=$(which python3) \
      -D OPENCV_EXTRA_MODULES_PATH=~/opencv_build/opencv_contrib/modules \
      -D WITH_CUDA=ON \
      -D OPENCV_DNN_CUDA=OFF \
      -D WITH_CUBLAS=ON \
      -D ENABLE_FAST_MATH=ON \
      -D CUDA_FAST_MATH=ON \
      -D BUILD_EXAMPLES=ON \
      -D BUILD_opencv_python3=ON \
      -D CUDA_ARCH_BIN="7.5" \
      ../opencv

# ---------------------------
# 7️⃣ Build and Install
# ---------------------------
make -j$(nproc)
sudo make install
sudo ldconfig

# ---------------------------
# 8️⃣ Verify Installation
# ---------------------------
python3 - <<EOF
import cv2
print("CUDA Enabled Device Count:", cv2.cuda.getCudaEnabledDeviceCount())
print("OpenCV CUDA Build Info:")
print(cv2.getBuildInformation().splitlines()[0:20])
EOF

echo "✅ OpenCV GPU build complete!"

