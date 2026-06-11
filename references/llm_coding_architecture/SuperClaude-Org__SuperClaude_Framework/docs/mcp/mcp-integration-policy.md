# MCP Integration Policy

Integration policy and usage guidelines for MCP (Model Context Protocol) servers in SuperClaude Framework.

## MCP Server Definitions

### Core MCP Servers

#### Memory & Error Learning

**ReflexionMemory (Built-in, Always Available)**
```yaml
Name: ReflexionMemory
Purpose: Error history storage and learning
Category: Memory Management (Built-in)
Auto-Managed: true (internal implementation)
PM Agent Role: Automatically used on errors

Capabilities:
  - Memory of past errors and solutions
  - Keyword-based similar error search
  - Learning to prevent recurrence
  - Project-scoped memory

Implementation:
  Location: superclaude/core/pm_init/reflexion_memory.py
  Storage: docs/memory/reflexion.jsonl (local file)
  Search: Keyword-based (50% overlap threshold)

Note: This is an internal implementation, not an external MCP server
```

**Mindbase MCP (Optional Enhancement via airis-mcp-gateway)**
```yaml
Name: mindbase
Purpose: Semantic search across all conversation history
Category: Memory Management (Optional MCP)
Auto-Managed: false (external MCP server - requires installation)
PM Agent Role: Automatically selected by Claude when available

Capabilities:
  - Persistence of all conversation history (PostgreSQL + pgvector)
  - Semantic search (qwen3-embedding:8b)
  - Cross-project knowledge sharing
  - Learning from all past conversations

Tools:
  - mindbase_search: Semantic search
  - mindbase_store: Conversation storage
  - mindbase_health: Health check

Installation:
  Requires: airis-mcp-gateway with "recommended" profile
  See: https://github.com/agiletec-inc/airis-mcp-gateway

Profile Dependency:
  - "recommended" profile: mindbase included (long-term projects)
  - "minimal" profile: mindbase NOT included (lightweight, quick tasks)

Usage Pattern:
  - With installation + recommended profile: Claude automatically uses it
  - Otherwise: Falls back to ReflexionMemory
  - PM Agent instructs: "Search past errors" (Claude selects tool)

Note: Optional enhancement. SuperClaude works fully with ReflexionMemory alone.
```

#### Serena MCP
```yaml
Name: serena
Purpose: コードベース理解のためのシンボル管理
Category: Code Understanding
Auto-Managed: false (明示的使用)
PM Agent Role: コード理解タスクで自動活用

Capabilities:
  - シンボル追跡（関数、クラス、変数）
  - コード構造分析
  - リファクタリング支援
  - 依存関係マッピング

Lifecycle:
  Start: 何もしない
  During: コード理解時に使用
  End: 自動削除（セッション終了）
  Cleanup: 自動

Usage Pattern:
  Use Cases:
    - リファクタリング計画
    - コード構造分析
    - シンボル間の関係追跡
    - 大規模コードベース探索

  NOT for:
    - タスク管理
    - 会話記憶
    - ドキュメント保存
    - プロジェクト知識管理

Trigger Conditions:
  - Keywords: "refactor", "analyze code structure", "find all usages"
  - File Count: >10 files involved
  - Complexity: Cross-file symbol tracking needed

Example:
  Task: "Refactor authentication system across 15 files"
  → Serena: Track auth-related symbols
  → PM Agent: Coordinate refactoring with Serena insights
```

#### Sequential MCP
```yaml
Name: sequential-thinking
Purpose: 複雑な推論と段階的分析
Category: Reasoning Engine
Auto-Managed: false (明示的使用)
PM Agent Role: Commander modeで複雑タスク分析

Capabilities:
  - 段階的推論
  - 仮説検証
  - 複雑な問題分解
  - システム設計分析

Lifecycle:
  Start: 何もしない
  During: 複雑分析時に使用
  End: 分析結果を返す
  Cleanup: 自動

Usage Pattern:
  Use Cases:
    - アーキテクチャ設計
    - 複雑なバグ分析
    - システム設計レビュー
    - トレードオフ分析

  NOT for:
    - 単純なタスク
    - 直感的に解決できる問題
    - コード生成（分析のみ）

Trigger Conditions:
  - Keywords: "design", "architecture", "analyze tradeoffs"
  - Complexity: Multi-component system analysis
  - Uncertainty: Multiple valid approaches exist

Example:
  Task: "Design microservices architecture for authentication"
  → Sequential: Step-by-step design analysis
  → PM Agent: Document design decisions in docs/patterns/
```

#### Context7 MCP
```yaml
Name: context7
Purpose: 公式ドキュメントとライブラリパターン参照
Category: Documentation Reference
Auto-Managed: false (明示的使用)
PM Agent Role: Pre-Implementation Confidence Check

Capabilities:
  - 公式ドキュメント検索
  - ライブラリベストプラクティス
  - API仕様確認
  - フレームワークパターン

Lifecycle:
  Start: 何もしない
  During: ドキュメント参照時に使用
  End: 情報を返す
  Cleanup: 自動

Usage Pattern:
  Use Cases:
    - ライブラリの使い方確認
    - ベストプラクティス参照
    - API仕様確認
    - 公式パターン学習

  NOT for:
    - プロジェクト固有ドキュメント（docs/使用）
    - 社内ドキュメント
    - カスタム実装パターン

Trigger Conditions:
  - Pre-Implementation: Confidence check時
  - Keywords: "official docs", "best practices", "how to use [library]"
  - New Library: 初めて使うライブラリ

Example:
  Task: "Implement JWT authentication with jose library"
  → Context7: Fetch jose official docs and patterns
  → PM Agent: Verify implementation against official patterns
```

#### Tavily MCP
```yaml
Name: tavily
Purpose: Web検索とリアルタイム情報取得
Category: Research
Auto-Managed: false (明示的使用)
PM Agent Role: Research modeで情報収集

Capabilities:
  - Web検索
  - 最新情報取得
  - 技術記事検索
  - エラーメッセージ検索

Lifecycle:
  Start: 何もしない
  During: 研究・調査時に使用
  End: 検索結果を返す
  Cleanup: 自動

Usage Pattern:
  Use Cases:
    - 最新のライブラリバージョン確認
    - エラーメッセージの解決策検索
    - 技術トレンド調査
    - 公式ドキュメント検索（Context7にない場合）

  NOT for:
    - プロジェクト内情報（Grep使用）
    - コードベース検索（Serena使用）
    - 過去の会話（Mindbase使用）

Trigger Conditions:
  - Keywords: "search", "latest", "current"
  - Error: Unknown error message
  - Research: New technology investigation

Example:
  Task: "Find latest Next.js 15 App Router patterns"
  → Tavily: Search web for latest patterns
  → PM Agent: Document findings in docs/patterns/
```

## MCP Selection Matrix

### By Task Type

```yaml
Code Understanding:
  Primary: Serena MCP
  Secondary: Grep (simple searches)
  Example: "Find all authentication-related symbols"

Complex Analysis:
  Primary: Sequential MCP
  Secondary: Native reasoning (simple cases)
  Example: "Design authentication architecture"

Documentation Reference:
  Primary: Context7 MCP
  Secondary: Tavily (if not in Context7)
  Example: "How to use React Server Components"

Research & Investigation:
  Primary: Tavily MCP
  Secondary: Context7 (official docs)
  Example: "Latest security best practices 2025"

Memory & History:
  Primary: Mindbase MCP (automatic)
  Secondary: None (fully automated)
  Example: N/A (transparent)

Task Management:
  Primary: TodoWrite (built-in)
  Secondary: None
  Example: Track multi-step implementation
```

### By Complexity Level

```yaml
Simple (1-2 files, clear path):
  MCPs: None (native tools sufficient)
  Tools: Read, Edit, Grep, Bash

Medium (3-10 files, some complexity):
  MCPs: Context7 (if new library)
  Tools: MultiEdit, Glob, Grep

Complex (>10 files, architectural changes):
  MCPs: Serena + Sequential
  Coordination: PM Agent Commander mode
  Tools: Task delegation, parallel execution

Research (information gathering):
  MCPs: Tavily + Context7
  Mode: DeepResearch mode
  Tools: WebFetch (selective)
```

## PM Agent Integration Rules

### Session Lifecycle

```yaml
Session Start:
  Auto-Execute:
    1. git status && git branch
    2. Read CLAUDE.md
    3. Read docs/patterns/*.md (latest 5)
    4. Mindbase auto-load (automatic)

  MCPs Used:
    - Mindbase: Automatic (no explicit call)
    - Others: None (wait for task)

  Output: 📍 [branch] | [status] | 🧠 [token]%

Pre-Implementation:
  Auto-Execute:
    1. Read relevant docs/patterns/
    2. Read relevant docs/mistakes/
    3. Confidence check

  MCPs Used:
    - Context7: If new library (automatic)
    - Serena: If complex refactor (automatic)

  Decision:
    High Confidence (>90%): Proceed
    Medium (70-89%): Present options
    Low (<70%): Stop, request clarification

During Implementation:
  Manual Trigger:
    - TodoWrite: Progress tracking
    - Serena: Code understanding (if needed)
    - Sequential: Complex analysis (if needed)

  MCPs Used:
    - Serena: On code complexity trigger
    - Sequential: On analysis keyword
    - Context7: On documentation need

Post-Implementation:
  Auto-Execute:
    1. Self-evaluation (Four Questions)
    2. Pattern extraction
    3. Documentation update

  MCPs Used:
    - Mindbase: Automatic save
    - Others: None (file-based documentation)

  Output:
    - Success → docs/patterns/
    - Failure → docs/mistakes/
    - Global → CLAUDE.md
```

### MCP Activation Triggers

```yaml
Serena MCP:
  Auto-Trigger Keywords:
    - "refactor"
    - "analyze code structure"
    - "find all usages"
    - "symbol tracking"

  Auto-Trigger Conditions:
    - File count > 10
    - Cross-file changes
    - Symbol renaming
    - Dependency analysis

  Manual Override: --serena flag

Sequential MCP:
  Auto-Trigger Keywords:
    - "design"
    - "architecture"
    - "analyze tradeoffs"
    - "complex problem"

  Auto-Trigger Conditions:
    - System design task
    - Multiple valid approaches
    - Uncertainty in implementation
    - Architectural decision

  Manual Override: --seq flag

Context7 MCP:
  Auto-Trigger Keywords:
    - "official docs"
    - "best practices"
    - "how to use [library]"
    - New library detected

  Auto-Trigger Conditions:
    - Pre-Implementation confidence check
    - New library in package.json
    - Framework pattern needed

  Manual Override: --c7 flag

Tavily MCP:
  Auto-Trigger Keywords:
    - "search"
    - "latest"
    - "current trends"
    - "find error solution"

  Auto-Trigger Conditions:
    - Research mode active
    - Unknown error message
    - Latest version check

  Manual Override: --tavily flag
```

## Anti-Patterns (禁止事項)

### DO NOT

```yaml
❌ Mindbaseを明示的に操作:
  Reason: 完全自動管理、PM Agentは触らない
  Instead: 何もしない（自動で動く）

❌ Serenaをタスク管理に使用:
  Reason: コード理解専用
  Instead: TodoWrite使用

❌ write_memory() / read_memory() 使用:
  Reason: Serenaはコード理解専用、タスク管理ではない
  Instead: TodoWrite + docs/

❌ docs/memory/ ディレクトリ作成:
  Reason: Mindbaseと重複
  Instead: docs/patterns/ と docs/mistakes/ 使用

❌ 全タスクでSequential使用:
  Reason: トークン浪費
  Instead: 複雑分析時のみ

❌ Context7をプロジェクトドキュメントに使用:
  Reason: 公式ドキュメント専用
  Instead: Read docs/ 使用
```

## Best Practices

### Efficient MCP Usage

```yaml
✅ Right Tool for Right Job:
  Simple → Native tools (Read, Edit, Grep)
  Medium → Context7 (new library)
  Complex → Serena + Sequential

✅ Lazy Evaluation:
  Don't preload MCPs
  Activate only when needed
  Let PM Agent auto-trigger

✅ Clear Separation:
  Memory: Mindbase (automatic)
  Knowledge: docs/ (file-based)
  Progress: TodoWrite (session)
  Code: Serena (understanding)

✅ Documentation First:
  Pre-Implementation: Context7 + docs/patterns/
  During: TodoWrite tracking
  Post: docs/patterns/ or docs/mistakes/
```

## Testing & Validation

### MCP Integration Tests

```yaml
Test Cases:

1. Mindbase Auto-Load:
   - Start session
   - Verify past context loaded automatically
   - No explicit mindbase calls

2. Serena Code Understanding:
   - Task: "Refactor auth across 15 files"
   - Verify Serena auto-triggered
   - Verify symbol tracking used

3. Sequential Complex Analysis:
   - Task: "Design microservices architecture"
   - Verify Sequential auto-triggered
   - Verify step-by-step reasoning

4. Context7 Documentation:
   - Task: "Implement with new library"
   - Verify Context7 auto-triggered
   - Verify official docs referenced

5. Tavily Research:
   - Task: "Find latest security patterns"
   - Verify Tavily auto-triggered
   - Verify web search executed
```

## Migration Checklist

```yaml
From Old System:
  - [ ] Remove docs/memory/ references
  - [ ] Remove write_memory() / read_memory() calls
  - [ ] Remove MODE_Task_Management.md memory sections
  - [ ] Update pm-agent.md with new MCP policy

To New System:
  - [ ] Add MCP integration policy docs
  - [ ] Update pm-agent.md triggers
  - [ ] Add auto-activation logic
  - [ ] Test MCP selection matrix
  - [ ] Validate anti-patterns enforcement
```

## References

- PM Agent: `~/.claude/superclaude/agents/pm-agent.md`
- Modes: `~/.claude/superclaude/modes/MODE_*.md`
- Rules: `~/.claude/superclaude/framework/rules.md`
- Memory Cleanup: `docs/architecture/pm-agent-responsibility-cleanup.md`
