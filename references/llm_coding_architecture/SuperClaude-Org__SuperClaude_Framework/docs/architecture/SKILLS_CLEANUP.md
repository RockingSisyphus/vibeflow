# Skills Cleanup for Clean Architecture

**Date**: 2025-10-21
**Issue**: `~/.claude/skills/` に古いSkillsが残っている
**Impact**: Claude Code起動時に約64KB (15K tokens) 読み込んでいる可能性

---

## 📊 現状

### ~/.claude/skills/ の内容

```bash
$ ls ~/.claude/skills/
brainstorming-mode
business-panel-mode
deep-research-mode
introspection-mode
orchestration-mode
pm                          # ← PM Agent Skill
pm.backup                   # ← バックアップ
task-management-mode
token-efficiency-mode
```

### サイズ確認

```bash
$ wc -c ~/.claude/skills/*/implementation.md ~/.claude/skills/*/SKILL.md
   64394 total  # 約64KB ≈ 15K tokens
```

---

## 🎯 クリーンアーキテクチャでの扱い

### 新アーキテクチャ

**PM Agent Core** → `src/superclaude/pm_agent/`
- Python modulesとして実装
- pytest fixturesで利用
- `~/.claude/` 汚染なし

**Skills (オプション)** → ユーザーが明示的にインストール
```bash
superclaude install-skill pm-agent
# → ~/.claude/skills/pm/ にコピー
```

---

## ⚠️ 問題：Skills自動読み込み

### Claude Codeの動作（推測）

```yaml
起動時:
  1. ~/.claude/ をスキャン
  2. skills/ 配下の全 *.md を読み込み
  3. implementation.md を Claude に渡す

Result: 64KB = 約15K tokens消費
```

### 影響

現在のローカル環境では：
- ✅ `src/superclaude/pm_agent/` - 新実装（使用中）
- ❌ `~/.claude/skills/pm/` - 古いSkill（残骸）
- ❌ `~/.claude/skills/*-mode/` - 他のSkills（残骸）

**重複読み込み**: 新旧両方が読み込まれている可能性

---

## 🧹 クリーンアップ手順

### Option 1: 全削除（推奨 - クリーンアーキテクチャ完全移行）

```bash
# バックアップ作成
mv ~/.claude/skills ~/.claude/skills.backup.$(date +%Y%m%d)

# 確認
ls ~/.claude/skills
# → "No such file or directory" になればOK
```

**効果**:
- ✅ 15K tokens回復
- ✅ クリーンな状態
- ✅ 新アーキテクチャのみ

---

### Option 2: PM Agentのみ削除

```bash
# PM Agentだけ削除（新実装があるため）
rm -rf ~/.claude/skills/pm
rm -rf ~/.claude/skills/pm.backup

# 他のSkillsは残す
ls ~/.claude/skills/
# → brainstorming-mode, business-panel-mode, etc. 残る
```

**効果**:
- ✅ PM Agent重複解消（約3K tokens回復）
- ✅ 他のSkillsは使える
- ❌ 他のSkillsのtoken消費は続く（約12K）

---

### Option 3: 必要なSkillsのみ残す

```bash
# 使っているSkillsを確認
cd ~/.claude/skills
ls -la

# 使わないものを削除
rm -rf brainstorming-mode     # 使ってない
rm -rf business-panel-mode    # 使ってない
rm -rf pm pm.backup           # 新実装あり

# 必要なものだけ残す
# deep-research-mode → 使ってる
# orchestration-mode → 使ってる
```

**効果**:
- ✅ カスタマイズ可能
- ⚠️ 手動管理必要

---

## 📋 推奨アクション

### Phase 3実施前

**1. バックアップ作成**
```bash
cp -r ~/.claude/skills ~/.claude/skills.backup.$(date +%Y%m%d)
```

**2. 古いPM Agent削除**
```bash
rm -rf ~/.claude/skills/pm
rm -rf ~/.claude/skills/pm.backup
```

**3. 動作確認**
```bash
# 新PM Agentが動作することを確認
make verify
uv run pytest tests/pm_agent/ -v
```

**4. トークン削減確認**
```bash
# Claude Code再起動して体感確認
# Context window利用可能量が増えているはず
```

---

### Phase 3以降（完全移行後）

**Option A: 全Skillsクリーン（最大効果）**
```bash
# 全Skills削除
rm -rf ~/.claude/skills

# 効果: 15K tokens回復
```

**Option B: 選択的削除**
```bash
# PM Agent系のみ削除
rm -rf ~/.claude/skills/pm*

# 他のSkillsは残す（deep-research, orchestration等）
# 効果: 3K tokens回復
```

---

## 🎯 PR準備への影響

### Before/After比較データ

**Before (現状)**:
```
Context consumed at startup:
- MCP tools: 5K tokens (AIRIS Gateway)
- Skills (全部): 15K tokens ← 削除対象
- SuperClaude: 0K tokens (未インストール状態想定)
─────────────────────────────
Total: 20K tokens
Available: 180K tokens
```

**After (クリーンアップ後)**:
```
Context consumed at startup:
- MCP tools: 5K tokens (AIRIS Gateway)
- Skills: 0K tokens ← 削除完了
- SuperClaude pytest plugin: 0K tokens (pytestなし時)
─────────────────────────────
Total: 5K tokens
Available: 195K tokens
```

**Improvement**: +15K tokens (7.5%改善)

---

## ⚡ 即時実行推奨コマンド

```bash
# 安全にバックアップ取りながら削除
cd ~/.claude
mv skills skills.backup.20251021
mkdir skills  # 空のディレクトリ作成（Claude Code用）

# 確認
ls -la skills/
# → 空になっていればOK
```

**効果**:
- ✅ 即座に15K tokens回復
- ✅ いつでも復元可能（backup残してる）
- ✅ クリーンな環境でテスト可能

---

**ステータス**: 実行待ち
**推奨**: Option 1 (全削除) - クリーンアーキテクチャ完全移行のため
