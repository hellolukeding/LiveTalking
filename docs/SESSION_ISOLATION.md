# 会话进程隔离功能使用说明

## 功能概述

会话进程隔离功能将每个数字人会话运行在独立的子进程中，彻底解决资源泄漏和阻塞问题。

## 启用方法

### 方式1: 环境变量（推荐）

在 `.env` 文件中添加：

```bash
USE_PROCESS_ISOLATION=true
MAX_SESSIONS=10
SESSION_IDLE_TIMEOUT=300
```

### 方式2: 系统环境变量

```bash
export USE_PROCESS_ISOLATION=true
python src/main/app.py --listenport 8011
```

### 方式3: 禁用进程隔离（使用原有模式）

```bash
USE_PROCESS_ISOLATION=false
python src/main/app.py --listenport 8011
```

## API 接口

### 销毁会话接口

```bash
POST /api/session/<session_id>/destroy
Content-Type: application/json
```

**响应示例：**
```json
{
  "code": 0,
  "msg": "Session destroyed"
}
```

### Offer 接口变化

`/offer` 接口返回值新增 `destroy_url` 字段：

```json
{
  "sdp": "...",
  "type": "answer",
  "sessionid": "123456",
  "destroy_url": "/api/session/123456/destroy",
  "code": 0
}
```

## 前端集成

### 断开连接时调用 destroy

```javascript
async function disconnect() {
    // 1. 关闭 WebRTC 连接
    if (pc) {
        pc.close();
        pc = null;
    }

    // 2. 调用 destroy 接口清理会话
    if (sessionId && destroyUrl) {
        try {
            await fetch(destroyUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({})
            });
            console.log('[Disconnect] Session destroyed');
        } catch (e) {
            console.error('[Disconnect] Failed to destroy session:', e);
        }
        sessionId = null;
        destroyUrl = null;
    }
}
```

### 页面关闭前清理

```javascript
window.addEventListener('beforeunload', () => {
    if (sessionId && destroyUrl) {
        navigator.sendBeacon(destroyUrl, JSON.stringify({}));
    }
});
```

## 工作模式对比

### 进程隔离模式（USE_PROCESS_ISOLATION=true）

| 特性 | 说明 |
|------|------|
| 会话隔离 | 每个会话独立进程 |
| 资源清理 | 进程终止自动释放所有资源 |
| 故障隔离 | 单个会话崩溃不影响其他会话 |
| 内存占用 | 每个进程独立占用内存 |
| 启动延迟 | 约100-200ms（进程创建） |

### 原有模式（USE_PROCESS_ISOLATION=false）

| 特性 | 说明 |
|------|------|
| 会话隔离 | 所有会话共享主进程 |
| 资源清理 | 依赖 stop_all_threads() |
| 故障隔离 | 可能影响其他会话 |
| 内存占用 | 共享内存 |
| 启动延迟 | 约50-100ms |

## 监控和调试

### 查看活动会话

```bash
tail -f logs/livetalking.log | grep "Session"
```

### 查看进程

```bash
ps aux | grep livetalking-session
```

### 查看会话状态

```bash
curl http://localhost:8011/api/session/<session_id>/status
```

## 故障排查

### 问题：会话无法创建

**检查项：**
1. 是否达到会话数量限制（MAX_SESSIONS）
2. GPU 内存是否充足
3. avatar 是否存在

### 问题：会话无法销毁

**解决方法：**
1. 检查日志中是否有 "Session destroyed" 消息
2. 查看进程是否被终止：`ps aux | grep <pid>`
3. 必要时手动终止：`kill -9 <pid>`

### 问题：切换模式后服务异常

**解决方法：**
1. 确认配置文件正确
2. 重启服务
3. 查看日志中的错误信息

## 架构说明

```
主进程              子进程 1           子进程 2
├── SessionManager     ├── LipReal         ├── LipReal
├── aiohttp            ├── 渲染线程        ├── 渲染线程
└── HTTP API          └── 音视频队列      └── 音视频队列
                           ↓
                    multiprocessing.Queue
                           ↓
                    QueueMediaTrack
                           ↓
                        WebRTC
```

## 回滚方案

如果遇到问题需要回滚：

```bash
# 方式1: 禁用环境变量
export USE_PROCESS_ISOLATION=false

# 方式2: 切换分支
git checkout main

# 方式3: 还原提交
git revert <commit-hash>
```
