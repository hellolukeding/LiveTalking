# 火山引擎 TTS 配置说明

## 当前错误

```
authentication signature from request: 'Authorization' header: invalid auth token
code: 401
backend_code: 45000010
```

## 问题原因

Token 无效或格式不正确。火山引擎 TTS 需要使用**Access Token**进行认证。

## 解决方案

### 方法 1: 获取正确的 Access Token

1. 登录[火山引擎控制台](https://console.volcengine.com/)
2. 进入**语音技术** > **语音合成**
3. 在**API 调用**页面获取正确的 Access Token
4. 更新`.env`文件中的`DOUBAO_TOKEN`

### 方法 2: 使用 API Key + Secret 生成 Token

火山引擎支持使用 API Key 和 Secret 动态生成 Token：

```python
import hashlib
import hmac
import time
import base64

def generate_token(access_key_id, secret_access_key):
    """生成火山引擎Access Token"""
    timestamp = str(int(time.time()))
    string_to_sign = f"{access_key_id}{timestamp}"
    signature = hmac.new(
        secret_access_key.encode('utf-8'),
        string_to_sign.encode('utf-8'),
        hashlib.sha256
    ).digest()
    signature_base64 = base64.b64encode(signature).decode('utf-8')
    return f"{access_key_id};{timestamp};{signature_base64}"
```

### 方法 3: 切换到其他 TTS 服务

如果火山引擎配置困难，可以切换到其他 TTS 服务：

#### Edge TTS (免费，无需配置)

```bash
# .env
TTS_TYPE=edgetts
EDGE_TTS_VOICE=zh-CN-YunxiNeural
```

#### 腾讯 TTS

```bash
# .env
TTS_TYPE=tencent
TENCENT_APPID=your_appid
TENCENT_SECRET_ID=your_secret_id
TENCENT_SECRET_KEY=your_secret_key
```

## 验证配置

修改配置后，运行诊断脚本验证：

```bash
poetry run python diagnose_doubao_connection.py
```

## 火山引擎 TTS 文档

- [单向流式 API 文档](https://www.volcengine.com/docs/6561/1719100)
- [认证说明](https://www.volcengine.com/docs/6561/79820)
- [错误码说明](https://www.volcengine.com/docs/6561/79823)

## 常见错误码

| 错误码   | 说明                   |
| -------- | ---------------------- |
| 401      | 认证失败，Token 无效   |
| 45000010 | Token 格式错误或已过期 |
| 45000011 | AppID 不存在           |
| 45000012 | 服务未开通             |

## 临时解决方案

如果无法立即获取正确的 Token，可以先切换到 Edge TTS：

```bash
# 修改.env文件
TTS_TYPE=edgetts
```

Edge TTS 是微软提供的免费 TTS 服务，无需配置即可使用。
