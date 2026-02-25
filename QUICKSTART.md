# 快速开始指南

## 📦 安装步骤

### 1. 验证项目结构

```bash
python verify_setup.py
```

### 2. 安装依赖

```bash
# 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置 API Key

**方式一：配置文件**

```bash
cp omni_agent/config/config-example.yaml omni_agent/config/config.yaml
vim omni_agent/config/config.yaml
```

编辑配置文件，替换 `YOUR_API_KEY_HERE` 为你的实际 API Key。

**方式二：环境变量**

```bash
export LLM_API_KEY="your_api_key_here"
export LLM_API_BASE=""  # 留空使用默认端点
export LLM_MODEL="anthropic/claude-3-5-sonnet-20241022"  # 格式: provider/model
```

**支持的模型格式**：
- 标准格式（推荐）：`anthropic/claude-3-5-sonnet-20241022`
- 自动检测：`claude-3-5-sonnet-20241022` → 自动添加 `anthropic/`
- 旧格式兼容：`openai:gpt-4o` → 自动转换为 `openai/gpt-4o`

### 4. 启动服务

```bash
# 开发模式（带热重载）
uvicorn omni_agent.main:app --reload

# 生产模式
python -m omni_agent.main
```

服务将在 http://localhost:8000 启动。

### 5. 测试 API

**查看 API 文档**

浏览器访问: http://localhost:8000/docs

**使用 Python 测试**

```bash
python examples/test_agent.py
```

**使用 curl 测试**

```bash
./examples/test_curl.sh
```

**手动测试**

```bash
curl -X POST http://localhost:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Create a Python file that prints Hello World",
    "max_steps": 10
  }'
```

## 🎯 常见任务示例

### 创建文件

```json
{
  "message": "Create a Python file named calculator.py with add and subtract functions"
}
```

### 执行命令

```json
{
  "message": "List all Python files in the current directory using ls command"
}
```

### 复杂任务

```json
{
  "message": "Create a REST API client in Python that fetches data from JSONPlaceholder API and saves it to a JSON file"
}
```

## 🔧 支持的 LLM 平台

### Anthropic Claude

```yaml
llm:
  api_key: "sk-ant-..."
  api_base: "https://api.anthropic.com"
  model: "claude-3-5-sonnet-20241022"
```

### MiniMax M2 (Global)

```yaml
llm:
  api_key: "your_minimax_key"
  api_base: "https://api.minimax.io/anthropic"
  model: "MiniMax-M2"
```

### MiniMax M2 (China)

```yaml
llm:
  api_key: "your_minimax_key"
  api_base: "https://api.minimaxi.com/anthropic"
  model: "MiniMax-M2"
```

## 📊 API 响应格式

```json
{
  "success": true,
  "message": "任务完成的结果文本",
  "steps": 3,
  "logs": [
    {
      "type": "step",
      "step": 1,
      "max_steps": 50
    },
    {
      "type": "tool_call",
      "tool": "write_file",
      "arguments": {
        "path": "hello.py",
        "content": "print('Hello')"
      }
    },
    {
      "type": "tool_result",
      "tool": "write_file",
      "success": true,
      "content": "Successfully wrote to /path/to/hello.py"
    }
  ]
}
```

## 🐛 故障排除

### 问题：找不到模块

```bash
# 确保从项目根目录运行
cd skill-agents
python -m omni_agent.main
```

### 问题：API Key 未配置

检查配置文件或环境变量：

```bash
# 检查配置文件
cat omni_agent/config/config.yaml

# 检查环境变量
echo $LLM_API_KEY
```

### 问题：端口被占用

指定其他端口：

```bash
uvicorn omni_agent.main:app --port 8080
```

## 📚 更多信息

- 完整文档: [README.md](README.md)
- API 文档: http://localhost:8000/docs
- 示例代码: [examples/](examples/)

## 🚀 下一步

1. 阅读 [README.md](README.md) 了解详细架构
2. 查看 [examples/](examples/) 了解更多用例
3. 扩展工具系统添加自定义工具
4. 部署到生产环境

祝使用愉快！🎉
