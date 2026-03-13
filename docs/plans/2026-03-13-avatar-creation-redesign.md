# 新建数字人功能改进设计文档

**日期**: 2026-03-13
**分支**: wav2lip384
**状态**: 已批准

## 概述

改进数字人创建功能，简化用户操作，固定使用 Doubao TTS，并添加多项增强功能。

---

## 核心需求

1. **固定 TTS 引擎**：只使用 Doubao TTS，移除其他选项
2. **Voice ID 选择**：提供常用音色下拉选择，支持自定义输入
3. **固定分辨率**：使用 genavatar384.py 生成 384x384 分辨率头像

---

## 架构设计

```
用户点击"新建形象"
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  AvatarCreatePage（简化表单）                            │
│  ├─ 上传视频（支持裁剪、预览）                            │
│  ├─ 输入形象名称                                         │
│  ├─ 显示 "语音引擎：Doubao TTS"（固定）                    │
│  ├─ 选择音色（下拉选择 + 试听 + 自定义）                  │
│  └─ 上传进度显示                                         │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  POST /avatars (multipart/form-data)                     │
│  ├─ video: 文件                                         │
│  ├─ name: 形象名称                                      │
│  ├─ tts_type: "doubao" (固定)                           │
│  └─ voice_id: 音色ID                                    │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  后端处理 (avatar_manager.py)                           │
│  ├─ 验证文件类型和大小                                   │
│  ├─ 创建 data/avatars/{avatar_id}/                      │
│  ├─ 调用 genavatar384.py (384x384)                      │
│  ├─ WebSocket 推送生成进度                               │
│  └─ 更新 meta.json                                      │
└─────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────────────┐
│  前端实时显示                                           │
│  ├─ WebSocket 接收进度更新                              │
│  └─ AvatarListPage 轮询状态                             │
└─────────────────────────────────────────────────────────┘
```

---

## 文件清单

### 修改文件

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `frontend/desktop_app/src/pages/AvatarCreatePage.tsx` | 修改 | 简化表单，添加音色选择和试听 |
| `src/services/avatar_manager.py` | 修改 | 使用 genavatar384.py，添加 WebSocket 进度推送 |
| `src/main/app.py` | 新增 | 添加音色试听 API，WebSocket 端点 |

### 新建文件

| 文件 | 说明 |
|------|------|
| `frontend/desktop_app/src/components/AudioPlayer.tsx` | 音色试听播放器组件 |
| `frontend/desktop_app/src/components/VideoCropper.tsx` | 视频裁剪组件 |
| `src/services/tts_preview.py` | TTS 音色试听服务 |

---

## 详细设计

### 1. 前端改动

#### 1.1 移除 TTS 引擎选择

**位置**: `AvatarCreatePage.tsx` 第 15-20 行

**删除**: `TTS_OPTIONS` 常量

**替换为**:

```typescript
// 默认 Voice ID（温柔淑女）
const DEFAULT_VOICE_ID = 'zh_female_wenroushunshun_mars_bigtts';

// 常用音色列表
const VOICE_OPTIONS = [
  { label: '温柔淑女（推荐）', value: 'zh_female_wenroushunshun_mars_bigtts' },
  { label: '阳光青年', value: 'zh_male_yangguangqingnian_mars_bigtts' },
  { label: '甜美桃子', value: 'zh_female_tianmeitaozi_mars_bigtts' },
  { label: '爽快思思', value: 'zh_female_shuangkuaisisi_moon_bigtts' },
  { label: '知性女声', value: 'zh_female_zhixingnvsheng_mars_bigtts' },
  { label: '清爽男大', value: 'zh_male_qingshuangnanda_mars_bigtts' },
  { label: '京腔侃爷', value: 'zh_male_jingqiangkanye_moon_bigtts' },
  { label: '湾湾小何', value: 'zh_female_wanwanxiaohe_moon_bigtts' },
  { label: '广州德哥', value: 'zh_male_guozhoudege_moon_bigtts' },
  { label: '呆萌川妹', value: 'zh_female_daimengchuanmei_moon_bigtts' },
  { label: '自定义输入...', value: '__custom__' },
];
```

#### 1.2 固定 TTS 引擎显示

**位置**: `AvatarCreatePage.tsx` 表单部分

**原来的 TTS Select** → **替换为固定文本**:

```tsx
<div style={{ marginBottom: 16 }}>
  <Text style={{ color: '#666', display: 'block', marginBottom: 8 }}>
    语音引擎 (TTS)
  </Text>
  <div style={{
    background: '#f5f5f5',
    padding: '10px 16px',
    borderRadius: 8,
    color: '#333',
    fontWeight: 500,
    fontSize: 14
  }}>
    Doubao TTS
  </div>
</div>
```

#### 1.3 音色选择 + 试听

```tsx
const [selectedVoice, setSelectedVoice] = useState(DEFAULT_VOICE_ID);
const [customVoice, setCustomVoice] = useState('');
const [showCustomInput, setShowCustomInput] = useState(false);

<Form.Item
  label={
    <span style={{ color: '#666' }}>
      语音音色
      <Tooltip title="点击试听按钮可预览音色">
        <InfoCircleOutlined style={{ marginLeft: 4, color: '#999' }} />
      </Tooltip>
    </span>
  }
  name="voice_id"
  rules={[{ required: true, message: '请选择语音音色' }]}
>
  <Space.Compact style={{ width: '100%' }}>
    <Select
      options={VOICE_OPTIONS}
      value={selectedVoice}
      onChange={(val) => {
        setSelectedVoice(val);
        setShowCustomInput(val === '__custom__');
        form.setFieldValue('voice_id', val === '__custom__' ? customVoice : val);
      }}
      showSearch
      optionFilterProp="label"
      placeholder="选择音色"
      style={{ flex: 1 }}
    />
    <Button
      icon={<SoundOutlined />}
      onClick={() => handlePreviewVoice(selectedVoice)}
      disabled={selectedVoice === '__custom__' || !selectedVoice}
    >
      试听
    </Button>
  </Space.Compact>
</Form.Item>

{showCustomInput && (
  <Form.Item
    label="自定义 Voice ID"
    style={{ marginBottom: 16 }}
  >
    <Input
      placeholder="输入 Doubao Voice Type ID"
      value={customVoice}
      onChange={(e) => {
        setCustomVoice(e.target.value);
        form.setFieldValue('voice_id', e.target.value);
      }}
      style={{ borderRadius: 8 }}
    />
    <Text style={{ color: '#999', fontSize: 12, display: 'block', marginTop: 4 }}>
      完整音色列表请参考：
      <a href="https://www.volcengine.com/docs/6561/1257544" target="_blank" rel="noopener noreferrer">
        豆包语音音色列表
      </a>
    </Text>
  </Form.Item>
)}
```

#### 1.4 音色试听功能

```typescript
const [previewAudio, setPreviewAudio] = useState<string>('');
const [previewLoading, setPreviewLoading] = useState(false);

const handlePreviewVoice = async (voiceId: string) => {
  if (!voiceId || voiceId === '__custom__') return;

  setPreviewLoading(true);
  try {
    // 调用试听 API
    const audioUrl = await previewVoiceTTS(voiceId);
    setPreviewAudio(audioUrl);

    // 播放音频
    const audio = new Audio(audioUrl);
    audio.play();
  } catch (e) {
    antMessage.error('试听失败: ' + String(e));
  } finally {
    setPreviewLoading(false);
  }
};
```

#### 1.5 提交逻辑固定 TTS

```typescript
const handleSubmit = async () => {
  try {
    const values = await form.validateFields();
    if (!videoFile) {
      antMessage.warning('请先上传视频文件');
      return;
    }

    setStep('submitting');
    setProgress(10);

    const formData = new FormData();
    const autoId = `avatar_${values.name.toLowerCase().replace(/\s+/g, '_')}_${Date.now()}`;
    formData.append('avatar_id', autoId);
    formData.append('name', values.name);
    formData.append('tts_type', 'doubao');  // 固定值
    formData.append('voice_id', selectedVoice === '__custom__' ? customVoice : selectedVoice);
    formData.append('video', videoFile);

    // 可选：视频裁剪时间段
    if (videoStartTime && videoEndTime) {
      formData.append('start_time', videoStartTime.toString());
      formData.append('end_time', videoEndTime.toString());
    }

    setProgress(40);

    const result = await createAvatar(formData);
    setProgress(100);
    setCreatedId(result.avatar_id);
    setStep('done');

  } catch (e: any) {
    setStep('error');
    antMessage.error('创建失败: ' + (e?.message ?? String(e)));
  }
};
```

---

### 2. 后端改动

#### 2.1 修改 avatar_manager.py

**位置**: `src/services/avatar_manager.py`

**修改 `generate_avatar_sync` 函数**:

```python
def generate_avatar_sync(avatar_id: str, video_path: str, name: str,
                         tts_type: str = "doubao",  # 默认改为 doubao
                         voice_id: str = "zh_female_wenroushunshun_mars_bigtts",  # 默认值
                         start_time: float = None,
                         end_time: float = None):
    """
    同步调用 wav2lip/genavatar384.py 生成数字人形象。

    Args:
        avatar_id: 头像ID
        video_path: 源视频路径
        name: 头像名称
        tts_type: TTS类型（固定为doubao）
        voice_id: 音色ID
        start_time: 视频开始时间（秒），用于裁剪
        end_time: 视频结束时间（秒），用于裁剪
    """
    avatar_path = get_avatar_path(avatar_id)
    avatar_path.mkdir(parents=True, exist_ok=True)

    # 写入 creating 状态
    meta = {
        "avatar_id": avatar_id,
        "name": name,
        "tts_type": "doubao",  # 固定为 doubao
        "voice_id": voice_id,
        "created_at": datetime.now().isoformat(),
        "status": "creating",
        "error": None,
        "frame_count": 0,
        "progress": 0,  # 新增：生成进度
    }
    _write_meta(avatar_id, meta)

    try:
        project_root = Path(__file__).parent.parent.parent

        # ✅ 使用 genavatar384.py
        genavatar_script = project_root / "wav2lip" / "genavatar384.py"

        cmd = [
            sys.executable,
            str(genavatar_script),
            "--avatar_id", avatar_id,
            "--video_path", video_path,
            "--img_size", "384",  # ✅ 固定 384x384
        ]

        # 添加裁剪参数（如果有）
        if start_time is not None:
            cmd.extend(["--start_time", str(start_time)])
        if end_time is not None:
            cmd.extend(["--end_time", str(end_time)])

        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=1800,  # 30分钟超时
        )

        if result.returncode != 0:
            raise RuntimeError(result.stderr or "genavatar process failed")

        # 移动生成的文件到正确位置
        gen_output = project_root / "results" / "avatars" / avatar_id
        target = avatar_path

        if gen_output.exists() and gen_output != target:
            # ... 文件移动逻辑保持不变 ...

        # 统计帧数
        face_imgs_path = target / "face_imgs"
        frame_count = len(list(face_imgs_path.glob("*.png"))) if face_imgs_path.exists() else 0

        # 更新 meta 为 ready
        meta.update({
            "status": "ready",
            "frame_count": frame_count,
            "completed_at": datetime.now().isoformat(),
            "progress": 100,
        })
        _write_meta(avatar_id, meta)

    except Exception as e:
        meta.update({
            "status": "error",
            "error": str(e),
            "progress": 0,
        })
        _write_meta(avatar_id, meta)
        raise
```

#### 2.2 新增音色试听 API

**位置**: `src/main/app.py`

```python
async def preview_voice_tts(request):
    """生成音色试听音频"""
    try:
        params = await request.json()
        voice_id = params.get('voice_id')

        if not voice_id:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "voice_id is required"}),
                status=400
            )

        # 验证 voice_id 格式
        import re
        if not re.match(r'^[a-zA-Z0-9_\-]+$', voice_id):
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Invalid voice_id format"}),
                status=400
            )

        # 调用 Doubao TTS API 生成试听音频
        from tts_service import generate_preview_audio
        audio_data = await generate_preview_audio(
            text="你好，我是数字人助手。",  # 固定试听文本
            voice_id=voice_id
        )

        # 返回音频文件
        return web.Response(
            body=audio_data,
            content_type='audio/mpeg'
        )

    except Exception as e:
        logger.error(f"[PREVIEW] Voice preview failed: {str(e)}")
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "msg": f"Preview failed: {str(e)}"}),
            status=500
        )

# 添加路由
appasync.router.add_post('/preview_voice', preview_voice_tts)
```

#### 2.3 WebSocket 进度推送

```python
# WebSocket 连接处理
async def avatar_progress_ws(request):
    """WebSocket 连接用于推送头像生成进度"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    avatar_id = request.query.get('avatar_id')
    if not avatar_id:
        await ws.close()
        return ws

    try:
        # 轮询 avatar 状态并推送进度
        while True:
            avatar_meta = get_avatar(avatar_id)
            if not avatar_meta:
                await ws.send_json({'error': 'Avatar not found'})
                break

            # 发送进度更新
            await ws.send_json({
                'status': avatar_meta.get('status'),
                'progress': avatar_meta.get('progress', 0),
                'message': f"生成进度: {avatar_meta.get('progress', 0)}%"
            })

            # 完成或失败则退出
            if avatar_meta.get('status') in ['ready', 'error']:
                break

            await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"[WS] Avatar progress error: {str(e)}")
    finally:
        await ws.close()

    return ws

# 添加 WebSocket 路由
appasync.router.add_get('/ws/avatar_progress/{avatar_id}', avatar_progress_ws)
```

---

### 3. 新增组件

#### 3.1 音色试听 API 客户端

**文件**: `frontend/desktop_app/src/api/avatar.ts`

```typescript
export const previewVoiceTTS = async (voiceId: string): Promise<string> => {
  const res = await client.post('/preview_voice', { voice_id }, {
    responseType: 'blob'
  });
  return URL.createObjectURL(res.data);
};
```

#### 3.2 进度显示组件

**文件**: `frontend/desktop_app/src/components/AvatarProgress.tsx` (新建)

```typescript
import { useEffect, useState } from 'react';
import { Progress, Card, Tag } from 'antd';

interface AvatarProgressProps {
  avatarId: string;
  onComplete?: () => void;
}

export default function AvatarProgress({ avatarId, onComplete }: AvatarProgressProps) {
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<'creating' | 'ready' | 'error'>('creating');

  useEffect(() => {
    // 建立 WebSocket 连接
    const ws = new WebSocket(`ws://localhost:8011/ws/avatar_progress/${avatarId}`);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setProgress(data.progress);
      setStatus(data.status);

      if (data.status === 'ready' || data.status === 'error') {
        ws.close();
        onComplete?.();
      }
    };

    return () => ws.close();
  }, [avatarId, onComplete]);

  return (
    <Card title="生成进度" style={{ marginTop: 24 }}>
      <Progress percent={progress} status={status === 'error' ? 'exception' : 'active'} />
      <div style={{ marginTop: 16, textAlign: 'center' }}>
        <Tag color={status === 'creating' ? 'processing' : status === 'ready' ? 'success' : 'error'}>
          {status === 'creating' ? '生成中' : status === 'ready' ? '完成' : '失败'}
        </Tag>
      </div>
    </Card>
  );
}
```

---

### 4. Settings 默认头像设置

**位置**: `frontend/desktop_app/src/components/Settings.tsx`

**新增默认头像选择**:

```typescript
// 添加到 Settings 组件
<Card title="默认头像" size="small" className="mb-4">
  <Form.Item label="默认头像">
    <Select
      options={avatars.map(a => ({ label: a.name, value: a.avatar_id }))}
      placeholder="选择默认头像"
      onChange={(val) => {
        localStorage.setItem('livetalking_default_avatar', val);
        message.success('默认头像已设置');
      }}
    />
  </Form.Item>
  <Text type="secondary" style={{ fontSize: 12 }}>
    新对话开始时将使用此头像
  </Text>
</Card>
```

---

### 5. 数据流

**提交阶段**:

```
FormData {
  avatar_id: "avatar_xxx_1234567890",
  name: "小雅",
  tts_type: "doubao",  // 固定
  voice_id: "zh_female_wenroushunshun_mars_bigtts",
  video: <File>,
  start_time: 0,      // 可选
  end_time: 30        // 可选
}
```

**后端处理**:

```
POST /avatars
    │
    ├─ 验证: 文件类型、大小、格式
    ├─ 生成 avatar_id
    ├─ 创建目录 + meta.json (status: "creating", progress: 0)
    │
    ├─ genavatar384.py
    │   ├─ 视频裁剪（如果指定时间段）
    │   ├─ 提取帧 → full_imgs/
    │   ├─ 人脸检测 → face_imgs/ (384x384)
    │   ├─ 保存坐标 → coords.pkl
    │   └─ 更新 meta (progress: 100, status: "ready")
    │
    └─ WebSocket 实时推送进度
```

**前端接收**:

```
WebSocket 连接
    ├─ 接收进度更新
    ├─ 更新进度条
    └─ 完成后跳转到列表页
```

---

### 6. 错误处理

| 场景 | 检测位置 | 处理方式 |
|------|----------|----------|
| 文件过大（>500MB） | 前端 + 后端 | 前端阻止上传，后端返回 400 |
| 格式不支持 | 前端 accept | 隐藏不支持文件 |
| 视频无人脸 | genavatar384.py | status: "error", 显示错误信息 |
| 生成超时 | 后端 timeout | status: "error", 提示重试 |
| 磁盘不足 | 后端 OSError | status: "error", 记录日志 |
| WebSocket 断开 | 前端 | 回退到轮询模式 |
| TTS API 失败 | 试听接口 | 显示错误，禁用试听按钮 |

---

### 7. 测试计划

| 测试项 | 验证内容 |
|--------|----------|
| **功能测试** |
| TTS 固定 | 界面无 TTS 选择，提交数据为 doubao |
| 音色选择 | 下拉列表显示，值正确传递 |
| 自定义音色 | 输入框出现，值正确传递 |
| 音色试听 | 点击试听播放音频 |
| 视频上传 | mp4/mov/avi 支持 |
| 进度显示 | WebSocket 推送进度 |
| 状态轮询 | creating → ready 正确更新 |
| **边界测试** |
| 空文件名 | 表单验证提示 |
| 超大文件 | 拒绝上传 |
| 无效音色ID | 验证失败 |
| **性能测试** |
| 并发创建 | 多个头像同时生成 |
| 长视频处理 | 裁剪功能正常 |

---

### 8. API 变更

**新增端点**:

| 端点 | 方法 | 说明 |
|------|------|------|
| `/preview_voice` | POST | 生成音色试听音频 |
| `/ws/avatar_progress/{avatar_id}` | WebSocket | 头像生成进度推送 |

**修改端点**:

| 端点 | 变更 |
|------|------|
| `POST /avatars` | tts_type 固定为 doubao，支持 start_time/end_time 参数 |

---

### 9. 常用音色列表（完整）

```typescript
const VOICE_OPTIONS = [
  // 推荐
  { label: '温柔淑女（推荐）', value: 'zh_female_wenroushunshun_mars_bigtts' },
  { label: '阳光青年', value: 'zh_male_yangguangqingnian_mars_bigtts' },
  { label: '甜美桃子', value: 'zh_female_tianmeitaozi_mars_bigtts' },

  // 通用
  { label: '爽快思思', value: 'zh_female_shuangkuaisisi_moon_bigtts' },
  { label: '知性女声', value: 'zh_female_zhixingnvsheng_mars_bigtts' },
  { label: '清爽男大', value: 'zh_male_qingshuangnanda_mars_bigtts' },
  { label: '邻家女孩', value: 'zh_female_linjianvhai_moon_bigtts' },

  // 地方口音
  { label: '京腔侃爷', value: 'zh_male_jingqiangkanye_moon_bigtts' },
  { label: '湾湾小何', value: 'zh_female_wanwanxiaohe_moon_bigtts' },
  { label: '湾区大叔', value: 'zh_female_wanqudashu_moon_bigtts' },
  { label: '呆萌川妹', value: 'zh_female_daimengchuanmei_moon_bigtts' },
  { label: '广州德哥', value: 'zh_male_guozhoudege_moon_bigtts' },

  // 情感音色（多情感）
  { label: '柔美女友（多情感）', value: 'zh_female_roumeinvyou_emo_v2_mars_bigtts' },
  { label: '甜心小美（多情感）', value: 'zh_female_tianxinxiaomei_emo_v2_mars_bigtts' },
  { label: '高冷御姐（多情感）', value: 'zh_female_gaolengyujie_emo_v2_mars_bigtts' },

  // 自定义
  { label: '自定义输入...', value: '__custom__' },
];
```

---

### 10. 实施优先级

**P0（必须）**:
- 固定 TTS 为 doubao
- 常用音色下拉选择
- 使用 genavatar384.py（384x384）

**P1（重要）**:
- 音色试听功能
- 自定义 Voice ID 输入
- 进度显示改进

**P2（可选）**:
- 视频裁剪功能
- 默认头像设置
- WebSocket 实时进度

---

## 总结

本设计文档涵盖了数字人创建功能的全面改进：

1. **简化操作**: 固定 Doubao TTS，减少用户选择困惑
2. **音色丰富**: 提供常用音色快速选择，支持自定义
3. **体验优化**: 试听功能、进度显示、视频裁剪
4. **技术升级**: 使用 384x384 分辨率，WebSocket 实时推送

**分支**: wav2lip384
**目标**: 让项目变得更好
