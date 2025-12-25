# LiveTalking Dockerfile
# 基于Ubuntu 22.04的深度学习环境
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    software-properties-common \
    python3.10 \
    python3.10-dev \
    python3.10-venv \
    python3-pip \
    ffmpeg \
    git \
    curl \
    wget \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libsndfile1 \
    portaudio19-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 创建Python虚拟环境
RUN python3.10 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 升级pip
RUN pip install --upgrade pip setuptools wheel

# 复制依赖文件
COPY requirements.txt .
COPY pyproject.toml .

# 安装Python依赖
# 先安装torch相关（单独安装以利用Docker缓存）
RUN pip install torch==2.1.0 torchvision==0.16.0 torchaudio==2.1.0 --index-url https://download.pytorch.org/whl/cu121

# 安装其他依赖
RUN pip install -r requirements.txt

# 安装项目包
COPY . .
RUN pip install -e .

# 创建必要的目录
RUN mkdir -p /app/models /app/data /app/logs

# 设置环境变量
ENV PYTHONPATH=/app
ENV CUDA_VISIBLE_DEVICES=0

# 暴露端口
EXPOSE 8011

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8011/health', timeout=5)" || exit 1

# 启动命令
CMD ["python", "src/main/start_quick_fixed.py"]
