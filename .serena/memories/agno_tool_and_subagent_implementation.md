# Agno 工具调用与子代理机制深度分析

## 核心架构总览

Agno的工具调用和子代理机制分两层实现：

1. **工具层（Tool Layer）**：Python函数 → Function模型 → LLM JSON Schema → 执行器
2. **子代理层（Subagent Layer）**：Agent/Team → Function Wrapper → 团队成员工具 → 执行

---

## 第一部分：工具调用机制（Tool Calling）

### 1.1 Python函数到LLM工具的转换流程

#### Step 1: Toolkit 类（`libs/agno/agno/tools/toolkit.py`）

**职责**：组织和注册工具

```python
class Toolkit:
    - functions: Dict[str, Function]  # 同步工具
    - async_functions: Dict[str, Function]  # 异步工具
    - auto_register: bool  # 自动注册所有工具
```

**关键方法**：

1. **`register(function, name=None)`**
   - 处理Function对象（来自@tool装饰器）
   - 处理原始可调用函数
   - 自动检测async函数 via `iscoroutinefunction()`
   - 应用工具包级别的配置（requires_confirmation、stop_after_tool_call等）

2. **`_register_decorated_tool(function, name, is_async)`**
   - 处理@tool装饰的方法（包含self参数）
   - 创建绑定方法并保留装饰器设置
   - 处理装饰器设置的优先级：装饰器 > 工具包配置

#### Step 2: Function 模型（`libs/agno/agno/tools/function.py`）

**职责**：将Python函数转换为LLM可用的工具定义

**关键属性**：
```python
class Function(BaseModel):
    name: str  # 函数名称（a-z, A-Z, 0-9, _, -, max 64 chars）
    description: Optional[str]  # 功能描述（给LLM选择用）
    parameters: Dict[str, Any]  # JSON Schema对象描述参数
    entrypoint: Optional[Callable]  # 实际Python函数
    
    # 执行控制
    show_result: bool  # 执行后显示结果
    stop_after_tool_call: bool  # 执行后停止Agent
    
    # HITL (Human-in-the-Loop) 支持
    requires_confirmation: Optional[bool]  # 需要用户确认
    requires_user_input: Optional[bool]  # 需要用户输入字段
    user_input_fields: Optional[List[str]]  # 用户提供的字段
    user_input_schema: Optional[List[UserInputField]]  # 用户输入架构
    external_execution: Optional[bool]  # 在Agent外部执行
    
    # 钩子
    pre_hook: Optional[Callable]  # 执行前调用
    post_hook: Optional[Callable]  # 执行后调用
    tool_hooks: Optional[List[Callable]]  # 工具调用钩子
    
    # 缓存
    cache_results: bool
    cache_ttl: int
    cache_dir: Optional[str]
```

**JSON Schema生成过程**：

1. **`from_callable(c, name=None, strict=False)`** - 从原始函数创建Function
   
   流程：
   ```
   Python函数
   → 获取签名和类型提示
   → 移除framework参数（agent, team, run_context）
   → 移除媒体参数（images, videos, audios, files）
   → 从docstring解析参数描述
   → 使用get_json_schema()生成JSON Schema
   → 标记需要的参数为required（如果没有默认值）
   → 包装可调用函数 via validate_call()
   ```

2. **`process_entrypoint(strict=False)`** - 处理entrypoint生成最终Schema
   
   特殊处理：
   - 检查是否已设置parameters（用户自定义优先）
   - 如果requires_user_input=True，创建user_input_schema
   - strict=True时：所有properties都是required，additionalProperties=false
   - 应用_wrap_callable()添加Pydantic验证

3. **参数排除逻辑**（重要）：
   ```python
   excluded_params = [
       "return", "agent", "team", "run_context", "self",
       "images", "videos", "audios", "files"
   ]
   # 还排除类型为Agent或Team的参数（即使名称不同）
   ```

4. **Schema Example**:
   ```json
   {
     "type": "object",
     "properties": {
       "query": {"type": "string", "description": "搜索查询"},
       "limit": {"type": "integer", "description": "结果数量"}
     },
     "required": ["query"],
     "additionalProperties": false  // 如果strict=True
   }
   ```

#### Step 3: Agent工具收集 (`libs/agno/agno/agent/_tools.py`)

**`get_tools()` 函数** - 收集所有工具并准备送给LLM

流程：
```
1. 解析callable工具工厂
2. 连接需要连接管理的工具（_requires_connect=True）
3. 收集来自多个来源的工具：
   - 显式提供的工具（agents.tools参数）
   - 内置工具：
     * 聊天历史（read_chat_history）
     * 工具调用历史（read_tool_call_history）
     * 会话历史搜索（search_session_history）
     * 用户记忆更新（enable_agentic_memory）
     * 学习机工具（_learning）
     * 文化知识更新（enable_agentic_culture）
     * 会话状态更新（enable_agentic_state）
   - 知识搜索工具（search_knowledge + knowledge）
   - 知识更新工具（update_knowledge）
   - 技能工具（skills.get_tools()）
```

**`parse_tools()` 函数** - 转换工具为Function对象或字典

处理流程：
```
对每个工具：
1. Dict → 保持原样（LLM原生工具）
2. Toolkit → 提取所有函数并处理
3. Function → 深拷贝并调用process_entrypoint()
4. Callable → 转换为Function via Function.from_callable()

应用配置：
- 设置strict模式（基于output_schema）
- 关联agent引用（func._agent = agent）
- 设置agent的tool_hooks
- 收集媒体（images, videos, audios, files）
```

#### Step 4: 模型响应处理（`libs/agno/agno/agent/_response.py`）

当模型返回tool_calls时的处理流程：

**主循环（Sync）**：
```python
def run(agent, input):
    while True:
        model_response = model.response(messages, tools=_functions)
        
        if model_response.tool_executions:
            for tool_call in model_response.tool_executions:
                # 执行工具
                run_tool(agent, tool_call, functions)
                
                # 处理HITL
                if requires_confirmation:
                    show_for_user_confirmation()
                    if user_confirms:
                        run_tool()
                    else:
                        reject_tool_call()
                
                # 处理外部执行
                if external_execution:
                    pause_until_external_result()
                
                # 处理用户输入
                if requires_user_input:
                    get_user_input_for_fields()
                    run_tool()
        
        if should_continue_loop:
            continue
        else:
            break
```

**`run_tool()` 函数** - 执行单个工具

```
1. 从tool_execution获取function_call
2. 调用model.run_function_call()（由特定Model实现）
   - 通过entrypoint调用Python函数
   - 注入framework参数（agent, team, run_context）
   - 注入媒体参数（images, videos, audios, files）
   - 执行pre_hook（如果定义）
   - 使用validate_call装饰器验证参数
   - 执行函数
   - 执行post_hook（如果定义）
3. 收集结果
4. 创建Message with role="tool"，包含tool_call_id
5. 添加到run_messages供下一轮循环
```

**Tool Call Limit 强制**：
- `agent.tool_call_limit` 限制总调用次数
- 在ResponseLoop中检查并停止
- 跟踪已执行的工具调用计数

### 1.2 Framework参数注入机制

当执行工具函数时，Agno自动注入这些参数（即使函数签名中没有声明）：

```python
# 示例函数
def search_api(query: str, agent: Agent = None, run_context: RunContext = None):
    # agent和run_context由Agno自动注入
    agent.memory_manager.get_memories()
    run_context.session_state
```

**注入逻辑**（在Function.process_entrypoint()）：
1. 检查函数签名中是否有这些参数
2. 从type_hints中移除这些参数
3. 不在JSON Schema中包含这些参数
4. 在执行时注入当前agent/team和run_context实例

### 1.3 工具钩子系统

**三层钩子**：

1. **Function级别** - `pre_hook`, `post_hook`
2. **Toolkit级别** - 在Toolkit构造时为所有工具应用
3. **Agent级别** - `agent.tool_hooks`，应用于所有函数

```python
# 执行顺序
pre_hook(function_call)
→ validate_call装饰器验证参数
→ entrypoint()
→ post_hook(function_call)
```

---

## 第二部分：子代理机制（Subagent / Team Member Calling）

### 2.1 Team架构

**Team 类** (`libs/agno/agno/team/team.py`)

基本属性：
```python
class Team:
    members: Union[List[Union[Agent, "Team"]], Callable]  # 成员列表
    mode: Optional[TeamMode]  # 执行模式
    respond_directly: bool  # 直接返回成员响应
    determine_input_for_members: bool  # 队长是否分析任务
    delegate_to_all_members: bool  # 委托给所有成员
```

**TeamMode 枚举** (`libs/agno/agno/team/mode.py`)

```python
class TeamMode(Enum):
    coordinate = "coordinate"    # 默认：队长选择成员，合成响应
    route = "route"              # 路由到specialist，直接返回
    broadcast = "broadcast"      # 并发委托给所有成员
    tasks = "tasks"              # 自主任务分解和循环
```

### 2.2 成员作为工具的包装（Member as Function）

#### Step 1: 生成委托工具

`_get_delegate_task_function()` (`libs/agno/agno/team/_default_tools.py` 第321-1109行)

创建一个可调用的委托函数，LLM可以用它来调用成员：

```python
def delegate_task_to_member(member_id: str, task: str) -> Iterator[str]:
    """
    使用此函数委托任务给选定的团队成员。
    提供清晰简洁的任务描述和预期输出。
    
    Args:
        member_id: 成员ID
        task: 任务描述
    Returns:
        str: 委托任务的结果
    """
    # 1. 按member_id查找成员
    result = _find_member_by_id(team, member_id, run_context=run_context)
    member_agent = result[1]
    
    # 2. 初始化成员
    _initialize_member(team, member_agent)
    
    # 3. 准备任务
    member_agent_task, history = _setup_delegate_task_to_member(member_agent, task)
    
    # 4. 调用成员agent.run()或agent.arun()
    member_agent_run_response = member_agent.run(
        input=member_agent_task,
        session_id=session.session_id,  # 共享session
        session_state=copy(run_context.session_state),
        images=images,
        videos=videos,
        audio=audio,
        files=files,
        stream=stream,
        ...
    )
    
    # 5. 处理响应并返回
    yield member_agent_run_response.content
```

**三个变体**：
1. `delegate_task_to_member()` - 委托给单个成员（同步）
2. `adelegate_task_to_member()` - 委托给单个成员（异步）
3. `delegate_task_to_members()` / `adelegate_task_to_members()` - 委托给所有成员

#### Step 2: 函数转换为Tool

```python
delegate_func = Function.from_callable(delegate_task_to_member, name="delegate_task_to_member")

# 配置
if team.respond_directly:
    delegate_func.stop_after_tool_call = True
    delegate_func.show_result = True
```

所以LLM看到的是：
```json
{
  "type": "function",
  "function": {
    "name": "delegate_task_to_member",
    "description": "Use this function to delegate a task...",
    "parameters": {
      "type": "object",
      "properties": {
        "member_id": {"type": "string"},
        "task": {"type": "string"}
      },
      "required": ["member_id", "task"]
    }
  }
}
```

#### Step 3: 成员发现和初始化

**`_find_member_by_id()`** - 递归搜索

```python
def _find_member_by_id(team, member_id, run_context=None):
    resolved_members = get_resolved_members(team, run_context)
    
    for i, member in enumerate(resolved_members):
        url_safe_member_id = get_member_id(member)  # 生成URL安全ID
        if url_safe_member_id == member_id:
            return (i, member)  # 返回索引和成员
        
        # 如果成员是Team，递归搜索
        if isinstance(member, Team):
            result = member._find_member_by_id(member_id, run_context)
            if result:
                return result
    
    return None
```

**`_initialize_member()`** - 准备成员运行

- 设置成员数据库连接
- 配置成员会话
- 应用团队设置到成员

#### Step 4: 任务准备（_setup_delegate_task_to_member）

```python
def _setup_delegate_task_to_member(member_agent, task):
    # 1. 初始化成员
    _initialize_member(team, member_agent)
    
    # 2. 继承响应模式
    if team.respond_directly and team output_schema:
        member_agent.output_schema = team_output_schema
    
    # 3. 汇总团队信息
    if team.share_member_interactions:
        team_member_interactions_str = get_team_member_interactions_str()
    
    # 4. 添加历史
    if team.add_team_history_to_members:
        team_history_str = session.get_team_history_context(num_runs=...)
    
    # 5. 确定任务
    if team.determine_input_for_members == False:
        member_agent_task = input  # 使用原始输入
    else:
        member_agent_task = task  # 使用LLM确定的任务
    
    # 6. 格式化任务（含有团队信息）
    if team_history_str or team_member_interactions_str:
        member_agent_task = format_member_agent_task(
            task_description=member_agent_task,
            team_member_interactions_str=team_member_interactions_str,
            team_history_str=team_history_str
        )
    
    # 7. 加载历史
    if member_agent.add_history_to_context:
        history = _get_history_for_member_agent(team, session, member_agent)
    
    return member_agent_task, history
```

### 2.3 数据流：Team输入 → Member调用 → Team使用结果

```
Team.run(input="找出最佳产品")
│
├─ 获取工具（包含delegate_task_to_member）
│
├─ 发送给LLM: "给定这些成员：ProductAnalyst, PriceChecker"
│   LLM回复: 调用delegate_task_to_member(member_id="product-analyst", task="...")
│
├─ 执行delegate_task_to_member():
│   ├─ _find_member_by_id("product-analyst") → ProductAnalyst Agent
│   ├─ 准备任务 + 历史 + 上下文
│   ├─ ProductAnalyst.run(task) ← 完整agent运行
│   │   ├─ ProductAnalyst获取自己的工具
│   │   ├─ ProductAnalyst.model.response(messages, tools)
│   │   ├─ 执行ProductAnalyst的工具调用
│   │   └─ 返回RunOutput
│   └─ 处理响应：
│       ├─ 添加到team_run_context（共享成员交互）
│       ├─ 添加到TeamSession（跟踪）
│       └─ Yield给LLM看
│
├─ 处理HITL暂停（如果成员需要人工输入）
│
└─ Team继续循环，可能调用另一个成员或生成最终响应
```

### 2.4 信息流和共享状态

**Session共享**：
```python
# Team和所有成员共享同一个session_id
member_agent.run(
    session_id=session.session_id,  # ← 同一session
    session_state=copy(run_context.session_state)  # ← 状态拷贝
)
```

**历史访问**：
```python
# 团队成员可以访问所有成员的历史消息
history = session.get_messages(
    last_n_runs=member_agent.num_history_runs,
    limit=member_agent.num_history_messages,
    member_ids=[member_agent_id]  # ← 过滤特定成员
)
```

**Team run context（共享交互）**：
```python
team_run_context = {
    "interactions": [
        {
            "member_name": "ProductAnalyst",
            "task": "分析产品...",
            "response": {...},
            "metrics": {...}
        },
        {
            "member_name": "PriceChecker",
            "task": "检查价格...",
            "response": {...}
        }
    ]
}

# 发送给下一个成员
if team.share_member_interactions:
    member_task += format(team_member_interactions_str)
```

### 2.5 Team执行模式

#### Mode: coordinate（默认）
```
Team Leader决定：
1. 哪个成员最适合
2. 给他什么任务
3. 如何汇总多个成员的响应
```

#### Mode: route
```
Team Leader把请求路由到specialist，直接返回其响应
如果member.respond_directly=True
```

#### Mode: broadcast
```
Team Leader委托同一任务给所有成员（并发）
并发执行（如果async mode）
```

#### Mode: tasks
```
Team Leader把目标分解为独立任务
所有成员共享一个task_list
自主循环直到所有任务完成
需要task management tools (_get_task_management_tools)
```

### 2.6 HITL 在成员调用中

当成员Agent需要用户输入时：

```python
# 成员agent运行
member_agent_run_response = member_agent.run(input)

# 检查暂停状态
if member_agent_run_response.is_paused:
    _propagate_member_pause(run_response, member_agent, member_agent_run_response)
    # Team也暂停，等待成员继续
    yield f"Member '{member_agent.name}' requires human input..."
    return  # 委托函数返回
```

---

## 第三部分：关键配置和优化

### 3.1 Tool Call Limit 强制机制

**`agent.tool_call_limit`** - 限制工具调用总数

强制过程（在响应循环中）：
```python
# 在 _response.py中
tool_call_count = 0
while tool_call_count < agent.tool_call_limit:
    model_response = model.response(...)
    if model_response.tool_executions:
        for tool in model_response.tool_executions:
            run_tool(...)
            tool_call_count += 1
            if tool_call_count >= agent.tool_call_limit:
                break
```

### 3.2 Tool Hooks 执行顺序

对于每个工具调用：

```
1. 创建Function实例（带有tool_hooks）
2. Agent的tool_hooks应用于Function
3. Model的run_function_call执行：
   a. pre_hook(function_call)
   b. validate_call检查参数
   c. entrypoint(*args, **kwargs)
   d. post_hook(function_call)
```

### 3.3 Media 参数注入

对于需要媒体的工具：

```python
# 收集媒体（仅当工具需要时）
if needs_media:
    joint_images = collect_joint_images(run_response.input, session)
    joint_videos = collect_joint_videos(...)
    
    # 注入到Function
    func._images = joint_images
    func._videos = joint_videos
```

### 3.4 缓存机制（Function级别）

```python
# 配置
Function(
    cache_results=True,
    cache_ttl=3600,  # 秒
    cache_dir="/tmp/agno_cache"
)

# 执行时
cache_key = _get_cache_key(entrypoint_args)
cached_result = _get_cached_result(cache_file)
if cached_result and not expired:
    return cached_result
else:
    result = entrypoint(...)
    _save_cached_result(cache_file, result)
    return result
```

---

## 第四部分：完整调用链示例

### 工具调用完整链

```
User: "搜索iPhone价格"
│
├─ Agent准备阶段
│  ├─ get_tools() → [search_api, update_memory, ...]
│  ├─ parse_tools() → Function对象列表
│  └─ determine_tools_for_model() → 最终模型工具列表
│
├─ Model推理
│  └─ model.response(messages, tools=tools_list)
│     → {"tool_calls": [{"name": "search_api", "arguments": {"query": "iPhone"}}]}
│
├─ Tool执行
│  ├─ run_tool(search_api)
│  ├─ function_call = Function.get_function_call_to_run_from_tool_execution()
│  └─ model.run_function_call()
│     ├─ 注入参数：agent=current_agent, run_context=...
│     ├─ 调用pre_hook（如果定义）
│     ├─ 验证参数（validate_call）
│     ├─ 执行search_api(query="iPhone", agent=agent, ...)
│     └─ 调用post_hook（如果定义）
│
├─ 结果处理
│  ├─ 创建Message(role="tool", content=result, tool_call_id=...)
│  ├─ 添加到run_messages
│  └─ 检查stop_after_tool_call标志
│
└─ 继续循环或返回
```

### 子代理调用完整链

```
Team Input: "找出最佳价格"
│
├─ Team准备
│  ├─ get_resolved_members() → [PriceChecker, ...]
│  ├─ _determine_tools_for_model() 创建delegate_task_to_member函数
│  └─ parse_tools() → delegate_task_to_member Function
│
├─ Team LLM推理
│  └─ team_model.response(messages, tools=team_tools)
│     → {"tool_calls": [{"name": "delegate_task_to_member", "arguments": {"member_id": "price-checker", "task": "..."}}]}
│
├─ 委托执行 (run_tool delegate_task_to_member)
│  ├─ _find_member_by_id("price-checker") → PriceChecker Agent
│  ├─ _setup_delegate_task_to_member()
│  │  ├─ 初始化成员
│  │  ├─ 添加团队历史和交互信息
│  │  └─ 准备任务字符串
│  │
│  └─ PriceChecker.run(task) ← 完整agent循环
│     ├─ PriceChecker获取自己的工具（search_prices, compare_vendors等）
│     ├─ PriceChecker.model.response(messages, tools)
│     ├─ 执行PriceChecker的工具调用
│     └─ 返回RunOutput("Amazon: $499, BestBuy: $489")
│
├─ 响应处理
│  ├─ _process_delegate_task_to_member()
│  │  ├─ 设置parent_run_id
│  │  ├─ 添加到team_run_context
│  │  ├─ 添加到session
│  │  └─ 更新team_media
│  └─ Yield给Team Model看
│
├─ Team模型看到:
│  "PriceChecker回复：Amazon: $499, BestBuy: $489"
│
└─ Team继续循环（可能调用另一个成员或生成最终答案）
```

---

## 核心设计洞察

### 1. 分离关注点
- **工具定义** = Function对象（含参数Schema）
- **工具执行** = Model特定的实现（run_function_call）
- **工具编排** = Agent响应循环（何时调用、如何处理结果）

### 2. 对称的Sync/Async设计
- 每个工具有sync和async版本
- Toolkit自动检测并管理两者
- get_async_functions()在async mode中优先使用async版本

### 3. Framework参数注入
- 工具可以访问agent/team而无需显式传参
- JSON Schema中不暴露这些参数（LLM看不到）
- 在执行时自动注入当前实例

### 4. 子代理是工具
- 成员Agent被包装为Function（delegate_task_to_member）
- Team Leader通过调用此工具与成员通信
- 完全隐藏了Agent.run()的复杂性

### 5. 会话隔离与共享
- 每个Agent有独立的消息历史
- 但在Team中共享session_id和session_state
- 会话状态是拷贝的，防止并发修改

### 6. HITL集成深度
- requires_confirmation - 执行前获批准
- requires_user_input - 特定字段需用户提供
- external_execution - 在Agent外部执行
- 成员暂停会传播到Team（Team也暂停）
