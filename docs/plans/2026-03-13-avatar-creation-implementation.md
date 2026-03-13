# Avatar Creation Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Simplify avatar creation by fixing Doubao TTS, adding voice selection with preview, and upgrading to 384x384 resolution.

**Architecture:** Frontend form simplification with fixed TTS, backend using genavatar384.py, WebSocket progress updates, and voice preview API.

**Tech Stack:** React, TypeScript, Ant Design, Python, aiohttp, WebSocket

---

## Task 1: Frontend - Remove TTS Selection and Add Voice Options

**Files:**
- Modify: `frontend/desktop_app/src/pages/AvatarCreatePage.tsx`

**Step 1: Update imports and constants**

Add to existing imports:
```typescript
import { InfoCircleOutlined, SoundOutlined } from '@ant-design/icons';
import { Space } from 'antd';
```

Replace TTS_OPTIONS (lines 15-20) with:
```typescript
// Default Voice ID (温柔淑女)
const DEFAULT_VOICE_ID = 'zh_female_wenroushunshun_mars_bigtts';

// Common voice options for Doubao TTS
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

**Step 2: Add state for voice selection**

After existing state declarations (around line 34), add:
```typescript
const [selectedVoice, setSelectedVoice] = useState(DEFAULT_VOICE_ID);
const [customVoice, setCustomVoice] = useState('');
const [showCustomInput, setShowCustomInput] = useState(false);
```

**Step 3: Replace TTS Select with fixed text display**

Find the TTS Form.Item (around lines 289-303) and replace with:
```typescript
<div style={{ marginBottom: 24 }}>
  <Text style={{ color: '#666', display: 'block', marginBottom: 8, fontSize: 14 }}>
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
  <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 4 }}>
    固定使用豆包语音合成，提供更自然的对话体验
  </Text>
</div>
```

**Step 4: Replace voice_id Form.Item with dropdown + custom input**

Find the voice_id Form.Item (around lines 305-315) and replace with:
```typescript
<Form.Item
  label={
    <span style={{ color: '#666' }}>
      语音音色
      <Tooltip title="点击试听按钮可预览音色效果">
        <InfoCircleOutlined style={{ marginLeft: 4, color: '#999', fontSize: 12 }} />
      </Tooltip>
    </span>
  }
  name="voice_id"
  rules={[{ required: true, message: '请选择语音音色' }]}
  initialValue={DEFAULT_VOICE_ID}
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
      size="large"
    />
  </Space.Compact>
</Form.Item>

{showCustomInput && (
  <div style={{ marginBottom: 24, marginLeft: 8 }}>
    <Text style={{ color: '#666', fontSize: 14, display: 'block', marginBottom: 8 }}>
      自定义 Voice ID
    </Text>
    <Input
      placeholder="输入 Doubao Voice Type ID"
      value={customVoice}
      onChange={(e) => {
        setCustomVoice(e.target.value);
        form.setFieldValue('voice_id', e.target.value);
      }}
      style={{ borderRadius: 8 }}
      size="large"
    />
    <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 4 }}>
      完整音色列表请参考：
      <a href="https://www.volcengine.com/docs/6561/1257544" target="_blank" rel="noopener noreferrer">
        豆包语音音色列表
      </a>
    </Text>
  </div>
)}
```

**Step 5: Update handleSubmit to fix tts_type**

Find handleSubmit function (around line 48) and modify the FormData creation:
```typescript
// Find these lines and modify:
formData.append('avatar_id', autoId);
formData.append('name', values.name);
formData.append('tts_type', 'doubao');  // Changed from values.tts_type
formData.append('voice_id', selectedVoice === '__custom__' ? customVoice : selectedVoice);
formData.append('video', videoFile);
```

**Step 6: Update form initialValues**

Find Form initialValues (around line 209) and remove tts_type:
```typescript
<Form
  form={form}
  layout="vertical"
  initialValues={{ voice_id: DEFAULT_VOICE_ID }}  // Removed tts_type
>
```

**Step 7: Update default ttsType state**

Find ttsType state (line 36) and remove:
```typescript
// Remove this line:
const [ttsType, setTtsType] = useState('edge');

// Also remove any setTtsType calls in onChange handlers
```

**Step 8: Commit**

```bash
git add frontend/desktop_app/src/pages/AvatarCreatePage.tsx
git commit -m "feat: fix TTS to Doubao, add voice selection dropdown"
```

---

## Task 2: Backend - Update avatar_manager.py to use genavatar384.py

**Files:**
- Modify: `src/services/avatar_manager.py`

**Step 1: Update generate_avatar_sync signature**

Find the function definition (line 178) and update default parameters:
```python
def generate_avatar_sync(avatar_id: str, video_path: str, name: str,
                         tts_type: str = "doubao",  # Changed default
                         voice_id: str = "zh_female_wenroushunshun_mars_bigtts"):  # Changed default
```

**Step 2: Update meta creation**

Find the meta dict creation (lines 188-197) and update:
```python
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
```

**Step 3: Update genavatar script path**

Find the genavatar_script assignment (line 201) and update:
```python
# Changed from "genavatar.py" to "genavatar384.py"
genavatar_script = project_root / "wav2lip" / "genavatar384.py"
```

**Step 4: Update img_size parameter**

Find the cmd list (lines 207-213) and update:
```python
cmd = [
    sys.executable,
    str(genavatar_script),
    "--avatar_id", avatar_id,
    "--video_path", video_path,
    "--img_size", "384",  # Changed from "96" to "384"
]
```

**Step 5: Update async wrapper**

Find generate_avatar_async (line 269) and update default parameters:
```python
async def generate_avatar_async(avatar_id: str, video_path: str, name: str,
                                 tts_type: str = "doubao",  # Changed default
                                 voice_id: str = "zh_female_wenroushunshun_mars_bigtts"):  # Changed default
    """In executor thread asynchronously run generate_avatar_sync."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        generate_avatar_sync,
        avatar_id, video_path, name, tts_type, voice_id
    )
```

**Step 6: Update _default_meta**

Find _default_meta function (line 71) and update defaults:
```python
def _default_meta(avatar_id: str, name: str) -> dict:
    return {
        "avatar_id": avatar_id,
        "name": name,
        "tts_type": "doubao",  # Changed from "edge"
        "voice_id": "zh_female_wenroushunshun_mars_bigtts",  # Changed default
        "created_at": datetime.now().isoformat(),
        "status": "ready",
        "error": None,
        "frame_count": 0,
    }
```

**Step 7: Commit**

```bash
git add src/services/avatar_manager.py
git commit -m "feat: use genavatar384.py for 384x384 avatars, fix TTS to doubao"
```

---

## Task 3: Frontend - Add Voice Preview API

**Files:**
- Modify: `frontend/desktop_app/src/api/avatar.ts`
- Modify: `frontend/desktop_app/src/pages/AvatarCreatePage.tsx`

**Step 1: Add previewVoiceTTS function to avatar.ts**

Add to `frontend/desktop_app/src/api/avatar.ts`:
```typescript
export const previewVoiceTTS = async (voiceId: string): Promise<string> => {
  const res = await client.post('/preview_voice', { voice_id }, {
    responseType: 'blob',
    headers: { 'Content-Type': 'application/json' },
  });
  return URL.createObjectURL(new Blob([res.data], { type: 'audio/mpeg' }));
};
```

**Step 2: Import in AvatarCreatePage**

Add to imports in AvatarCreatePage.tsx:
```typescript
import { createAvatar, previewVoiceTTS } from '../api/avatar';
```

**Step 3: Add preview state handlers**

Add after existing state declarations:
```typescript
const [previewLoading, setPreviewLoading] = useState(false);
```

**Step 4: Add preview handler function**

Add before the return statement:
```typescript
const handlePreviewVoice = async (voiceId: string) => {
  if (!voiceId || voiceId === '__custom__' || previewLoading) {
    return;
  }

  setPreviewLoading(true);
  try {
    const audioUrl = await previewVoiceTTS(voiceId);
    const audio = new Audio(audioUrl);
    audio.play();

    audio.onended = () => {
      URL.revokeObjectURL(audioUrl);
    };
  } catch (e) {
    antMessage.error('试听失败: ' + String(e));
  } finally {
    setPreviewLoading(false);
  }
};
```

**Step 5: Add preview button to voice selection**

Update the Space.Compact in the voice_id Form.Item to include preview button:
```typescript
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
    size="large"
  />
  <Button
    icon={<SoundOutlined />}
    onClick={() => handlePreviewVoice(selectedVoice)}
    disabled={selectedVoice === '__custom__' || !selectedVoice || previewLoading}
    loading={previewLoading}
  >
    试听
  </Button>
</Space.Compact>
```

**Step 6: Commit**

```bash
git add frontend/desktop_app/src/api/avatar.ts frontend/desktop_app/src/pages/AvatarCreatePage.tsx
git commit -m "feat: add voice preview functionality"
```

---

## Task 4: Backend - Add Voice Preview API Endpoint

**Files:**
- Modify: `src/main/app.py`

**Step 1: Add preview_voice endpoint**

Add after the avatars endpoints section (around line 1230):
```python
async def preview_voice_tts(request):
    """
    生成音色试听音频
    Returns: Audio data (audio/mpeg)
    """
    try:
        params = await request.json()
        voice_id = params.get('voice_id')

        if not voice_id:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "voice_id is required"}),
                status=400
            )

        # Validate voice_id format
        import re
        if not re.match(r'^[a-zA-Z0-9_\-]+$', voice_id):
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Invalid voice_id format"}),
                status=400
            )

        # Call Doubao TTS service to generate preview audio
        from tts_service import generate_preview_audio

        audio_data = await generate_preview_audio(
            text="你好，我是数字人。",  # Fixed preview text
            voice_id=voice_id
        )

        if not audio_data:
            return web.Response(
                content_type="application/json",
                text=json.dumps({"code": -1, "msg": "Failed to generate audio"}),
                status=500
            )

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

# Add route
appasync.router.add_post('/preview_voice', preview_voice_tts)
```

**Step 2: Create tts_service.py wrapper**

Create `src/tts_service.py`:
```python
"""
TTS Service Wrapper for Doubao
Provides text-to-speech functionality with voice preview support
"""
import aiohttp
import asyncio
from logger import logger

# Doubao TTS configuration
TTS_SERVER_URL = "http://127.0.0.1:9880"  # Default Doubao TTS server

async def generate_preview_audio(text: str, voice_id: str) -> bytes:
    """
    Generate audio using Doubao TTS for voice preview

    Args:
        text: Text to synthesize
        voice_id: Voice type ID

    Returns:
        Audio data as bytes (mp3 format)
    """
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "text": text,
                "voice_type": voice_id,
                "speed": 1.0,
            }

            async with session.post(
                f"{TTS_SERVER_URL}/v1/tts",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status != 200:
                    logger.error(f"[TTS] Request failed: {response.status}")
                    return None

                audio_data = await response.read()
                return audio_data

    except asyncio.TimeoutError:
        logger.error("[TTS] Request timeout")
        return None
    except Exception as e:
        logger.error(f"[TTS] Error: {str(e)}")
        return None


async def generate_speech_async(text: str, voice_id: str = "zh_female_wenroushunshun_mars_bigtts") -> bytes:
    """
    Generate speech for actual conversation use

    Args:
        text: Text to synthesize
        voice_id: Voice type ID

    Returns:
        Audio data as bytes
    """
    return await generate_preview_audio(text, voice_id)
```

**Step 3: Commit**

```bash
git add src/main/app.py src/tts_service.py
git commit -m "feat: add voice preview API endpoint"
```

---

## Task 5: Frontend - Update AvatarListPage for Doubao Labels

**Files:**
- Modify: `frontend/desktop_app/src/pages/AvatarListPage.tsx`

**Step 1: Update TTS_LABELS**

Find TTS_LABELS constant (lines 18-23) and update:
```typescript
const TTS_LABELS: Record<string, string> = {
  doubao: 'Doubao TTS',
  // Removed: edge, tencent, azure
};
```

**Step 2: Commit**

```bash
git add frontend/desktop_app/src/pages/AvatarListPage.tsx
git commit -m "chore: update TTS labels for Doubao only"
```

---

## Task 6: Testing - Manual Testing

**Step 1: Restart backend with new code**

```bash
# Stop existing backend
pkill -f "python src/main/app.py.*8011"

# Start backend
cd /opt/2026/LiveTalking
source .venv/bin/activate
PYTHONPATH=/opt/2026/LiveTalking/src/core:/opt/2026/LiveTalking/src:/opt/2026/LiveTalking/src/utils:/opt/2026/LiveTalking/src/services:/opt/2026/LiveTalking:$PYTHONPATH nohup python src/main/app.py --avatar_id wav2lip256_avatar1 --model wav2lip --listenport 8011 > /tmp/wav2lip384.log 2>&1 &
```

**Step 2: Test avatar creation flow**

1. Navigate to `http://localhost:1420/avatars`
2. Click "新建形象" button
3. Verify:
   - TTS engine shows "Doubao TTS" (fixed, not selectable)
   - Voice dropdown shows common options
   - Custom input appears when "自定义输入..." is selected
   - Preview button plays audio for selected voice

**Step 3: Test avatar creation**

1. Upload a test video
2. Enter name
3. Select voice from dropdown
4. Click "上传并生成数字人形象"
5. Verify:
   - Progress shows correctly
   - Status changes to "ready" after completion
   - New avatar appears in list with Doubao TTS label

**Step 4: Test 384x384 resolution**

Check generated avatar:
```bash
ls -la data/avatars/{new_avatar_id}/face_imgs/
file data/avatars/{new_avatar_id}/face_imgs/00000000.png
# Should show 384x384 resolution
```

**Step 5: Test error cases**

1. Try uploading invalid file format
2. Try with empty name
3. Try without selecting voice
4. Verify proper error messages

---

## Task 7: Documentation - Update AVATAR_GUIDE.md

**Files:**
- Modify: `docs/AVATAR_GUIDE.md`

**Step 1: Update TTS section**

Find the TTS section and update:
```markdown
## TTS Configuration

LiveTalking uses **Doubao TTS** (豆包语音合成) as the default and only TTS engine.

### Supported Voice Types

The system supports 200+ voice types from Doubao TTS. Common voices include:

| Voice Name | Voice Type ID |
|------------|---------------|
| 温柔淑女 (推荐) | zh_female_wenroushunshun_mars_bigtts |
| 阳光青年 | zh_male_yangguangqingnian_mars_bigtts |
| 甜美桃子 | zh_female_tianmeitaozi_mars_bigtts |
| 爽快思思 | zh_female_shuangkuaisisi_moon_bigtts |
| 知性女声 | zh_female_zhixingnvsheng_mars_bigtts |
| 清爽男大 | zh_male_qingshuangnanda_mars_bigtts |

For the complete voice list, see: [豆包语音音色列表](https://www.volcengine.com/docs/6561/1257544)

### Voice Selection

When creating an avatar:
1. Select a voice from the dropdown
2. Click "试听" to preview the voice
3. Or enter a custom Voice Type ID
```

**Step 2: Update resolution section**

```markdown
## Avatar Resolution

All avatars are generated at **384x384** resolution using Wav2Lip384 model for higher quality output.
```

**Step 3: Commit**

```bash
git add docs/AVATAR_GUIDE.md
git commit -m "docs: update guide for Doubao TTS and 384x384 resolution"
```

---

## Task 8: Code Review

**Step 1: Run code-review-pro skill**

Use code-review-pro to review all changed files:
- `frontend/desktop_app/src/pages/AvatarCreatePage.tsx`
- `frontend/desktop_app/src/api/avatar.ts`
- `frontend/desktop_app/src/pages/AvatarListPage.tsx`
- `src/services/avatar_manager.py`
- `src/main/app.py`
- `src/tts_service.py`

**Step 2: Fix any issues found**

Address security, performance, and code quality issues.

**Step 3: Final commit**

```bash
git add -A
git commit -m "fix: address code review feedback"
```

---

## Summary

This implementation plan:

1. **Fixes TTS to Doubao only** - Removes selection, fixes value
2. **Adds voice selection** - Dropdown with 10 common voices + custom input
3. **Adds voice preview** - Click to hear voice before selecting
4. **Upgrades to 384x384** - Uses genavatar384.py for higher quality
5. **Updates all references** - AvatarListPage, documentation

**Total files changed**: 6
- Modified: 5 (AvatarCreatePage.tsx, avatar.ts, AvatarListPage.tsx, avatar_manager.py, app.py)
- New: 1 (tts_service.py)

**Priority**: P0 (required) = Tasks 1, 2, 5, 6
**Priority**: P1 (important) = Tasks 3, 7
**Priority**: P2 (nice to have) = Task 4, 8
