# LiveTalking

Real-time interactive streaming digital human.

## 快速启动

```bash
poetry run livetalking
```

或者使用启动器：

```bash
python run_livetalking.py
```

详细说明请查看 `启动说明.md`

## 部署（Docker）

推荐使用 `docker` + `docker compose` 在带 GPU 的宿主机上部署。仓库包含 `docker/` 下的配置与脚本。

- 准备（在仓库根目录执行）:

```bash
cd docker
sudo ./deploy.sh setup
```

- 构建并启动服务:

```bash
sudo ./deploy.sh start
# 或者直接使用 docker compose
docker compose -f docker/docker-compose.yml up --build -d
```

- 说明与要点:
  - 前端位于 `frontend/desktop_app`，部署脚本会尝试在 `setup` 阶段自动构建前端并将产物挂载到 Nginx（`../frontend/desktop_app/dist`）。
  - 后端入口为 `src/main/start_quick_fixed.py`（容器运行时会跳过交互提示），也可通过 `run_livetalking.py` 本地运行。可通过环境变量配置：`LISTEN_PORT`、`TTS_TYPE`、`ASR_TYPE`、`CUDA_VISIBLE_DEVICES` 等。
  - 默认暴露端口: `8011`（应用）和 `80/443`（Nginx）。
  - GPU: 若需要 GPU 支持，请安装 `nvidia-container-toolkit` 并在宿主机上配置 NVIDIA 运行时。
  - 若不使用 GPU，请告知，我可以添加一个 CPU-only 的 Dockerfile 供选择。
