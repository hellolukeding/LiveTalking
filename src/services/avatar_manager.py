"""
Avatar Manager Service
负责数字人形象的 CRUD 管理与异步生成。
每个形象存储在 data/avatars/{avatar_id}/ 目录下，
包含 full_imgs/, face_imgs/, coords.pkl, 以及本模块维护的 meta.json。
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


# 数据目录（相对于项目根目录）
def get_avatars_root() -> Path:
    """返回 avatars 根目录（绝对路径）。"""
    # 此文件在 src/services/，项目根在 ../..
    project_root = Path(__file__).parent.parent.parent
    return project_root / "data" / "avatars"


def get_avatar_path(avatar_id: str) -> Path:
    return get_avatars_root() / avatar_id


def get_meta_path(avatar_id: str) -> Path:
    return get_avatar_path(avatar_id) / "meta.json"


def get_avatar_image_path(avatar_id: str) -> Optional[str]:
    """
    获取形象头像的相对路径（用于API返回）。
    优先使用 face_imgs，其次 full_imgs，取第一帧。
    返回 None 表示没有可用图片。
    """
    avatar_path = get_avatar_path(avatar_id)
    if not avatar_path.exists():
        return None

    # 优先使用 face_imgs（人脸裁剪图）
    face_imgs_dir = avatar_path / "face_imgs"
    full_imgs_dir = avatar_path / "full_imgs"

    image_dir = None
    if face_imgs_dir.exists():
        images = sorted(face_imgs_dir.glob("*.png"))
        if images:
            image_dir = "face_imgs"
            image_name = images[0].name
    elif full_imgs_dir.exists():
        images = sorted(full_imgs_dir.glob("*.png"))
        if images:
            image_dir = "full_imgs"
            image_name = images[0].name

    if image_dir:
        return f"/avatars/{avatar_id}/{image_dir}/{image_name}"
    return None


# ──────────────────────────────────────────────────────────────
# 元数据 I/O
# ──────────────────────────────────────────────────────────────

def _default_meta(avatar_id: str, name: str) -> dict:
    return {
        "avatar_id": avatar_id,
        "name": name,
        "tts_type": "doubao",  # Changed from "edge"
        "voice_id": "zh_female_wenroushunshun_mars_bigtts",  # Changed default
        "created_at": datetime.now().isoformat(),
        "status": "ready",   # creating | ready | error
        "error": None,
        "frame_count": 0,
    }


def _read_meta(avatar_id: str) -> Optional[dict]:
    meta_path = get_meta_path(avatar_id)
    if not meta_path.exists():
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _write_meta(avatar_id: str, meta: dict):
    meta_path = get_meta_path(avatar_id)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────────────────────
# 公开 API
# ──────────────────────────────────────────────────────────────

def list_avatars() -> list[dict]:
    """
    扫描 data/avatars/ 下所有子目录，读取 meta.json 返回形象列表。
    如果 meta.json 不存在，则为旧版 avatar 自动生成默认元数据。
    """
    root = get_avatars_root()
    root.mkdir(parents=True, exist_ok=True)
    avatars = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        avatar_id = entry.name
        meta = _read_meta(avatar_id)
        if meta is None:
            # 检查是否是合法的 avatar 目录（有 coords.pkl 或 face_imgs）
            has_data = (entry / "coords.pkl").exists() or (entry / "face_imgs").exists()
            if not has_data:
                continue
            # 为旧 avatar 自动写入默认 meta
            meta = _default_meta(avatar_id, avatar_id.replace("_", " ").title())
            # 统计帧数
            face_imgs = entry / "face_imgs"
            if face_imgs.exists():
                meta["frame_count"] = len(list(face_imgs.glob("*.png")))
            _write_meta(avatar_id, meta)
        # 添加图片路径
        meta["image_path"] = get_avatar_image_path(avatar_id)
        avatars.append(meta)
    return avatars


def get_avatar(avatar_id: str) -> Optional[dict]:
    """返回单个形象元数据，不存在则返回 None。"""
    avatar_path = get_avatar_path(avatar_id)
    if not avatar_path.exists():
        return None
    meta = _read_meta(avatar_id)
    if meta is None:
        return None
    # 添加图片路径
    meta["image_path"] = get_avatar_image_path(avatar_id)
    return meta


def update_avatar(avatar_id: str, updates: dict) -> Optional[dict]:
    """
    更新形象元数据（只更新 name / tts_type / voice_id 等允许字段）。
    返回更新后的 meta，不存在则返回 None。
    """
    meta = _read_meta(avatar_id)
    if meta is None:
        return None

    allowed_fields = {"name", "tts_type", "voice_id"}
    for field in allowed_fields:
        if field in updates:
            meta[field] = updates[field]

    meta["updated_at"] = datetime.now().isoformat()
    _write_meta(avatar_id, meta)
    return meta


def delete_avatar(avatar_id: str) -> bool:
    """删除形象目录，成功返回 True，不存在返回 False。"""
    avatar_path = get_avatar_path(avatar_id)
    if not avatar_path.exists():
        return False
    shutil.rmtree(avatar_path)
    return True


def generate_avatar_sync(avatar_id: str, video_path: str, name: str,
                         tts_type: str = "doubao",  # Changed default
                         voice_id: str = "zh_female_wenroushunshun_mars_bigtts"):  # Changed default
    """
    同步调用 wav2lip/genavatar384.py 生成数字人形象。
    此函数在后台线程中执行，会修改 meta.json 中的 status 字段。
    """
    avatar_path = get_avatar_path(avatar_id)
    avatar_path.mkdir(parents=True, exist_ok=True)

    # 写入 creating 状态
    meta = {
        "avatar_id": avatar_id,
        "name": name,
        "tts_type": "doubao",  # Changed from tts_type parameter
        "voice_id": voice_id,
        "created_at": datetime.now().isoformat(),
        "status": "creating",
        "error": None,
        "frame_count": 0,
    }
    _write_meta(avatar_id, meta)

    try:
        project_root = Path(__file__).parent.parent.parent
        # Changed from "genavatar.py" to "genavatar384.py"
        genavatar_script = project_root / "wav2lip" / "genavatar384.py"

        # 覆盖 genavatar384.py 的输出目录到 data/avatars/
        # genavatar384.py 默认输出到 ./results/avatars/{avatar_id}，
        # 我们通过软链或直接修改路径；这里使用 img_size=384
        cmd = [
            sys.executable,
            str(genavatar_script),
            "--avatar_id", avatar_id,
            "--video_path", video_path,
            "--img_size", "384",  # Changed from "96" to "384"
        ]

        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=1800,  # 30分钟超时
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr or "genavatar process failed")

        # genavatar384.py 把产物写进了 ./results/avatars/{avatar_id}
        # 把产物移动到正确位置 data/avatars/{avatar_id}
        gen_output = project_root / "results" / "avatars" / avatar_id
        target = avatar_path

        if gen_output.exists() and gen_output != target:
            if (gen_output / "full_imgs").exists():
                if (target / "full_imgs").exists():
                    shutil.rmtree(target / "full_imgs")
                shutil.move(str(gen_output / "full_imgs"), str(target / "full_imgs"))
            if (gen_output / "face_imgs").exists():
                if (target / "face_imgs").exists():
                    shutil.rmtree(target / "face_imgs")
                shutil.move(str(gen_output / "face_imgs"), str(target / "face_imgs"))
            if (gen_output / "coords.pkl").exists():
                shutil.move(str(gen_output / "coords.pkl"), str(target / "coords.pkl"))
            # 清理 results 目录
            try:
                shutil.rmtree(gen_output)
            except Exception:
                pass

        # 统计帧数
        face_imgs_path = target / "face_imgs"
        frame_count = len(list(face_imgs_path.glob("*.png"))) if face_imgs_path.exists() else 0

        # 更新 meta 为 ready
        meta.update({
            "status": "ready",
            "frame_count": frame_count,
            "completed_at": datetime.now().isoformat(),
        })
        _write_meta(avatar_id, meta)

    except Exception as e:
        meta.update({
            "status": "error",
            "error": str(e),
        })
        _write_meta(avatar_id, meta)
        raise


async def generate_avatar_async(avatar_id: str, video_path: str, name: str,
                                 tts_type: str = "doubao",  # Changed default
                                 voice_id: str = "zh_female_wenroushunshun_mars_bigtts"):  # Changed default
    """在 executor 线程中异步运行 generate_avatar_sync。"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        generate_avatar_sync,
        avatar_id, video_path, name, tts_type, voice_id
    )
