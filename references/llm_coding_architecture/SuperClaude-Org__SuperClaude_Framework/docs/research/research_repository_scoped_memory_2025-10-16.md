# Repository-Scoped Memory Management for AI Coding Assistants
**Research Report | 2025-10-16**

## Executive Summary

This research investigates best practices for implementing repository-scoped memory management in AI coding assistants, with specific focus on SuperClaude PM Agent integration. Key findings indicate that **local file storage with git repository detection** is the industry standard for session isolation, offering optimal performance and developer experience.

### Key Recommendations for SuperClaude

1. **✅ Adopt Local File Storage**: Store memory in repository-specific directories (`.superclaude/memory/` or `docs/memory/`)
2. **✅ Use Git Detection**: Implement `git rev-parse --git-dir` for repository boundary detection
3. **✅ Prioritize Simplicity**: Start with file-based approach before considering databases
4. **✅ Maintain Backward Compatibility**: Support future cross-repository intelligence as optional feature

---

## 1. Industry Best Practices

### 1.1 Cursor IDE Memory Architecture

**Implementation Pattern**:
```
project-root/
├── .cursor/
│   └── rules/           # Project-specific configuration
├── .git/                # Repository boundary marker
└── memory-bank/         # Session context storage
    ├── project_context.md
    ├── progress_history.md
    └── architectural_decisions.md
```

**Key Insights**:
- Repository-level isolation using `.cursor/rules` directory
- Memory Bank pattern: structured knowledge repository for cross-session context
- MCP integration (Graphiti) for sophisticated memory management across sessions
- **Problem**: Users report context loss mid-task and excessive "start new chat" prompts

**Relevance to SuperClaude**: Validates local directory approach with repository-scoped configuration.

---

### 1.2 GitHub Copilot Workspace Context

**Implementation Pattern**:
- Remote code search indexes for GitHub/Azure DevOps repositories
- Local indexes for non-cloud repositories (limit: 2,500 files)
- Respects `.gitignore` for index exclusion
- Workspace-level context with repository-specific boundaries

**Key Insights**:
- Automatic index building for GitHub-backed repos
- `.gitignore` integration prevents sensitive data indexing
- Repository authorization through GitHub App permissions
- **Limitation**: Context scope is workspace-wide, not repository-specific by default

**Relevance to SuperClaude**: `.gitignore` integration is critical for security and performance.

---

### 1.3 Session Isolation Best Practices

**Git Worktrees for Parallel Sessions**:
```bash
# Enable multiple isolated Claude sessions
git worktree add ../feature-branch feature-branch
# Each worktree has independent working directory, shared git history
```

**Context Window Management**:
- Long sessions lead to context pollution → performance degradation
- **Best Practice**: Use `/clear` command between tasks
- Create session-end context files (`GEMINI.md`, `CONTEXT.md`) for handoff
- Break tasks into smaller, isolated chunks

**Enterprise Security Architecture** (4-Layer Defense):
1. **Prevention**: Rate-limit access, auto-strip credentials
2. **Protection**: Encryption, project-level role-based access control
3. **Detection**: SAST/DAST/SCA on pull requests
4. **Response**: Detailed commit-prompt mapping

**Relevance to SuperClaude**: PM Agent should implement context reset between repository changes.

---

## 2. Git Repository Detection Patterns

### 2.1 Standard Detection Methods

**Recommended Approach**:
```bash
# Detect if current directory is in git repository
git rev-parse --git-dir

# Check if inside working tree
git rev-parse --is-inside-work-tree

# Get repository root
git rev-parse --show-toplevel
```

**Implementation Considerations**:
- Git searches parent directories for `.git` folder automatically
- `libgit2` library recommended for programmatic access
- Avoid direct `.git` folder parsing (fragile to git internals changes)

### 2.2 Security Concerns

- **Issue**: Millions of `.git` folders exposed publicly by misconfiguration
- **Mitigation**: Always respect `.gitignore` and add `.superclaude/` to ignore patterns
- **Best Practice**: Store sensitive memory data in gitignored directories

---

## 3. Storage Architecture Comparison

### 3.1 Local File Storage

**Advantages**:
- ✅ **Performance**: Faster than databases for sequential reads
- ✅ **Simplicity**: No database setup or maintenance
- ✅ **Portability**: Works offline, no network dependencies
- ✅ **Developer-Friendly**: Files are readable/editable by humans
- ✅ **Git Integration**: Can be versioned (if desired) or gitignored

**Disadvantages**:
- ❌ No ACID transactions
- ❌ Limited query capabilities
- ❌ Manual concurrency handling

**Use Cases**:
- **Perfect for**: Session context, architectural decisions, project documentation
- **Not ideal for**: High-concurrency writes, complex queries

---

### 3.2 Database Storage

**Advantages**:
- ✅ ACID transactions
- ✅ Complex queries (SQL)
- ✅ Concurrency management
- ✅ Scalability for cross-repository intelligence (future)

**Disadvantages**:
- ❌ **Performance**: Slower than local files for simple reads
- ❌ **Complexity**: Database setup and maintenance overhead
- ❌ **Network Bottlenecks**: If using remote database
- ❌ **Developer UX**: Requires database tools to inspect

**Use Cases**:
- **Future feature**: Cross-repository pattern mining
- **Not needed for**: Basic repository-scoped memory

---

### 3.3 Vector Databases (Advanced)

**Recommendation**: **Not needed for v1**

**Future Consideration**:
- Semantic search across project history
- Pattern recognition across repositories
- Requires significant infrastructure investment
- **Wait until**: SuperClaude reaches "super-intelligence" level

---

## 4. SuperClaude PM Agent Recommendations

### 4.1 Immediate Implementation (v1)

**Architecture**:
```
project-root/
├── .git/                          # Repository boundary
├── .gitignore
│   └── .superclaude/              # Add to gitignore
├── .superclaude/
│   └── memory/
│       ├── session_state.json     # Current session context
│       ├── pm_context.json        # PM Agent PDCA state
│       └── decisions/             # Architectural decision records
│           ├── 2025-10-16_auth.md
│           └── 2025-10-15_db.md
└── docs/
    └── superclaude/               # Human-readable documentation
        ├── patterns/              # Successful patterns
        └── mistakes/              # Error prevention

```

**Detection Logic**:
```python
import subprocess
from pathlib import Path

def get_repository_root() -> Path | None:
    """Detect git repository root using git rev-parse."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None

def get_memory_dir() -> Path:
    """Get repository-scoped memory directory."""
    repo_root = get_repository_root()
    if repo_root:
        memory_dir = repo_root / ".superclaude" / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        return memory_dir
    else:
        # Fallback to global memory if not in git repo
        return Path.home() / ".superclaude" / "memory" / "global"
```

**Session Lifecycle Integration**:
```python
# Session Start
def restore_session_context():
    repo_root = get_repository_root()
    if not repo_root:
        return {}  # No repository context

    memory_file = repo_root / ".superclaude" / "memory" / "pm_context.json"
    if memory_file.exists():
        return json.loads(memory_file.read_text())
    return {}

# Session End
def save_session_context(context: dict):
    repo_root = get_repository_root()
    if not repo_root:
        return  # Don't save if not in repository

    memory_file = repo_root / ".superclaude" / "memory" / "pm_context.json"
    memory_file.parent.mkdir(parents=True, exist_ok=True)
    memory_file.write_text(json.dumps(context, indent=2))
```

---

### 4.2 PM Agent Memory Management

**PDCA Cycle Integration**:
```python
# Plan Phase
write_memory(repo_root / ".superclaude/memory/plan.json", {
    "hypothesis": "...",
    "success_criteria": "...",
    "risks": [...]
})

# Do Phase
write_memory(repo_root / ".superclaude/memory/experiment.json", {
    "trials": [...],
    "errors": [...],
    "solutions": [...]
})

# Check Phase
write_memory(repo_root / ".superclaude/memory/evaluation.json", {
    "outcomes": {...},
    "adherence_check": "...",
    "completion_status": "..."
})

# Act Phase
if success:
    move_to_patterns(repo_root / "docs/superclaude/patterns/pattern-name.md")
else:
    move_to_mistakes(repo_root / "docs/superclaude/mistakes/mistake-YYYY-MM-DD.md")
```

---

### 4.3 Context Isolation Strategy

**Problem**: User switches from `SuperClaude_Framework` to `airis-mcp-gateway`
**Current Behavior**: PM Agent retains SuperClaude context → Noise
**Desired Behavior**: PM Agent detects repository change → Clears context → Loads airis-mcp-gateway context

**Implementation**:
```python
class RepositoryContextManager:
    def __init__(self):
        self.current_repo = None
        self.context = {}

    def check_repository_change(self):
        """Detect if repository changed since last invocation."""
        new_repo = get_repository_root()

        if new_repo != self.current_repo:
            # Repository changed - clear context
            if self.current_repo:
                self.save_context(self.current_repo)

            self.current_repo = new_repo
            self.context = self.load_context(new_repo) if new_repo else {}

            return True  # Context cleared
        return False  # Same repository

    def load_context(self, repo_root: Path) -> dict:
        """Load repository-specific context."""
        memory_file = repo_root / ".superclaude" / "memory" / "pm_context.json"
        if memory_file.exists():
            return json.loads(memory_file.read_text())
        return {}

    def save_context(self, repo_root: Path):
        """Save current context to repository."""
        if not repo_root:
            return
        memory_file = repo_root / ".superclaude" / "memory" / "pm_context.json"
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        memory_file.write_text(json.dumps(self.context, indent=2))
```

**Usage in PM Agent**:
```python
# Session Start Protocol
context_mgr = RepositoryContextManager()
if context_mgr.check_repository_change():
    print(f"📍 Repository: {context_mgr.current_repo.name}")
    print(f"前回: {context_mgr.context.get('last_session', 'No previous session')}")
    print(f"進捗: {context_mgr.context.get('progress', 'Starting fresh')}")
```

---

### 4.4 .gitignore Integration

**Add to .gitignore**:
```gitignore
# SuperClaude Memory (session-specific, not for version control)
.superclaude/memory/

# Keep architectural decisions (optional - can be versioned)
# !.superclaude/memory/decisions/
```

**Rationale**:
- Session state changes frequently → should not be committed
- Architectural decisions MAY be versioned (team decision)
- Prevents accidental secret exposure in memory files

---

## 5. Future Enhancements (v2+)

### 5.1 Cross-Repository Intelligence

**When to implement**: After PM Agent demonstrates reliable single-repository context

**Architecture**:
```
~/.superclaude/
└── global_memory/
    ├── patterns/              # Cross-repo patterns
    │   ├── authentication.json
    │   └── testing.json
    └── repo_index/            # Repository metadata
        ├── SuperClaude_Framework.json
        └── airis-mcp-gateway.json
```

**Smart Context Selection**:
```python
def get_relevant_context(current_repo: str) -> dict:
    """Select context based on current repository."""
    # Local context (high priority)
    local = load_local_context(current_repo)

    # Global patterns (low priority, filtered by relevance)
    global_patterns = load_global_patterns()
    relevant = filter_by_similarity(global_patterns, local.get('tech_stack'))

    return merge_contexts(local, relevant, priority="local")
```

---

### 5.2 Vector Database Integration

**When to implement**: If SuperClaude requires semantic search across 100+ repositories

**Use Case**:
- "Find all authentication implementations across my projects"
- "What error handling patterns have I used successfully?"

**Technology**: pgvector, Qdrant, or Pinecone

**Cost-Benefit**: High complexity, only justified for "super-intelligence" tier features

---

## 6. Implementation Roadmap

### Phase 1: Repository-Scoped File Storage (Immediate)
**Timeline**: 1-2 weeks
**Effort**: Low

- [ ] Implement `get_repository_root()` detection
- [ ] Create `.superclaude/memory/` directory structure
- [ ] Integrate with PM Agent session lifecycle
- [ ] Add `.superclaude/memory/` to `.gitignore`
- [ ] Test repository change detection

**Success Criteria**:
- ✅ PM Agent context isolated per repository
- ✅ No noise from other projects
- ✅ Session resumes correctly within same repository

---

### Phase 2: PDCA Memory Integration (Short-term)
**Timeline**: 2-3 weeks
**Effort**: Medium

- [ ] Integrate Plan/Do/Check/Act with file storage
- [ ] Implement `docs/superclaude/patterns/` and `docs/superclaude/mistakes/`
- [ ] Create ADR (Architectural Decision Records) format
- [ ] Add 7-day cleanup for `docs/temp/`

**Success Criteria**:
- ✅ Successful patterns documented automatically
- ✅ Mistakes recorded with prevention checklists
- ✅ Knowledge accumulates within repository

---

### Phase 3: Cross-Repository Patterns (Future)
**Timeline**: 3-6 months
**Effort**: High

- [ ] Implement global pattern database
- [ ] Smart context filtering by tech stack
- [ ] Pattern similarity scoring
- [ ] Opt-in cross-repo intelligence

**Success Criteria**:
- ✅ PM Agent learns from past projects
- ✅ Suggests relevant patterns from other repos
- ✅ No performance degradation

---

## 7. Comparison Matrix

| Feature | Local Files | Database | Vector DB |
|---------|-------------|----------|-----------|
| **Performance** | ⭐⭐⭐⭐⭐ Fast | ⭐⭐⭐ Medium | ⭐⭐ Slow (network) |
| **Simplicity** | ⭐⭐⭐⭐⭐ Simple | ⭐⭐ Complex | ⭐ Very Complex |
| **Setup Time** | Minutes | Hours | Days |
| **ACID Transactions** | ❌ No | ✅ Yes | ✅ Yes |
| **Query Capabilities** | ⭐⭐ Basic | ⭐⭐⭐⭐⭐ SQL | ⭐⭐⭐⭐ Semantic |
| **Offline Support** | ✅ Yes | ⚠️ Depends | ❌ No |
| **Developer UX** | ⭐⭐⭐⭐⭐ Excellent | ⭐⭐⭐ Good | ⭐⭐ Fair |
| **Maintenance** | ⭐⭐⭐⭐⭐ None | ⭐⭐⭐ Regular | ⭐⭐ Intensive |

**Recommendation for SuperClaude v1**: **Local Files** (clear winner for repository-scoped memory)

---

## 8. Security Considerations

### 8.1 Sensitive Data Handling

**Problem**: Memory files may contain secrets, API keys, internal URLs
**Solution**: Automatic redaction + gitignore

```python
import re

SENSITIVE_PATTERNS = [
    r'sk_live_[a-zA-Z0-9]{24,}',  # Stripe keys
    r'eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*',  # JWT tokens
    r'ghp_[a-zA-Z0-9]{36}',  # GitHub tokens
]

def redact_sensitive_data(text: str) -> str:
    """Remove sensitive data before storing in memory."""
    for pattern in SENSITIVE_PATTERNS:
        text = re.sub(pattern, '[REDACTED]', text)
    return text
```

### 8.2 .gitignore Best Practices

**Always gitignore**:
- `.superclaude/memory/` (session state)
- `.superclaude/temp/` (temporary files)

**Optional versioning** (team decision):
- `.superclaude/memory/decisions/` (ADRs)
- `docs/superclaude/patterns/` (successful patterns)

---

## 9. Conclusion

### Key Takeaways

1. **✅ Local File Storage is Optimal**: Industry standard for repository-scoped context
2. **✅ Git Detection is Standard**: Use `git rev-parse --show-toplevel`
3. **✅ Start Simple, Evolve Later**: Files → Database (if needed) → Vector DB (far future)
4. **✅ Repository Isolation is Critical**: Prevents context noise across projects

### Recommended Architecture for SuperClaude

```
SuperClaude_Framework/
├── .git/
├── .gitignore (+.superclaude/memory/)
├── .superclaude/
│   └── memory/
│       ├── pm_context.json       # Current session state
│       ├── plan.json             # PDCA Plan phase
│       ├── experiment.json       # PDCA Do phase
│       └── evaluation.json       # PDCA Check phase
└── docs/
    └── superclaude/
        ├── patterns/             # Successful implementations
        │   └── authentication-jwt.md
        └── mistakes/             # Error prevention
            └── mistake-2025-10-16.md
```

**Next Steps**:
1. Implement `RepositoryContextManager` class
2. Integrate with PM Agent session lifecycle
3. Add `.superclaude/memory/` to `.gitignore`
4. Test with repository switching scenarios
5. Document for team adoption

---

**Research Confidence**: High (based on industry standards from Cursor, GitHub Copilot, and security best practices)

**Sources**:
- Cursor IDE memory management architecture
- GitHub Copilot workspace context documentation
- Enterprise AI security frameworks
- Git repository detection patterns
- Storage performance benchmarks

**Last Updated**: 2025-10-16
**Next Review**: After Phase 1 implementation (2-3 weeks)
