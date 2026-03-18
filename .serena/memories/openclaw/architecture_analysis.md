# OpenClaw Agent Architecture Analysis

## 1. AGENT EXECUTION LOOP (pi-embedded-runner.ts → run.ts)

### Core Loop Pattern
The main agent execution loop in `runEmbeddedPiAgent()` implements a **multi-layered retry architecture**:

```
Session → Global Lane Queue
    ↓
Workspace Initialization
    ↓
Model Resolution (with plugin hooks: before_model_resolve, before_agent_start)
    ↓
Context Window Guard (check min/warn thresholds)
    ↓
Auth Profile Resolution (with cooldown handling)
    ↓
Outer Loop: Run Retry Iterations (BASE_RUN_RETRY_ITERATIONS=24 + 8 per profile, max 160)
    ├─ Profile Failover Loop (per auth profile candidate)
    │  ├─ Think Level Fallback Loop (attempt progressive simplification)
    │  │  └─ Inner Attempt Loop (runEmbeddedAttempt)
    │  │     ├─ API Call with CompactionSafetyTimeout
    │  │     ├─ Tool Execution Loop (until max_steps or completion)
    │  │     └─ Usage Accumulation (cache-aware)
    │  └─ On failure: classify + failover
    └─ On success: return result

Result: EmbeddedPiRunResult (with aggregated usage, messages, final status)
```

### Key Design Decisions:
1. **Defensive Retry Stacking**: Multiple fallback layers (auth profiles, thinking levels, model resolution)
2. **Workspace Queuing**: Commands enqueued per session and globally to prevent concurrent execution
3. **Cache-Aware Usage**: Uses LAST API call's cache fields (not accumulated) to avoid context inflation
4. **API Key Resolution**: Dynamic auth profile rotation during failures
5. **Compaction Safety Timeout**: Prevents runaway summarization attempts

### Error Classification
Failures trigger automatic failover based on:
- `isAuthAssistantError` → rotate auth profile
- `isCompactionFailureError` → trigger overflow compaction
- `isLikelyContextOverflowError` → compaction first, then failover
- `isTimeoutErrorMessage` → think level fallback
- `isRateLimitAssistantError` → mark profile in cooldown

---

## 2. CONTEXT WINDOW MANAGEMENT & COMPACTION (compaction.ts)

### Token Estimation & Sanitization
- **Safe Estimation**: `estimateMessagesTokens()` strips `toolResult.details` (untrusted payloads)
- **Tokenization**: Uses `cl100k_base` encoding via `estimateTokens()` (from pi-coding-agent)
- **Safety Margin**: Applied multiplier = 1.2 (20% buffer for estimation inaccuracy)

### Multi-Stage Summarization Strategy

#### 1. **Chunking by Token Share** (`splitMessagesByTokenShare`)
   - Divides messages into N parts by equal token distribution
   - Ensures balanced chunks for parallel summarization
   - Default: 2 parts, normalized to 1-messageCount range

#### 2. **Chunking by Max Tokens** (`chunkMessagesByMaxTokens`)
   - Enforces absolute token ceiling per chunk
   - Applies safety margin before enforcement
   - Splits oversized messages to prevent unbounded chunk growth

#### 3. **Adaptive Chunk Ratio** (`computeAdaptiveChunkRatio`)
   - Reduces chunk ratio when average message > 10% of context
   - Base: 0.4 (40% of context), Min: 0.15 (15%)
   - Formula: `reduction = min(avgRatio × 2, BASE - MIN)`

#### 4. **Three-Tier Summarization** (`summarizeInStages`)
   - **Tier 1**: Full summarization with multi-chunk strategy
   - **Tier 2** (fallback): Partial summarization (exclude oversized messages, annotate)
   - **Tier 3** (final fallback): Just note message count and oversized status
   - Large message threshold: > 50% of context window

### Context Pruning (`pruneHistoryForContextShare`)
- Removes oldest chunks until history fits budget
- Default budget: 50% of maxContextTokens
- **Tool Result Repair**: After dropping chunk, removes orphaned `tool_result` messages (whose `tool_use` was dropped)
- Prevents "unexpected tool_use_id" errors from LLM API

### Overhead Constants
- `SUMMARIZATION_OVERHEAD_TOKENS = 4096`: Reserved for summary prompt + instructions + system prompt
- Applied when calculating max chunk tokens: `maxChunkTokens = maxTokens - SUMMARIZATION_OVERHEAD_TOKENS`

---

## 3. CONTEXT WINDOW GUARD (context-window-guard.ts)

### Resolution Hierarchy
Resolves final context window in priority order:
1. **modelsConfig** (from `cfg.models.providers[provider].models[id].contextWindow`)
2. **Model Definition** (from model object's contextWindow)
3. **Config Override** (`cfg.agents.defaults.contextTokens` caps everything)
4. **Default** (128k tokens)

### Guard Evaluation
```typescript
ContextWindowGuardResult {
  tokens: number           // Final resolved window
  source: ContextWindowSource  // Where it came from
  shouldWarn: boolean      // tokens < 32k
  shouldBlock: boolean     // tokens < 16k (hard min)
}
```

### Design Pattern
- **Graceful Degradation**: Warn at 32k, block at 16k
- **Configuration Cascading**: Local overrides > model defaults > global defaults
- **Zero-Failure Design**: Even with invalid config, returns safe defaults

---

## 4. SYSTEM PROMPT COMPOSITION (system-prompt.ts)

### Prompt Modes
- **"full"**: All sections (main agent)
- **"minimal"**: Reduced sections (Tooling, Workspace, Runtime only; for subagents)
- **"none"**: Just basic identity line

### Core Sections (Conditional)
1. **Tooling** (always): Tool list with descriptions + tool call style guidance
2. **Tool Call Style**: Guidance on narration (avoid routine, narrate complex/sensitive)
3. **Safety**: Self-preservation guards, no manipulation, no prompt hijacking
4. **Skills** (if configured): Skill scanning + read protocol
5. **Memory Recall** (if tools available): Memory search + memory get + citation guidance
6. **OpenClaw CLI** (always): Gateway subcommands, self-update restrictions
7. **Model Aliases** (if configured): Provider/model format hints
8. **Workspace**: Working directory + guidance for sandbox vs host
9. **Documentation** (if docs path): Links to docs, Discord, clawhub
10. **Sandbox** (if enabled): Explanation of sandbox constraints, browser/elevated access
11. **User Identity** (if owner numbers): Authorized senders with hash/raw display
12. **Time Zone** (if configured): Current date/time guidance
13. **Reactions** (if enabled): Minimal vs extensive reaction guidance
14. **Reasoning Format** (if thinking enabled): `<think>...</think><final>...</final>` structure
15. **Project Context** (if context files): Loads SOUL.md (for persona) + other .md files
16. **Silent Replies** (full mode): Response with only token when nothing to say
17. **Heartbeats** (full mode): Heartbeat polling + HEARTBEAT_OK response
18. **Runtime Info**: Agent ID, host, OS, node, model, shell, channel, capabilities, thinking level

### Tool Management
- **Tool Names Deduped** by lowercase, preserves caller casing
- **Tool Ordering**: Priority order (read, write, edit, etc.) then extras sorted
- **Tool Summaries**: Core tool descriptions + custom tool descriptions from params
- **External Tools**: Plugins/custom tools appended after core tools

### Dynamic Building Functions
- `buildSkillsSection()`: Conditional skill metadata
- `buildMemorySection()`: Memory recall + citations mode
- `buildMessagingSection()`: message tool + channel routing + inline buttons + message tool hints
- `buildVoiceSection()`: TTS hints (if enabled)
- `buildDocsSection()`: Docs path + links
- `buildReplyTagsSection()`: [[reply_to_current]] tags
- `buildUserIdentitySection()`: Owner identity with hash/raw display

### Key Design: Modular Section Building
All sections use guard functions that return empty array if condition not met, then filtered and joined.
Supports easy addition of new conditional sections without complex nesting.

---

## 5. SUBAGENT SYSTEM (subagent-spawn.ts, subagent-depth.ts, subagent-registry.ts)

### Spawn Flow: `spawnSubagentDirect()`

```
1. Validate Depth Limit
   - Load parent depth from session store
   - Fail if parentDepth >= maxSpawnDepth (default 3)

2. Validate Active Child Limit
   - Count active runs for requester session
   - Fail if activeChildren >= maxChildren (default 5)

3. Resolve Target Agent & Model
   - Allowlist check (allowAgents config)
   - Model selection (override or agent default)
   - Thinking level validation (normalize + error if invalid)

4. Create Child Session
   - Generate UUID: `agent:{targetAgentId}:subagent:{randomUUID()}`
   - Patch session via gateway: spawnDepth, model, thinkingLevel
   - Bind to thread (if mode="session" + thread=true)

5. Build Child System Prompt
   - Indicate subagent role + depth display
   - Build task context with require "do not poll"

6. Invoke Child via Gateway
   - Call `gateway.agent()` with:
     * message: child task
     * lane: AGENT_LANE_SUBAGENT
     * idempotencyKey: childIdem
     * deliver: false (don't deliver to user, auto-announce on completion)
     * spawnedBy: parentSessionKey
     * groupId/groupChannel/groupSpace: inherit from parent

7. Register + Lifecycle
   - Register run in subagent registry
   - Fire subagent_spawned hook (plugin notification)
   - Return status="accepted" with childSessionKey + runId
```

### Spawn Modes
- **"run"**: One-shot execution, auto-cleanup on completion
- **"session"**: Persistent session (requires thread=true), stays active for follow-ups

### Depth Tracking: `getSubagentDepthFromSessionStore()`
Recursive depth calculation:
```
1. Try direct lookup in session store by sessionKey
2. If spawnedBy field exists, recursively resolve parent depth + 1
3. Fallback to parsing sessionKey for embedded depth marker
4. Visited set prevents infinite loops from circular references
```

### Registry: `subagent-registry.ts`
In-memory + disk-persisted registry of active/completed runs:
- **Announce Queue**: Retries with exponential backoff (1s → 8s max, 3 attempts)
- **Cleanup**: Deferred cleanup (keep/delete session) based on spawn mode
- **Lifecycle Hooks**: subagent_spawned, subagent_ended (with reasons: complete, error, killed)
- **Completion Detection**: Automatic announcement when child completes
- **Orphan Detection**: Marks runs whose sessions were deleted externally

---

## 6. TOOL POLICY SYSTEM (tool-policy.ts, tool-policy-pipeline.ts)

### Policy Resolution Pipeline

**Steps (in order):**
1. `tools.profile` (current profile name) → strip plugin-only
2. `tools.byProvider.profile` (provider-specific profile) → strip plugin-only
3. `tools.allow` (global allowlist) → strip plugin-only
4. `tools.byProvider.allow` (provider-specific allowlist) → strip plugin-only
5. `agents.{agentId}.tools.allow` (agent-specific allowlist) → strip plugin-only
6. `agents.{agentId}.tools.byProvider.allow` (agent-provider-specific) → strip plugin-only
7. `group tools.allow` (group-level allowlist)

Each step **filters** cumulative result through its policy.

### Owner-Only Tools
Tools restricted by `ownerOnly=true` property or name:
- `whatsapp_login`, `cron`, `gateway` are fallback owner-only names
- Non-owner senders: tool filtered out
- Filtered senders: tool wrapped with execution guard throwing "Tool restricted to owner senders."

### Plugin Tool Groups
Enables:
- `group:plugins` expansion (expands to all plugin tools)
- `{pluginId}` expansion (expands to all tools from that plugin)

### Tool Name Deduplication
- Normalized (lowercase) for matching
- Preserves caller casing in tool definitions
- Deduped by Set

### Allowlist Stripping Logic
When an allowlist contains **only plugin tools** (no core tools):
- Stripped to undefined (prevents accidentally disabling core tools)
- Warning logged with suggestion to use `tools.alsoAllow` for additive behavior
- Configurable per pipeline step with `stripPluginOnlyAllowlist` flag

---

## 7. TOOL LOOP DETECTION (tool-loop-detection.ts)

### Detection Strategy: Multi-Level Detector

**Sliding Window**: Keeps last 30 tool calls (TOOL_CALL_HISTORY_SIZE)

**Records**:
```typescript
type ToolCallRecord = {
  toolName: string
  argsHash: string        // SHA256 of deterministic JSON
  resultHash?: string     // SHA256 of result outcome
  toolCallId?: string
  timestamp: number
}
```

### Four Detectors (configurable):

#### 1. **Generic Repeat** (genericRepeat detector)
- Tracks identical tool + args calls
- Warning at 10 repeats (WARNING_THRESHOLD)
- Only warns; doesn't block
- Applies to all tools

#### 2. **Known Poll No-Progress** (knownPollNoProgress detector)
- Targets `command_status`, `process(action=poll|log)`
- Tracks: same args + identical result hash
- Warning at 10 repeats
- Critical block at 20 repeats (CRITICAL_THRESHOLD)
- Message: "Stop polling and increase wait time or report as failed"

#### 3. **Ping-Pong** (pingPong detector)
- Detects alternating tool calls: A→B→A→B→...
- Requires: stable outcomes on both sides (same result hashes)
- Warning at 10 alternations
- Critical block at 20 alternations
- Message: "Stop retrying, this looks like a ping-pong loop"

#### 4. **Global Circuit Breaker** (always active if enabled)
- Hard block at 30 repeats with NO progress (GLOBAL_CIRCUIT_BREAKER_THRESHOLD)
- Prevents infinite loops across all detectors
- Level: critical
- Blocks session execution

### Hash Functions
```
hashToolCall(toolName, params):
  → "{toolName}:{digestStable(params)}"
  → Uses sorted JSON keys for deterministic serialization

hashToolOutcome(toolName, params, result, error):
  → For process(action=poll): hashes status, exitCode, exitSignal, aggregated, text
  → For process(action=log): hashes status, totalLines, totalChars, truncated, exitCode, text
  → For command_status: digests full result
  → For others: digests result.details + text content
  → Errors: hashes formatted error message
```

### Streak Calculation
```
getNoProgressStreak():
  → Count consecutive calls with same tool+args+resultHash
  → Must have resultHash populated to count
  → Returns count + latestResultHash

getPingPongStreak():
  → Detect alternating pattern: if last K calls alternate between signature A and B
  → Require both A and B outcomes to be stable (consistent hashes)
  → Returns count + pairedToolName + noProgressEvidence flag
```

### Integration Points
1. `recordToolCall()` - Called before tool execution
2. `detectToolCallLoop()` - Called before tool execution
3. `recordToolCallOutcome()` - Called after tool execution completes
4. `getToolCallStats()` - Diagnostic API (total calls, unique patterns, most frequent)

### Configuration Defaults
```typescript
{
  enabled: false                    // Off by default
  historySize: 30
  warningThreshold: 10
  criticalThreshold: 20
  globalCircuitBreakerThreshold: 30
  detectors: {
    genericRepeat: true
    knownPollNoProgress: true
    pingPong: true
  }
}
```

---

## 8. ARCHITECTURAL PATTERNS & INNOVATIONS

### Pattern 1: Layered Failover
- Multiple levels of retry (outer: profile rotation, inner: think level fallback, innermost: attempt loop)
- Each level has configurable max iterations
- Graceful degradation (disable thinking, rotate auth, try another model)

### Pattern 2: Token-Aware Chunking
Three parallel chunking strategies:
- **Equal Share**: Divide by message count for balanced distribution
- **Max Size**: Enforce ceiling to prevent model overload
- **Adaptive**: Adjust ratio based on message size distribution
Allows summarization to adapt to heterogeneous message streams.

### Pattern 3: Orphan Repair
After history pruning, actively repairs broken message relationships:
- Detects tool_result without corresponding tool_use
- Removes orphaned tool_results before sending to LLM
- Prevents "unexpected tool_use_id" API errors
Shows sophisticated understanding of LLM API constraints.

### Pattern 4: Cache-Aware Usage Reporting
- Tracks both accumulated and "last API call" usage
- Uses LAST values for context reporting (not sum)
- Prevents cache inflation from multiple tool-call round trips
- Demonstrates deep API knowledge (cacheRead ≈ current_context_size per call)

### Pattern 5: Multidimensional Tool Policy
- 7-layer pipeline of allow/deny filters
- Plugin-aware expansion (group:plugins, {pluginId})
- Warns on plugin-only allowlists (prevents accidental core tool disabling)
- Supports both additive (alsoAllow) and restrictive (deny) policies

### Pattern 6: Depth-Tracked Subagents
- Session store persists spawnDepth + spawnedBy parent reference
- Recursive depth resolution with cycle detection
- Fallback to sessionKey embedded depth marker
- Limits nesting to prevent runaway agent trees

### Pattern 7: Configurable Loop Detection
- Four independent detectors with separate thresholds
- Stable outcome hashing (ignores result text variance)
- Distinguishes polling loops (no progress) from ping-pong loops (alternating)
- Global circuit breaker prevents system-wide loops

---

## 9. KEY CONFIGURATION POINTS

### Agent Limits (defaults in code)
- `SPAWN_AGENT_MAX_SPAWN_DEPTH = 3` (max nesting)
- `maxChildrenPerAgent = 5` (concurrent children per session)
- `subagentRunTimeoutSeconds` (configurable per spawn or global default)

### Token Management
- `contextTokens` cap (cfg.agents.defaults.contextTokens)
- Compaction overhead: 4096 tokens reserved
- Safety margin: 1.2x (20% buffer)
- Min chunk ratio: 15%, base ratio: 40%

### Loop Detection
- All thresholds configurable (warning, critical, global)
- History size: 30 calls
- Can be disabled per session

### Tool Policy
- 7-layer pipeline
- Plugin group expansion
- Owner-only tool filtering
- Additive (alsoAllow) support

---

## 10. DESIGN PHILOSOPHY

**"Defensive & Graceful"**
- Multiple fallback layers (auth, thinking, model)
- Conservative token estimates (safety margin)
- Orphan repair (prevent API errors)
- Progressive degradation (don't fail fast)

**"Context-Aware"**
- Cache-aware usage (not just accumulated tokens)
- Adaptive chunk sizing (message-size aware)
- Overflow detection + compaction trigger
- Subagent depth tracking (prevent runaway nesting)

**"Safety-First"**
- Owner-only tools (privilege separation)
- Loop detection (prevent runaway execution)
- Circuit breakers (global guard)
- Context window guard (min thresholds)

**"Observable"**
- Diagnostic session state (tool call history)
- Loop detection statistics (patterns, frequency)
- Compaction diagnostics (diagId, attempt tracking)
- Registry persistence (disk + memory mirroring)
