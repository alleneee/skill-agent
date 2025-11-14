# FastAPI Agent Frontend

基于 React + TypeScript + Tailwind CSS 构建的 FastAPI Agent Web 前端，提供 ChatGPT 风格的对话界面。

## 功能特性

- ✅ **实时流式对话** - 使用 SSE 实时显示 Agent 的思考过程和回复
- ✅ **会话管理** - 支持创建、切换、删除会话，数据存储在浏览器 LocalStorage
- ✅ **工具调用可视化** - 显示 Agent 调用的工具及执行结果
- ✅ **执行状态监控** - 实时显示步骤进度和 Token 使用情况
- ✅ **ChatGPT 风格 UI** - 简洁美观的聊天界面

## 技术栈

- **框架**: React 18 + TypeScript
- **构建工具**: Vite
- **状态管理**: Zustand
- **HTTP 客户端**: Axios
- **样式**: Tailwind CSS
- **Markdown**: react-markdown
- **图标**: lucide-react

## 快速开始

### 安装依赖

```bash
npm install
```

### 启动开发服务器

```bash
npm run dev
```

访问 http://localhost:3000

### 构建生产版本

```bash
npm run build
```

## 使用说明

### 1. 新建对话

点击左侧边栏的"新对话"按钮创建新会话。

### 2. 发送消息

在输入框输入消息，支持：
- 点击发送按钮
- 按 Cmd/Ctrl + Enter 快捷键

### 3. 查看实时输出

- **思考过程**: 点击"思考过程..."可展开查看
- **流式内容**: 回复内容逐字显示
- **工具调用**: 显示工具调用及执行结果
- **执行状态**: 顶部状态栏显示步骤和 Token 使用

### 4. 会话管理

- **切换会话**: 点击左侧会话列表
- **删除会话**: 悬停后点击垃圾桶图标

## 项目结构

```
frontend/
├── src/
│   ├── pages/Chat.tsx          # 主聊天页面
│   ├── services/               # API 服务层
│   ├── stores/                 # Zustand 状态管理
│   ├── types/                  # TypeScript 类型
│   ├── hooks/                  # 自定义 Hooks
│   └── utils/                  # 工具函数
├── package.json
└── vite.config.ts
```

## 后续改进

- [ ] 会话搜索功能
- [ ] 会话标题编辑
- [ ] 导出会话
- [ ] 代码高亮
- [ ] 暗色主题
- [ ] 移动端优化

---

**技术支持**: 查看浏览器控制台错误信息，或检查后端服务运行状态。
