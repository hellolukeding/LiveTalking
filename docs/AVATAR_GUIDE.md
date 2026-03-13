# Avatar Management Guide

This guide explains how to create, manage, and use digital human avatars in LiveTalking.

## Overview

LiveTalking supports multiple digital human avatars that can be used for video conversations. Each avatar is generated from a source video and can be independently selected per conversation session.

## Avatar Selection Workflow

### Web Interface

1. **Navigate to Avatar Selection Page**
   ```
   http://localhost:1420/select-avatar
   ```

2. **Select an Avatar**
   - View all available avatars in grid layout
   - Each card shows preview image, name, TTS type, and frame count
   - Click on an avatar card to select it

3. **Start Video Chat**
   - After selection, you'll be redirected to the video chat page
   - The selected avatar will be used for the conversation

### Route Protection

- Accessing `/videochat` without an `avatar_id` parameter automatically redirects to the selection page
- This ensures every conversation has a valid avatar selected

## Avatar Management API

### List All Avatars

```http
GET /avatars
```

**Response:**
```json
{
  "code": 0,
  "data": [
    {
      "avatar_id": "wav2lip256_avatar1",
      "name": "Wav2Lip256 Avatar1",
      "tts_type": "edge",
      "voice_id": "zh-CN-XiaoxiaoNeural",
      "status": "ready",
      "frame_count": 537,
      "image_path": "/avatars/wav2lip256_avatar1/face_imgs/00000000.png",
      "created_at": "2026-03-10T10:30:00",
      "updated_at": "2026-03-10T10:30:00"
    }
  ]
}
```

### Get Avatar Details

```http
GET /avatars/{avatar_id}
```

**Response:**
```json
{
  "code": 0,
  "data": {
    "avatar_id": "wav2lip256_avatar1",
    "name": "Wav2Lip256 Avatar1",
    "status": "ready",
    ...
  }
}
```

### Create New Avatar

```http
POST /avatars
Content-Type: multipart/form-data
```

**Parameters:**
- `avatar_id`: Unique identifier (optional, auto-generated if not provided)
- `name`: Display name
- `video`: Video file (mp4, mov, avi, webm)
- `tts_type`: TTS engine type (edge, doubao, cosyvoice, etc.)
- `voice_id`: Voice identifier for TTS

**Response:**
```json
{
  "code": 0,
  "data": {
    "avatar_id": "new_avatar_123",
    "status": "creating"
  }
}
```

### Update Avatar Metadata

```http
PUT /avatars/{avatar_id}
Content-Type: application/json
```

**Body:**
```json
{
  "name": "Updated Name",
  "tts_type": "edge",
  "voice_id": "zh-CN-XiaoxiaoNeural"
}
```

### Delete Avatar

```http
DELETE /avatars/{avatar_id}
```

**Response:** `204 No Content`

## Avatar Data Model

| Field | Type | Description |
|-------|------|-------------|
| `avatar_id` | string | Unique identifier (alphanumeric, underscore, hyphen only) |
| `name` | string | Display name |
| `tts_type` | string | TTS engine type |
| `voice_id` | string | Voice identifier for TTS |
| `status` | string | `creating` \| `ready` \| `error` |
| `frame_count` | number | Number of frames in the avatar |
| `image_path` | string \| null | Preview image URL |
| `created_at` | string | ISO 8601 timestamp |
| `updated_at` | string | ISO 8601 timestamp (optional) |

## Avatar Storage

Avatars are stored in the following directory structure:

```
data/avatars/{avatar_id}/
├── full_imgs/         # Full frame images
│   ├── 00000000.png
│   ├── 00000001.png
│   └── ...
├── face_imgs/         # Cropped face images
│   ├── 00000000.png
│   ├── 00000001.png
│   └── ...
├── coords.pkl         # Face coordinates (pickle format)
└── meta.json          # Avatar metadata
```

## WebRTC Integration

The `/offer` endpoint now requires an `avatar_id` parameter:

```javascript
const response = await fetch('/offer', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    sdp: sessionDescription.sdp,
    type: sessionDescription.type,
    avatar_id: 'wav2lip256_avatar1'  // Required
  })
});
```

**Validation:**
- `avatar_id` is required
- Must match format: `^[a-zA-Z0-9_-]+$`
- Maximum length: 64 characters
- Avatar must exist and have status `ready`

**Error Responses:**

| Error | Code | Message |
|-------|------|---------|
| Missing avatar_id | 400 | "avatar_id is required" |
| Invalid format | 400 | "Invalid avatar_id format" |
| Not found | 400 | "Avatar not found: {id}" |
| Not ready | 400 | "Avatar not ready: {id}" |

## Creating Avatars from Video

### Using genavatar384.py

For 384x384 resolution avatars:

```bash
cd /opt/2026/LiveTalking
python wav2lip/genavatar384.py \
  --video_path /path/to/source/video.mp4 \
  --avatar_id my_new_avatar \
  --img_size 384
```

### Using genavatar.py

For 96x96 resolution avatars:

```bash
python wav2lip/genavatar.py \
  --video_path /path/to/source/video.mp4 \
  --avatar_id my_new_avatar
```

### Output

The generated avatar will be saved to `data/avatars/{avatar_id}/` with:
- Face images at the specified resolution
- Face coordinates for animation
- Metadata file

## Troubleshooting

### Avatar Not Showing in Selection Page

1. Check avatar status is `ready` (not `creating` or `error`)
2. Verify `data/avatars/{avatar_id}/meta.json` exists
3. Check server logs for errors

### Avatar Selection Redirects Immediately

- This happens if no `avatar_id` is provided in the URL
- Ensure you're accessing `/videochat?avatar_id={id}` or using the selection page

### "Avatar Not Ready" Error

- The avatar is still being generated (status: `creating`)
- Wait for generation to complete
- Check server logs for generation errors

## Security Considerations

1. **Avatar ID Validation**: All avatar_id parameters are validated to prevent path traversal attacks
2. **File Upload Restrictions**: Only specific video file types are allowed (mp4, mov, avi, webm)
3. **Access Control**: Avatar images are served with path validation

## Future Enhancements

- [ ] Avatar preview with animation
- [ ] Batch avatar creation
- [ ] Avatar search and filtering
- [ ] Avatar categories/tags
- [ ] Avatar usage analytics
