# 记忆文件格式规范

## profile.md 模板

```markdown
## 基本信息
- 职业: 全栈开发者
- 主力语言: Python, TypeScript

## 技术栈
- 编辑器: VS Code + vim 键位
- 包管理: uv (Python), pnpm (Node)
- 操作系统: macOS + zsh

## 偏好
- 代码风格: 简洁，不写多余注释
- 框架: FastAPI, Next.js
- 测试: pytest, 偏好 TDD
```

## habit.md 模板

```markdown
## 交互偏好
- 回复使用中文
- 直接给方案，少解释
- 不使用 emoji

## 工作模式
- 先写测试再写实现
- 偏好小步提交
- 重构前先确认测试通过

## 常用工具链
- git: 使用 conventional commits
- 部署: Docker + Kubernetes
```

## context.md 模板

```markdown
## 当前任务
重构记忆系统，支持 .md 文件存储

## 进展
- [x] 设计文件结构
- [x] 创建 memory-management skill
- [ ] 迁移存储层

## 关键决策
- 使用 .md 替代 JSON 存储记忆内容
- profile/habit 提升为用户级别，不绑定 session

## 待解决
- 向量索引与 .md 文件的同步机制
```

## 更新规则

### 合并而非追加

当新信息与已有内容相关时，合并到同一条目：

```markdown
# 之前
- 主力语言: Python

# 之后（用户提到也用 TypeScript）
- 主力语言: Python, TypeScript
```

### 按章节组织

同类信息归入同一章节，新类别创建新的二级标题：

```markdown
## 技术栈        ← 已有章节
- 编辑器: vim

## 项目管理      ← 新发现的类别
- 使用 Linear 跟踪任务
```

### 删除过时信息

当用户明确更正时，直接替换旧内容：

```markdown
# 之前
- 框架: Django

# 用户说 "我现在改用 FastAPI 了"
- 框架: FastAPI
```
