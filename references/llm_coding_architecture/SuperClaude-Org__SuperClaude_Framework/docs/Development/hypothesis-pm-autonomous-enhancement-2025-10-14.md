# PM Agent Autonomous Enhancement - 改善提案

> **Date**: 2025-10-14
> **Status**: 提案中（ユーザーレビュー待ち）
> **Goal**: ユーザーインプット最小化 + 確信を持った先回り提案

---

## 🎯 現状の問題点

### 既存の `superclaude/commands/pm.md`
```yaml
良い点:
  ✅ PDCAサイクルが定義されている
  ✅ サブエージェント連携が明確
  ✅ ドキュメント記録の仕組みがある

改善が必要な点:
  ❌ ユーザーインプット依存度が高い
  ❌ 調査フェーズが受動的
  ❌ 提案が「どうしますか？」スタイル
  ❌ 確信を持った提案がない
```

---

## 💡 改善提案

### Phase 0: **自律的調査フェーズ**（新規追加）

#### ユーザーリクエスト受信時の自動実行
```yaml
Auto-Investigation (許可不要・自動実行):
  1. Context Restoration:
     - Read docs/Development/tasks/current-tasks.md
     - list_memories() → 前回のセッション確認
     - read_memory("project_context") → プロジェクト理解
     - read_memory("past_mistakes") → 過去の失敗確認

  2. Project Analysis:
     - Read CLAUDE.md → プロジェクト固有ルール
     - Glob **/*.md → ドキュメント構造把握
     - mcp__serena__get_symbols_overview → コード構造理解
     - Grep "TODO\|FIXME\|XXX" → 既知の課題確認

  3. Current State Assessment:
     - Bash "git status" → 現在の状態
     - Bash "git log -5 --oneline" → 最近の変更
     - Read tests/ → テストカバレッジ確認
     - Security scan → セキュリティリスク確認

  4. Competitive Research (必要時):
     - tavily search → ベストプラクティス調査
     - context7 → 公式ドキュメント参照
     - Deep Research → 競合サービス分析

  5. Architecture Evaluation:
     - 既存アーキテクチャの強み分析
     - 技術スタックの特徴把握
     - 拡張可能性の評価
```

#### 出力形式
```markdown
📊 自律調査完了

現状分析:
  - プロジェクト: [名前]（[技術スタック]）
  - 進捗: [前回セッションの続き or 新規タスク]
  - コードベース: [ファイル数]、テストカバレッジ [%]
  - 既知の課題: [TODO/FIXME数]
  - 最近の変更: [git log要約]

アーキテクチャの強み:
  - [強み1]: [具体的な理由]
  - [強み2]: [具体的な理由]

不足している要素:
  - [不足1]: [影響]
  - [不足2]: [影響]
```

---

### Phase 1: **確信を持った提案**（強化）

#### ❌ 改善前（受動的）
```
User: "認証機能作って"

PM Agent: "認証機能を実装しますね。
          どんな認証方式がいいですか？"

→ ユーザーに丸投げ
```

#### ✅ 改善後（能動的・確信あり）
```
User: "認証機能作って"

PM Agent:
  📊 自律調査完了（3秒）:
     - 既存: Supabase統合済み（強み）
     - 不足: 認証機能なし
     - テスト: カバレッジ45%（目標80%）
     - 競合調査: Auth0、Clerk、Supabase Auth比較済み
     - セキュリティ: OWASP推奨3項目未対応

  💡 確信を持った提案:

     このアーキテクチャはSupabase連携に強みがあるため、
     **Supabase Auth統合**を推奨します。

     具体的な実装方針:
     1. Supabase Auth統合（JWT + リフレッシュトークン）
     2. MFA対応（TOTP実装）
     3. セキュリティテスト追加（カバレッジ85%目標）
     4. 既存APIとのシームレス統合

     選択理由:
     ✅ 既存のSupabase接続再利用（実装コスト最小）
     ✅ エンタープライズグレードのセキュリティ
     ✅ 無料枠で十分な機能（コスト効率◎）
     ✅ 将来のスケーラビリティ確保

     代替案との比較:
     - Auth0: 月$25〜、実装複雑度高
     - Clerk: 月$25〜、React特化（このプロジェクトはNext.js）
     - Supabase Auth: 無料、既存統合済み ← 推奨

     この方針で進めてよろしいですか？
```

---

### Phase 2: **自律実行**（既存を強化）

#### 承認後の自動フロー
```yaml
User: "OK"

PM Agent（完全自律実行）:
  1. Architecture Design:
     - system-architect: Supabase Auth設計
     - security-engineer: セキュリティレビュー

  2. Implementation:
     - backend-architect: API統合実装
     - frontend-architect: UI実装
     - Load magic: Login/Register components

  3. Testing:
     - Write tests/auth/*.test.ts
     - pytest実行 → 失敗検出

  4. Self-Correction:
     - context7 → Supabase公式ドキュメント確認
     - エラー原因特定: "JWTシークレット未設定"
     - 修正実装
     - 再テスト → 合格

  5. Documentation:
     - Update docs/patterns/supabase-auth-integration.md
     - Update CLAUDE.md（認証パターン追加）
     - write_memory("success_pattern", 詳細)

  6. Report:
     ✅ 認証機能実装完了

     実装内容:
     - Supabase Auth統合（JWT + リフレッシュ）
     - MFA対応（TOTP）
     - テストカバレッジ: 45% → 87%（目標達成）
     - セキュリティ: OWASP準拠確認済み

     学習記録:
     - 成功パターン: docs/patterns/supabase-auth-integration.md
     - 遭遇したエラー: JWT設定不足（修正済み）
     - 次回の改善: 環境変数チェックリスト更新
```

---

## 🔧 実装方針

### `superclaude/commands/pm.md` への追加セクション

#### 1. Autonomous Investigation Phase（新規）
```markdown
## Phase 0: Autonomous Investigation (Auto-Execute)

**Trigger**: Any user request received

**Execution**: Automatic, no permission required

### Investigation Steps:
1. **Context Restoration**
   - Read `docs/Development/tasks/current-tasks.md`
   - Serena memory restoration
   - Project context loading

2. **Project Analysis**
   - CLAUDE.md → Project rules
   - Code structure analysis
   - Test coverage check
   - Security scan
   - Known issues detection (TODO/FIXME)

3. **Competitive Research** (when relevant)
   - Best practices research (Tavily)
   - Official documentation (Context7)
   - Alternative solutions analysis

4. **Architecture Evaluation**
   - Identify architectural strengths
   - Detect technology stack characteristics
   - Assess extensibility

### Output Format:
```
📊 Autonomous Investigation Complete

Current State:
  - Project: [name] ([stack])
  - Progress: [status]
  - Codebase: [files count], Test Coverage: [%]
  - Known Issues: [count]
  - Recent Changes: [git log summary]

Architectural Strengths:
  - [strength 1]: [rationale]
  - [strength 2]: [rationale]

Missing Elements:
  - [gap 1]: [impact]
  - [gap 2]: [impact]
```
```

#### 2. Confident Proposal Phase（強化）
```markdown
## Phase 1: Confident Proposal (Enhanced)

**Principle**: Never ask "What do you want?" - Always propose with conviction

### Proposal Format:
```
💡 Confident Proposal:

[Implementation approach] is recommended.

Specific Implementation Plan:
1. [Step 1 with rationale]
2. [Step 2 with rationale]
3. [Step 3 with rationale]

Selection Rationale:
✅ [Reason 1]: [Evidence]
✅ [Reason 2]: [Evidence]
✅ [Reason 3]: [Evidence]

Alternatives Considered:
- [Alt 1]: [Why not chosen]
- [Alt 2]: [Why not chosen]
- [Recommended]: [Why chosen] ← Recommended

Proceed with this approach?
```

### Anti-Patterns (Never Do):
❌ "What authentication do you want?" (Passive)
❌ "How should we implement this?" (Uncertain)
❌ "There are several options..." (Indecisive)

✅ "Supabase Auth is recommended because..." (Confident)
✅ "Based on your architecture's Supabase integration..." (Evidence-based)
```

#### 3. Autonomous Execution Phase（既存を明示化）
```markdown
## Phase 2: Autonomous Execution

**Trigger**: User approval ("OK", "Go ahead", "Yes")

**Execution**: Fully autonomous, systematic PDCA

### Self-Correction Loop:
```yaml
Implementation:
  - Execute with sub-agents
  - Write comprehensive tests
  - Run validation

Error Detected:
  → Context7: Check official documentation
  → Identify root cause
  → Implement fix
  → Re-test
  → Repeat until passing

Success:
  → Document pattern (docs/patterns/)
  → Update learnings (write_memory)
  → Report completion with evidence
```

### Quality Gates:
- Tests must pass (no exceptions)
- Coverage targets must be met
- Security checks must pass
- Documentation must be updated
```

---

## 📊 期待される効果

### Before (現状)
```yaml
User Input Required: 高
  - 認証方式の選択
  - 実装方針の決定
  - エラー対応の指示
  - テスト方針の決定

Proposal Quality: 受動的
  - "どうしますか？"スタイル
  - 選択肢の羅列のみ
  - ユーザーが決定

Execution: 半自動
  - エラー時にユーザーに報告
  - 修正方針をユーザーが指示
```

### After (改善後)
```yaml
User Input Required: 最小
  - "認証機能作って"のみ
  - 提案への承認/拒否のみ

Proposal Quality: 能動的・確信あり
  - 調査済みの根拠提示
  - 明確な推奨案
  - 代替案との比較

Execution: 完全自律
  - エラー自己修正
  - 公式ドキュメント自動参照
  - テスト合格まで自動実行
  - 学習自動記録
```

### 定量的目標
- ユーザーインプット削減: **80%削減**
- 提案品質向上: **確信度90%以上**
- 自律実行成功率: **95%以上**

---

## 🚀 実装ステップ

### Step 1: pm.md 修正
- [ ] Phase 0: Autonomous Investigation 追加
- [ ] Phase 1: Confident Proposal 強化
- [ ] Phase 2: Autonomous Execution 明示化
- [ ] Examples セクションに具体例追加

### Step 2: テスト作成
- [ ] `tests/test_pm_autonomous.py`
- [ ] 自律調査フローのテスト
- [ ] 確信提案フォーマットのテスト
- [ ] 自己修正ループのテスト

### Step 3: 動作確認
- [ ] 開発版インストール
- [ ] 実際のワークフローで検証
- [ ] フィードバック収集

### Step 4: 学習記録
- [ ] `docs/patterns/pm-autonomous-workflow.md`
- [ ] 成功パターンの文書化

---

## ✅ ユーザー承認待ち

**この方針で実装を進めてよろしいですか？**

承認いただければ、すぐに `superclaude/commands/pm.md` の修正を開始します。
