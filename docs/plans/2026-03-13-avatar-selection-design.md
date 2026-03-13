# Avatar 选择功能设计文档

**日期**: 2026-03-13
**状态**: 已批准

## 概述

为 LiveTalking 项目实现每会话独立的数字人形象选择功能。用户在进入视频聊天前必须先选择一个可用的 avatar。

## 需求背景

**当前问题：**
- 后端在启动时加载单一全局 avatar，所有会话共享
- 前端没有 avatar 选择 UI
- `/offer` 接口不支持 avatar_id 参数

**目标：**
- 每个会话可以独立选择不同的 avatar
- 用户进入聊天前必须选择 avatar
- 多个会话可同时使用不同 avatar

## 架构设计

```
用户访问 /videochat
       │
       ▼
[路由守卫] 检查 URL 是否有 avatar_id 参数
       │
       ├─ 无 avatar_id → 重定向到 /select-avatar
       │
       └─ 有 avatar_id → 继续
                      │
                      ▼
              [AvatarSelectionPage] 显示所有可用 avatar
                      │
                      ▼
              用户点击选择某个 avatar
                      │
                      ▼
              跳转到 /videochat?avatar_id=xxx
                      │
                      ▼
              [VideoChat] 组件加载
                      │
                      ├─ 从 URL 获取 avatar_id
                      ├─ 调用 /offer API 时传递 avatar_id
                      └─ 开始视频会话
```

## 前端改动

### 1. 新建 AvatarSelectionPage 组件

**文件**: `frontend/desktop_app/src/pages/AvatarSelectionPage.tsx`

**功能**:
- 展示所有 status='ready' 的 avatar 卡片（网格布局）
- 每个卡片显示：预览图、名称、TTS类型、帧数
- 点击卡片 → 跳转到 `/videochat?avatar_id={id}`
- 空状态处理

### 2. 添加路由

**文件**: `frontend/desktop_app/src/App.tsx`

```tsx
<Route path="/select-avatar" element={<AvatarSelectionPage />} />
```

### 3. 添加路由守卫

**文件**: `frontend/desktop_app/src/components/VideoChat.tsx`

```tsx
const [searchParams] = useSearchParams();
const avatarId = searchParams.get('avatar_id');

useEffect(() => {
  if (!avatarId) {
    navigate('/select-avatar', { replace: true });
  }
}, [avatarId, navigate]);
```

### 4. 修改 API 接口

**文件**: `frontend/desktop_app/src/api/index.ts`

```typescript
export interface OfferPayload {
  sdp: string | undefined;
  type: string | undefined;
  avatar_id: string;  // 新增
}
```

## 后端改动

### 1. 修改 /offer 接口

**文件**: `src/main/app.py`

```python
async def offer(request):
    params = await request.json()

    # 验证 avatar_id 参数
    avatar_id = params.get('avatar_id')
    if not avatar_id:
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "msg": "avatar_id is required"}),
            status=400
        )

    # 验证 avatar 是否存在且就绪
    from services.avatar_manager import get_avatar
    avatar_meta = get_avatar(avatar_id)
    if not avatar_meta or avatar_meta.get('status') != 'ready':
        return web.Response(
            content_type="application/json",
            text=json.dumps({"code": -1, "msg": "Avatar not found or not ready"}),
            status=400
        )
```

### 2. 修改 build_nerfreal 支持按会话加载

**文件**: `src/main/app.py`

```python
def build_nerfreal(sessionid: int, avatar_id: str) -> BaseReal:
    import copy
    opt_copy = copy.copy(opt)
    opt_copy.sessionid = sessionid

    # 按会话加载 avatar
    from lipreal import load_avatar
    session_avatar = load_avatar(avatar_id)

    if opt_copy.model == 'wav2lip':
        from lipreal import LipReal
        nerfreal = LipReal(opt_copy, model, session_avatar)
    # ... 其他模型
    return nerfreal
```

### 3. 修改调用

```python
nerfreal = await asyncio.get_event_loop().run_in_executor(
    None, build_nerfreal, sessionid, avatar_id
)
```

## 数据流

```
┌─────────────────┐
│ AvatarSelection │
│    Page         │
└────────┬────────┘
         │ GET /avatars
         ▼
┌─────────────────┐
│  Backend API    │
│ avatar_manager  │
└────────┬────────┘
         │ 返回 avatar 列表
         ▼
┌─────────────────┐
│  用户点击选择    │
│ avatar_id=abc   │
└────────┬────────┘
         │ navigate /videochat?avatar_id=abc
         ▼
┌─────────────────┐
│  VideoChat 组件  │
└────────┬────────┘
         │ POST /offer { sdp, type, avatar_id: "abc" }
         ▼
┌─────────────────┐
│  Backend /offer │
│  验证 avatar_id │
└────────┬────────┘
         │ load_avatar("abc")
         ▼
┌─────────────────┐
│  会话专属 avatar │
│  加载到内存      │
└────────┬────────┘
         │ WebRTC 连接建立
         ▼
┌─────────────────┐
│  视频会话开始    │
└─────────────────┘
```

## 错误处理

| 场景 | 处理方式 |
|------|----------|
| avatar_id 不存在 | 返回 400，前端提示"Avatar不存在" |
| avatar 状态不是 ready | 返回 400，前端提示"Avatar未就绪" |
| /avatars API 失败 | 显示错误提示，提供重试按钮 |
| 加载 avatar 失败 | 记录日志，返回 500 错误 |

## 文件清单

### 新建文件
- `frontend/desktop_app/src/pages/AvatarSelectionPage.tsx`

### 修改文件
- `frontend/desktop_app/src/api/index.ts`
- `frontend/desktop_app/src/components/VideoChat.tsx`
- `frontend/desktop_app/src/App.tsx`
- `src/main/app.py`

## 兼容性

- 保留全局 `avatar` 变量作为启动时的默认值
- 不影响命令行参数 `--avatar_id` 的作用
- 向后兼容：如果不需要多 avatar 功能，现有流程仍可工作
