# Avatar Selection Feature Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable per-session avatar selection in the LiveTalking video chat application.

**Architecture:** Create a dedicated avatar selection page that redirects users to VideoChat with avatar_id parameter. Backend /offer endpoint validates and loads the specified avatar for each session independently.

**Tech Stack:** React, React Router, TypeScript, aiohttp, Python

---

## Task 1: Frontend - Create AvatarSelectionPage Component

**Files:**
- Create: `frontend/desktop_app/src/pages/AvatarSelectionPage.tsx`

**Step 1: Create the AvatarSelectionPage component**

```tsx
import { useNavigate } from 'react-router-dom';
import { Card, Col, message, Row, Spin, Tag, Typography } from 'antd';
import { useEffect, useState } from 'react';
import { listAvatars, AvatarMeta } from '../api/avatar';

const { Title, Text } = Typography;

export default function AvatarSelectionPage() {
  const navigate = useNavigate();
  const [avatars, setAvatars] = useState<AvatarMeta[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadAvatars();
  }, []);

  const loadAvatars = async () => {
    try {
      const data = await listAvatars();
      const readyAvatars = data.filter(a => a.status === 'ready');
      setAvatars(readyAvatars);
    } catch (error) {
      message.error('加载头像列表失败');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleSelectAvatar = (avatarId: string) => {
    navigate(`/videochat?avatar_id=${avatarId}`);
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spin size="large" tip="加载中..." />
      </div>
    );
  }

  if (avatars.length === 0) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Title level={3}>暂无可用数字人形象</Title>
        <Text type="secondary">请先在头像管理页面创建形象</Text>
      </div>
    );
  }

  return (
    <div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      <Title level={2}>选择数字人形象</Title>
      <Text type="secondary">点击下方卡片选择要使用的数字人形象</Text>

      <Row gutter={[16, 16]} style={{ marginTop: '24px' }}>
        {avatars.map((avatar) => (
          <Col xs={24} sm={12} md={8} lg={6} key={avatar.avatar_id}>
            <Card
              hoverable
              cover={avatar.image_path ? (
                <div style={{ height: '200px', overflow: 'hidden', background: '#f0f0f0' }}>
                  <img
                    alt={avatar.name}
                    src={`http://localhost:8010${avatar.image_path}`}
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                </div>
              ) : (
                <div style={{ height: '200px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f0f0f0' }}>
                  <Text type="secondary">无预览图</Text>
                </div>
              )}
              onClick={() => handleSelectAvatar(avatar.avatar_id)}
              style={{ cursor: 'pointer' }}
            >
              <Card.Meta
                title={avatar.name}
                description={
                  <div>
                    <Tag color="blue">{avatar.tts_type}</Tag>
                    <div style={{ marginTop: '8px' }}>
                      <Text type="secondary">ID: {avatar.avatar_id}</Text>
                    </div>
                    {avatar.frame_count && (
                      <div>
                        <Text type="secondary">帧数: {avatar.frame_count}</Text>
                      </div>
                    )}
                  </div>
                }
              />
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  );
}
```

**Step 2: Add route to App.tsx**

**Files:**
- Modify: `frontend/desktop_app/src/App.tsx`

Find the Routes component and add:

```tsx
import AvatarSelectionPage from './pages/AvatarSelectionPage';

// Inside <Routes>
<Route path="/select-avatar" element={<AvatarSelectionPage />} />
```

**Step 3: Commit**

```bash
git add frontend/desktop_app/src/pages/AvatarSelectionPage.tsx frontend/desktop_app/src/App.tsx
git commit -m "feat: add AvatarSelectionPage component"
```

---

## Task 2: Frontend - Update API Interface

**Files:**
- Modify: `frontend/desktop_app/src/api/index.ts`

**Step 1: Update OfferPayload interface**

Find the `OfferPayload` interface and add `avatar_id`:

```typescript
export interface OfferPayload {
    sdp: string | undefined;
    type: string | undefined;
    avatar_id: string;  // 新增 avatar_id 参数
}
```

**Step 2: Commit**

```bash
git add frontend/desktop_app/src/api/index.ts
git commit -m "feat: add avatar_id to OfferPayload interface"
```

---

## Task 3: Frontend - Add Route Guard to VideoChat

**Files:**
- Modify: `frontend/desktop_app/src/components/VideoChat.tsx`

**Step 1: Add URL parameter check**

Find the component imports and add:

```tsx
import { useNavigate, useSearchParams } from 'react-router-dom';
```

Inside the `VideoChat` component, after the `navigate` declaration, add:

```tsx
const [searchParams] = useSearchParams();
const avatarId = searchParams.get('avatar_id');

useEffect(() => {
  if (!avatarId) {
    navigate('/select-avatar', { replace: true });
  }
}, [avatarId, navigate]);
```

**Step 2: Update negotiateOffer call to include avatar_id**

Find the `negotiateOffer` call and add `avatar_id` to the payload:

```tsx
// Before:
await negotiateOffer({
  sdp: offer.sdp,
  type: offer.type,
});

// After:
await negotiateOffer({
  sdp: offer.sdp,
  type: offer.type,
  avatar_id: avatarId || '',  // 添加 avatar_id
});
```

**Step 3: Commit**

```bash
git add frontend/desktop_app/src/components/VideoChat.tsx
git commit -m "feat: add route guard and avatar_id to VideoChat"
```

---

## Task 4: Backend - Update /offer Endpoint

**Files:**
- Modify: `src/main/app.py`

**Step 1: Locate the offer function**

The `offer` function is around line 122.

**Step 2: Add avatar_id validation**

Find the line `if not params or 'sdp' not in params or 'type' not in params:` and add avatar_id check after it:

```python
# After the existing params validation:
avatar_id = params.get('avatar_id')
if not avatar_id:
    logger.error("[OFFER] avatar_id is required")
    return web.Response(
        content_type="application/json",
        text=json.dumps({"code": -1, "msg": "avatar_id is required"}),
        status=400
    )

# Validate avatar exists and is ready
from services.avatar_manager import get_avatar
avatar_meta = get_avatar(avatar_id)
if not avatar_meta:
    logger.error(f"[OFFER] Avatar not found: {avatar_id}")
    return web.Response(
        content_type="application/json",
        text=json.dumps({"code": -1, "msg": f"Avatar not found: {avatar_id}"}),
        status=400
    )

if avatar_meta.get('status') != 'ready':
    logger.error(f"[OFFER] Avatar not ready: {avatar_id}, status={avatar_meta.get('status')}")
    return web.Response(
        content_type="application/json",
        text=json.dumps({"code": -1, "msg": f"Avatar not ready: {avatar_id}"}),
        status=400
    )

logger.info(f"[OFFER] Using avatar: {avatar_id}")
```

**Step 3: Commit**

```bash
git add src/main/app.py
git commit -m "feat: add avatar_id validation to /offer endpoint"
```

---

## Task 5: Backend - Modify build_nerfreal for Per-Session Avatar

**Files:**
- Modify: `src/main/app.py`

**Step 1: Update build_nerfreal function signature**

Find the `def build_nerfreal(sessionid: int)` function (around line 100) and modify:

```python
def build_nerfreal(sessionid: int, avatar_id: str) -> BaseReal:
    # 创建副本避免修改全局 opt
    import copy
    opt_copy = copy.copy(opt)
    opt_copy.sessionid = sessionid

    # 按会话加载 avatar（不再使用全局 avatar）
    from lipreal import load_avatar
    session_avatar = load_avatar(avatar_id)
    logger.info(f"[BUILD] Loaded avatar for session {sessionid}: {avatar_id}")

    if opt_copy.model == 'wav2lip':
        from lipreal import LipReal
        nerfreal = LipReal(opt_copy, model, session_avatar)
    elif opt_copy.model == 'musetalk':
        from musereal import MuseReal
        nerfreal = MuseReal(opt_copy, model, session_avatar)
    elif opt_copy.model == 'ultralight':
        from lightreal import LightReal
        nerfreal = LightReal(opt_copy, model, session_avatar)
    return nerfreal
```

**Step 2: Update the offer function call**

Find the line `nerfreal = await asyncio.get_event_loop().run_in_executor(None, build_nerfreal, sessionid)` and update:

```python
# Before:
nerfreal = await asyncio.get_event_loop().run_in_executor(None, build_nerfreal, sessionid)

# After:
nerfreal = await asyncio.get_event_loop().run_in_executor(None, build_nerfreal, sessionid, avatar_id)
```

**Step 3: Commit**

```bash
git add src/main/app.py
git commit -m "feat: support per-session avatar loading in build_nerfreal"
```

---

## Task 6: Testing - Manual Testing

**Step 1: Start the backend server**

```bash
cd /opt/2026/LiveTalking
python src/main/app.py --avatar_id wav2lip384_avatar1
```

**Step 2: Start the frontend**

```bash
cd frontend/desktop_app
npm run dev
```

**Step 3: Test flow**

1. Open browser and navigate to `http://localhost:1420/select-avatar`
2. Verify avatar selection page loads with available avatars
3. Click on an avatar card
4. Verify redirect to `/videochat?avatar_id=<selected_id>`
5. Verify video chat starts successfully
6. Open a second browser tab and select a different avatar
7. Verify both sessions use different avatars simultaneously

**Step 4: Test error cases**

1. Try accessing `/videochat` without `avatar_id` - should redirect to selection page
2. Try passing invalid `avatar_id` - should show error message
3. Try passing `avatar_id` with status not 'ready' - should show error message

---

## Task 7: Code Review

**Step 1: Run code-review-pro skill**

Use the code-review-pro skill to review all changed files:

- `frontend/desktop_app/src/pages/AvatarSelectionPage.tsx`
- `frontend/desktop_app/src/api/index.ts`
- `frontend/desktop_app/src/components/VideoChat.tsx`
- `frontend/desktop_app/src/App.tsx`
- `src/main/app.py`

**Step 2: Fix any issues found**

Address security, performance, and code quality issues identified by the review.

**Step 3: Final commit**

```bash
git add -A
git commit -m "fix: address code review feedback"
```

---

## Task 8: Documentation

**Step 1: Update README if needed**

If there are any user-facing changes, update the README.

**Step 2: Commit documentation**

```bash
git add README.md
git commit -m "docs: update usage documentation for avatar selection"
```

---

## Summary

This implementation plan adds per-session avatar selection functionality:

1. **Frontend**: New AvatarSelectionPage with route guard on VideoChat
2. **API**: Extended OfferPayload to include avatar_id
3. **Backend**: /offer validates avatar_id and loads per-session avatar

**Total files changed**: 5
- New: 1 (AvatarSelectionPage.tsx)
- Modified: 4 (App.tsx, VideoChat.tsx, api/index.ts, app.py)
