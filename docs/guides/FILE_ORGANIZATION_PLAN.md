# 文件整理方案

## 当前问题

根目录文件过多，缺乏组织，包括：

- 大量测试文件散落在根目录
- 文档文件分散
- 核心代码与测试代码混合
- 优化相关的文件分散在多个目录

## 整理方案

### 1. 核心代码目录结构

```
src/
├── core/           # 核心运行时代码
│   ├── basereal.py
│   ├── ttsreal.py
│   ├── lightreal.py
│   ├── lipreal.py
│   ├── musereal.py
│   ├── hubertasr.py
│   ├── lipasr.py
│   ├── museasr.py
│   ├── tencentasr.py
│   ├── baseasr.py
│   └── webrtc.py
├── llm/            # LLM相关
│   └── llm.py
├── utils/          # 工具类
│   ├── logger.py
│   └── system_prompt.py
├── services/       # 服务集成
│   └── (特定服务的封装)
└── main/           # 主入口
    ├── app.py
    └── start_quick.py
```

### 2. 测试目录整理

```
tests/
├── unit/           # 单元测试
│   ├── test_tts_simple.py
│   ├── test_tts_local_playback.py
│   ├── test_tts_complete_flow.py
│   └── test_tencent_asr/
├── integration/    # 集成测试
│   ├── test_tencent_asr_integration.py
│   └── test_tencent_asr.py
├── optimization/   # 优化测试 (合并 test_optimization 和 tests/debug)
│   ├── audio_fix/
│   ├── connection/
│   ├── codec/
│   └── final_verification/
└── fixtures/       # 测试数据
```

### 3. 文档整理

```
docs/
├── guides/         # 使用指南
│   ├── README.md
│   ├── README-EN.md
│   ├── 快速测试指南.md
│   └── 快速测试指南.md
├── configuration/  # 配置说明
│   ├── 火山引擎TTS配置说明.md
│   └── DEPLOYMENT_GUIDE.md
├── troubleshooting/ # 问题排查
│   ├── 音频修复说明.md
│   ├── 音频修复完成.md
│   ├── 最新修复说明.md
│   ├── AUDIO_FIX_SUMMARY.md
│   ├── NOISE_FIX_COMPLETE.md
│   ├── 修复完成总结.md
│   └── SOLUTION_SUMMARY.md
└── architecture/   # 架构文档
    └── WEBSOCKET_OPTIMIZATION_GUIDE.md
```

### 4. 前端和资源

```
frontend/
├── desktop_app/    # Tauri桌面应用
└── web/            # Web前端

assets/             # 静态资源 (保持不变)
models/             # 模型文件 (保持不变)
scripts/            # 脚本工具 (保持不变)
```

### 5. 需要清理的文件

- 临时测试文件
- 重复的功能测试
- 调试日志文件
- 过时的修复脚本

## 执行步骤

1. 创建目标目录结构
2. 移动核心代码文件
3. 整理测试文件
4. 整理文档
5. 清理临时文件
6. 更新配置和引用
