#!/bin/bash

echo "========================================="
echo "前端功能测试报告"
echo "========================================="
echo ""

echo "1. 检查前端服务状态..."
if curl -s http://localhost:3001 > /dev/null; then
    echo "   ✅ 前端服务运行中 (http://localhost:3001)"
else
    echo "   ❌ 前端服务无法访问"
    exit 1
fi

echo ""
echo "2. 检查后端服务状态..."
if curl -s http://localhost:8000/health > /dev/null; then
    echo "   ✅ 后端服务运行中 (http://localhost:8000)"
else
    echo "   ❌ 后端服务无法访问"
fi

echo ""
echo "3. 测试后端流式 API..."
echo "   发送测试消息: '请用 Markdown 格式列举你的 3 个主要功能'"
echo ""

response=$(curl -N -s -X POST http://localhost:8000/api/v1/agent/run/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"请用 Markdown 格式简单列举你的 3 个主要功能（用列表形式）", "max_steps":10}' \
  2>&1 | head -100)

if echo "$response" | grep -q "type.*content"; then
    echo "   ✅ 流式输出正常工作"
    echo ""
    echo "   收到的内容示例:"
    echo "$response" | grep "type.*content" | head -3 | sed 's/^/   /'
else
    echo "   ❌ 流式输出异常"
fi

echo ""
echo "========================================="
echo "前端访问地址: http://localhost:3001"
echo "后端访问地址: http://localhost:8000"
echo "========================================="
echo ""
echo "📝 请在浏览器中手动测试以下功能:"
echo ""
echo "   1. ✓ 页面加载和样式"
echo "   2. ✓ 创建新对话"
echo "   3. ✓ 发送消息并查看流式输出"
echo "   4. ✓ Markdown 渲染（标题、列表、代码等）"
echo "   5. ✓ 输入框和按钮对齐"
echo "   6. ✓ 会话切换和删除"
echo ""
