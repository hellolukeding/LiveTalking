# LiveTalking 项目结构说明

## 整理后的目录结构

```
LiveTalking/
├── src/                          # 核心源代码
│   ├── core/                     # 核心运行时组件
│   │   ├── basereal.py          # 基础实时处理类
│   │   ├── ttsreal.py           # TTS实时处理
│   │   ├── lightreal.py         # 轻量级实时处理
│   │   ├── lipreal.py           # 唇形同步实时处理
│   │   ├── musereal.py          # MuseTalk实时处理
│   │   ├── hubertasr.py         # Hubert ASR
│   │   ├── lipasr.py            # 唇形同步ASR
│   │   ├── museasr.py           # Muse ASR
│   │   ├── tencentasr.py        # 腾讯ASR
│   │   ├── baseasr.py           # 基础ASR类
│   │   └── webrtc.py            # WebRTC相关
│   ├── llm/                     # 大语言模型
│   │   └── llm.py               # LLM接口
│   ├── utils/                   # 工具类
│   │   ├── logger.py            # 日志工具
│   │   └── system_prompt.py     # 系统提示词
│   ├── services/                # 服务集成 (待开发)
│   └── main/                    # 主入口
│       ├── app.py               # Flask应用入口
│       ├── start_quick.py       # 快速启动脚本
│       ├── genavatar_musetalk.py # MuseTalk头像生成
│       └── verify_audio_fix.py  # 音频修复验证
├── tests/                       # 测试代码
│   ├── unit/                    # 单元测试
│   │   ├── test_tts_simple.py
│   │   ├── test_tts_local_playback.py
│   │   ├── test_tts_complete_flow.py
│   │   └── test_tencent_asr/    # 腾讯ASR测试
│   ├── integration/             # 集成测试
│   │   ├── test_tencent_asr_integration.py
│   │   ├── test_tencent_asr.py
│   │   └── test_tencent_simple.py
│   ├── optimization/            # 优化测试
│   │   ├── audio_fix/           # 音频修复测试
│   │   ├── connection/          # 连接优化测试
│   │   ├── codec/               # 编解码测试
│   │   ├── final_verification/  # 最终验证
│   │   ├── debug/               # 调试工具
│   │   └── (其他优化测试文件)
│   └── fixtures/                # 测试数据
├── docs/                        # 文档
│   ├── guides/                  # 使用指南
│   ├── configuration/           # 配置说明
│   ├── troubleshooting/         # 问题排查
│   └── architecture/            # 架构文档
├── frontend/                    # 前端应用
│   ├── desktop_app/             # Tauri桌面应用
│   └── web/                     # Web前端
├── assets/                      # 静态资源
├── models/                      # 模型文件
├── scripts/                     # 脚本工具
├── data/                        # 数据文件
├── demo/                        # 演示代码
├── ultralight/                  # 轻量级模型
├── wav2lip/                    # Wav2Lip模型
├── musetalk/                    # MuseTalk模型
├── .env                         # 环境变量
├── pyproject.toml              # Poetry配置
├── poetry.lock                 # 依赖锁定
├── requirements.txt            # Pip依赖
├── Dockerfile                  # Docker配置
├── .gitignore                  # Git忽略
├── LICENSE                     # 许可证
└── README.md                   # 项目说明 (建议移到 docs/guides/)
```

## 主要变化

### 1. 代码组织

- **src/core/**: 所有核心运行时代码
- **src/llm/**: LLM 相关代码
- **src/utils/**: 工具类
- **src/main/**: 应用入口和启动脚本

### 2. 测试组织

- **tests/unit/**: 单元测试
- **tests/integration/**: 集成测试
- **tests/optimization/**: 性能优化测试
- **tests/fixtures/**: 测试数据

### 3. 文档组织

- **docs/guides/**: 使用指南和快速开始
- **docs/configuration/**: 配置说明
- **docs/troubleshooting/**: 问题排查和修复记录
- **docs/architecture/**: 架构设计文档

### 4. 前端组织

- **frontend/desktop_app/**: Tauri 桌面应用
- **frontend/web/**: Web 前端

## 文件移动清单

### 已移动到 src/core/

- basereal.py, ttsreal.py, lightreal.py, lipreal.py
- musereal.py, hubertasr.py, lipasr.py, museasr.py
- tencentasr.py, baseasr.py, webrtc.py

### 已移动到 src/llm/

- llm.py

### 已移动到 src/utils/

- logger.py, system_prompt.py

### 已移动到 src/main/

- app.py, start_quick.py
- genavatar_musetalk.py, verify_audio_fix.py

### 已移动到 tests/

- test\_\*.py → tests/unit/
- test/ → tests/integration/
- test_optimization/ → tests/optimization/

### 已移动到 docs/

- README.md, README-EN.md, 快速测试指南.md → docs/configuration/
- 火山引擎 TTS 配置说明.md, DEPLOYMENT_GUIDE.md → docs/configuration/
- 音频修复相关文档 → docs/troubleshooting/
- WEBSOCKET 优化文档 → docs/architecture/

### 已移动到 frontend/

- desktop_app/, web/

## 后续步骤

1. **更新导入路径**: 需要更新所有文件的导入语句以适应新结构
2. **更新配置文件**: 更新 pyproject.toml 中的脚本路径
3. **更新文档引用**: 更新 README 中的文件路径引用
4. **清理临时文件**: 移除 **pycache** 和 .venv (可选)

## 注意事项

- 某些文件如 models/, musetalk/, wav2lip/, ultralight/ 保持原位，因为它们可能是模型或第三方库
- assets/, data/, scripts/ 保持原位，作为项目资源
- Dockerfile 和 CI/CD 配置保持原位
