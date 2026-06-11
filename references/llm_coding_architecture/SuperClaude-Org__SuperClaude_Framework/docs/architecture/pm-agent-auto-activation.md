# PM Agent Auto-Activation Architecture

## Problem Statement

**Current Issue**: PM Agent functionality requires manual `/sc:pm` command invocation, making it easy to forget and inconsistently applied.

**User Concern**: "今は、/sc:pmコマンドを毎回叩かないと、PM-modeやってくれないきがする"

## Solution: Behavior-Based Auto-Activation

PM Agent should activate automatically based on **context detection**, not manual commands.

### Architecture Overview

```yaml
PM Agent Activation Layers:

  Layer 1 - Session Start (ALWAYS):
    Trigger: Every new conversation session
    Action: Auto-restore context from docs/memory/
    Detection: Session initialization event

  Layer 2 - Documentation Guardian (CONTINUOUS):
    Trigger: Any file operation in project
    Action: Ensure relevant docs are read before implementation
    Detection: Write/Edit tool usage

  Layer 3 - Commander (ON-DEMAND):
    Trigger: Complex tasks (>3 steps OR >3 files)
    Action: Orchestrate sub-agents and track progress
    Detection: TodoWrite usage OR complexity keywords

  Layer 4 - Post-Implementation (AUTO):
    Trigger: Task completion
    Action: Document learnings and update knowledge base
    Detection: Completion keywords OR test pass

  Layer 5 - Mistake Handler (IMMEDIATE):
    Trigger: Errors or test failures
    Action: Root cause analysis and prevention documentation
    Detection: Error messages OR test failures
```

## Implementation Strategy

### 1. Session Start Auto-Activation

**File**: `~/.claude/superclaude/agents/pm-agent.md`

**Trigger Detection**:
```yaml
session_start_indicators:
  - First message in new conversation
  - No prior context in current session
  - Token budget reset to baseline
  - No active TodoWrite items in memory
```

**Auto-Execution (No Manual Command)**:
```yaml
Wave 1 - PARALLEL Context Restoration:
  1. Bash: git status && git branch
  2. PARALLEL Read (silent):
     - Read docs/memory/pm_context.md (if exists)
     - Read docs/memory/last_session.md (if exists)
     - Read docs/memory/next_actions.md (if exists)
     - Read docs/memory/current_plan.json (if exists)
     - Read CLAUDE.md (ALWAYS)
     - Read docs/patterns/*.md (recent 5 files)

Checkpoint - Confidence Check (200 tokens):
  ❓ "全ファイル読めた？"
  ❓ "コンテキストに矛盾ない？"
  ❓ "次のアクション実行に十分な情報？"

  IF confidence >70%:
    → Output: 📍 [branch] | [status] | 🧠 [token]%
    → Ready for user request
  ELSE:
    → Report what's missing
    → Request user clarification
```

**Key Change**: This happens **automatically** at session start, not via `/sc:pm` command.

### 2. Documentation Guardian (Continuous)

**Purpose**: Ensure documentation is ALWAYS read before making changes

**Trigger Detection**:
```yaml
pre_write_checks:
  - BEFORE any Write tool usage
  - BEFORE any Edit tool usage
  - BEFORE complex TodoWrite (>3 tasks)

detection_logic:
  IF tool_name in [Write, Edit, MultiEdit]:
    AND file_path matches project patterns:
      → Auto-trigger Documentation Guardian
```

**Auto-Execution**:
```yaml
Documentation Guardian Protocol:

1. Identify Relevant Docs:
   file_path: src/auth.ts
   → Read docs/patterns/authentication-*.md
   → Read docs/mistakes/auth-*.md
   → Read CLAUDE.md sections matching "auth"

2. Confidence Check:
   ❓ "関連ドキュメント全部読んだ？"
   ❓ "過去の失敗パターン把握してる？"
   ❓ "既存の成功パターン確認した？"

   IF any_missing:
     → Read missing docs
     → Update understanding
     → Proceed with implementation
   ELSE:
     → Proceed confidently

3. Pattern Matching:
   IF similar_mistakes_found:
     ⚠️ "過去に同じミス発生: [mistake_pattern]"
     ⚠️ "防止策: [prevention_checklist]"
     → Apply prevention before implementation
```

**Key Change**: Automatic documentation reading BEFORE any file modification.

### 3. Commander Mode (On-Demand)

**Purpose**: Orchestrate complex multi-step tasks with sub-agents

**Trigger Detection**:
```yaml
commander_triggers:
  complexity_based:
    - TodoWrite with >3 tasks
    - Operations spanning >3 files
    - Multi-directory scope (>2 dirs)
    - Keywords: "refactor", "migrate", "redesign"

  explicit_keywords:
    - "orchestrate"
    - "coordinate"
    - "delegate"
    - "parallel execution"
```

**Auto-Execution**:
```yaml
Commander Protocol:

1. Task Analysis:
   - Identify independent vs dependent tasks
   - Determine parallelization opportunities
   - Select appropriate sub-agents

2. Orchestration Plan:
   tasks:
     - task_1: [agent-backend] → auth refactor
     - task_2: [agent-frontend] → UI updates (parallel)
     - task_3: [agent-test] → test updates (after 1+2)

   parallelization:
     wave_1: [task_1, task_2] # parallel
     wave_2: [task_3]         # sequential dependency

3. Execution with Tracking:
   - TodoWrite for overall plan
   - Sub-agent delegation via Task tool
   - Progress tracking in docs/memory/checkpoint.json
   - Validation gates between waves

4. Synthesis:
   - Collect sub-agent outputs
   - Integrate results
   - Final validation
   - Update documentation
```

**Key Change**: Auto-activates when complexity detected, no manual command needed.

### 4. Post-Implementation Auto-Documentation

**Trigger Detection**:
```yaml
completion_indicators:
  test_based:
    - "All tests passing" in output
    - pytest: X/X passed
    - ✅ keywords detected

  task_based:
    - All TodoWrite items marked completed
    - No pending tasks remaining

  explicit:
    - User says "done", "finished", "complete"
    - Commit message created
```

**Auto-Execution**:
```yaml
Post-Implementation Protocol:

1. Self-Evaluation (The Four Questions):
   ❓ "テストは全てpassしてる？"
   ❓ "要件を全て満たしてる？"
   ❓ "思い込みで実装してない？"
   ❓ "証拠はある？"

   IF any_fail:
     ❌ NOT complete
     → Report actual status
   ELSE:
     ✅ Proceed to documentation

2. Pattern Extraction:
   - What worked? → docs/patterns/[pattern].md
   - What failed? → docs/mistakes/[mistake].md
   - New learnings? → docs/memory/patterns_learned.jsonl

3. Knowledge Base Update:
   IF global_pattern_discovered:
     → Update CLAUDE.md with new rule
   IF project_specific_pattern:
     → Update docs/patterns/
   IF anti_pattern_identified:
     → Update docs/mistakes/

4. Session State Update:
   - Write docs/memory/session_summary.json
   - Update docs/memory/next_actions.md
   - Clean up temporary docs (>7 days old)
```

**Key Change**: Automatic documentation after task completion, no manual trigger needed.

### 5. Mistake Handler (Immediate)

**Trigger Detection**:
```yaml
error_indicators:
  test_failures:
    - "FAILED" in pytest output
    - "Error" in test results
    - Non-zero exit code

  runtime_errors:
    - Exception stacktrace detected
    - Build failures
    - Linter errors (critical only)

  validation_failures:
    - Type check errors
    - Schema validation failures
```

**Auto-Execution**:
```yaml
Mistake Handler Protocol:

1. STOP Current Work:
   → Halt further implementation
   → Do not workaround the error

2. Reflexion Pattern:
   a) Check Past Errors:
      → Grep docs/memory/solutions_learned.jsonl
      → Grep docs/mistakes/ for similar errors

   b) IF similar_error_found:
      ✅ "過去に同じエラー発生済み"
      ✅ "解決策: [past_solution]"
      → Apply known solution

   c) ELSE (new error):
      → Root cause investigation
      → Document new solution

3. Documentation:
   Create docs/mistakes/[feature]-YYYY-MM-DD.md:
     - What Happened (現象)
     - Root Cause (根本原因)
     - Why Missed (なぜ見逃したか)
     - Fix Applied (修正内容)
     - Prevention Checklist (防止策)
     - Lesson Learned (教訓)

4. Update Knowledge Base:
   → echo '{"error":"...","solution":"..."}' >> docs/memory/solutions_learned.jsonl
   → Update prevention checklists
```

**Key Change**: Immediate automatic activation when errors detected, no manual trigger.

## Removal of Manual `/sc:pm` Command

### Current State
- `/sc:pm` command in `~/.claude/commands/sc/pm.md`
- Requires user to manually invoke every session
- Inconsistent application

### Proposed Change
- **Remove** `/sc:pm` command entirely
- **Replace** with behavior-based auto-activation
- **Keep** pm-agent persona for all behaviors

### Migration Path

```yaml
Step 1 - Update pm-agent.md:
  Remove: "Manual Invocation: /sc:pm command"
  Add: "Auto-Activation: Behavior-based triggers (see below)"

Step 2 - Delete /sc:pm command:
  File: ~/.claude/commands/sc/pm.md
  Action: Archive or delete (functionality now in persona)

Step 3 - Update rules.md:
  Agent Orchestration section:
  - Remove references to /sc:pm command
  - Add auto-activation trigger documentation

Step 4 - Test Auto-Activation:
  - Start new session → Should auto-restore context
  - Make file changes → Should auto-read relevant docs
  - Complete task → Should auto-document learnings
  - Encounter error → Should auto-trigger mistake handler
```

## Benefits

### 1. No Manual Commands Required
- ✅ PM Agent always active, never forgotten
- ✅ Consistent documentation reading
- ✅ Automatic knowledge base maintenance

### 2. Context-Aware Activation
- ✅ Right behavior at right time
- ✅ No unnecessary overhead
- ✅ Efficient token usage

### 3. Guaranteed Documentation Quality
- ✅ Always read relevant docs before changes
- ✅ Automatic pattern documentation
- ✅ Mistake prevention through Reflexion

### 4. Seamless Orchestration
- ✅ Auto-detects complex tasks
- ✅ Auto-delegates to sub-agents
- ✅ Auto-tracks progress

## Token Budget Impact

```yaml
Current (Manual /sc:pm):
  If forgotten: 0 tokens (no PM functionality)
  If remembered: 200-500 tokens per invocation
  Average: Inconsistent, user-dependent

Proposed (Auto-Activation):
  Session Start: 200 tokens (ALWAYS)
  Documentation Guardian: 0-100 tokens (as needed)
  Commander: 0 tokens (only if complex task)
  Post-Implementation: 200-2,500 tokens (only after completion)
  Mistake Handler: 0 tokens (only if error)

  Total per session: 400-3,000 tokens (predictable)

  Trade-off: Slight increase in baseline usage
  Benefit: 100% consistent PM Agent functionality
  ROI: Prevents 5K-50K token waste from wrong implementations
```

## Implementation Checklist

```yaml
Phase 1 - Core Auto-Activation:
  - [ ] Update pm-agent.md with auto-activation triggers
  - [ ] Remove session start from /sc:pm command
  - [ ] Test session start auto-restoration
  - [ ] Verify token budget calculations

Phase 2 - Documentation Guardian:
  - [ ] Add pre-write documentation checks
  - [ ] Implement pattern matching logic
  - [ ] Test with various file operations
  - [ ] Verify no performance degradation

Phase 3 - Commander Mode:
  - [ ] Add complexity detection logic
  - [ ] Implement sub-agent delegation
  - [ ] Test parallel execution patterns
  - [ ] Verify progress tracking

Phase 4 - Post-Implementation:
  - [ ] Add completion detection logic
  - [ ] Implement auto-documentation triggers
  - [ ] Test pattern extraction
  - [ ] Verify knowledge base updates

Phase 5 - Mistake Handler:
  - [ ] Add error detection logic
  - [ ] Implement Reflexion pattern lookup
  - [ ] Test mistake documentation
  - [ ] Verify prevention checklist updates

Phase 6 - Cleanup:
  - [ ] Archive /sc:pm command
  - [ ] Update all documentation
  - [ ] Remove manual invocation references
  - [ ] Final integration testing
```

## Example Workflow (After Implementation)

```yaml
User Session:

1. Start Conversation:
   Claude: [Auto-activates PM Agent]
   Claude: 📍 feature/auth | ✨ Clean | 🧠 15% (30K/200K)
   User: "Fix authentication bug in auth.ts"

2. Pre-Implementation:
   Claude: [Documentation Guardian activates]
   Claude: [Reads docs/patterns/authentication-*.md silently]
   Claude: [Reads docs/mistakes/auth-*.md silently]
   Claude: ⚠️ Past mistake found: "Missing token validation"
   Claude: Applying prevention checklist before implementation...

3. Implementation:
   Claude: [Makes changes with prevention applied]
   Claude: [Runs tests]
   Claude: ✅ All tests passing

4. Post-Implementation:
   Claude: [Auto-activates documentation]
   Claude: [Runs Four Questions self-check]
   Claude: [Extracts pattern: "Token validation pattern"]
   Claude: [Updates docs/patterns/authentication-token-validation.md]
   Claude: ✅ Task complete with documentation updated

User: [Never had to invoke /sc:pm manually]
```

## Conclusion

This architecture ensures PM Agent functionality is **always active** through behavior-based triggers, eliminating the need for manual `/sc:pm` command invocation while maintaining clear responsibility separation and guaranteed documentation quality.
