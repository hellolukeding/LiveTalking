#!/bin/bash
# 快速测试脚本

echo "======================================================================"
echo "DoubaoTTS 音频修复快速测试"
echo "======================================================================"

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 测试1: 验证代码修复
echo -e "\n${YELLOW}[测试1]${NC} 验证代码修复..."
python verify_audio_fix.py
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 代码修复验证通过${NC}"
else
    echo -e "${RED}❌ 代码修复验证失败${NC}"
    exit 1
fi

# 测试2: 测试音频流处理
echo -e "\n${YELLOW}[测试2]${NC} 测试音频流处理..."
python test_complete_audio_flow.py
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ 音频流处理测试通过${NC}"
else
    echo -e "${RED}❌ 音频流处理测试失败${NC}"
    exit 1
fi

# 测试3: 诊断DoubaoTTS连接
echo -e "\n${YELLOW}[测试3]${NC} 诊断DoubaoTTS连接..."
python diagnose_doubao_connection.py
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ DoubaoTTS连接正常${NC}"
else
    echo -e "${RED}❌ DoubaoTTS连接失败${NC}"
    echo -e "${YELLOW}提示: 请检查环境变量 DOUBAO_APPID, DOUBAO_TOKEN${NC}"
fi

# 总结
echo ""
echo "======================================================================"
echo -e "${GREEN}所有测试完成！${NC}"
echo "======================================================================"
echo ""
echo "下一步:"
echo "1. 重启应用: python app.py"
echo "2. 测试TTS播放，检查是否有声音和口型"
echo "3. 查看日志: tail -f livetalking.log | grep -E 'DOUBAO|Audio forwarded'"
echo ""
echo "如果仍有问题，请查看: 最新修复说明.md"
echo "======================================================================"
