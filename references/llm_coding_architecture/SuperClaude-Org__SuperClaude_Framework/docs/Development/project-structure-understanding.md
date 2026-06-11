# SuperClaude Framework - Project Structure Understanding

> **Critical Understanding**: このプロジェクトとインストール後の環境の関係

---

## 🏗️ 2つの世界の区別

### 1. このプロジェクト（Git管理・開発環境）

**Location**: `~/github/SuperClaude_Framework/`

**Role**: ソースコード・開発・テスト

```
SuperClaude_Framework/
├── setup/                  # インストーラーロジック
│   ├── components/         # コンポーネント定義（何をインストールするか）
│   ├── data/              # 設定データ（JSON/YAML）
│   ├── cli/               # CLIインターフェース
│   ├── utils/             # ユーティリティ関数
│   └── services/          # サービスロジック
│
├── superclaude/           # ランタイムロジック（実行時の動作）
│   ├── core/             # コア機能
│   ├── modes/            # 行動モード
│   ├── agents/           # エージェント定義
│   ├── mcp/              # MCPサーバー統合
│   └── commands/         # コマンド実装
│
├── tests/                # テストコード
├── docs/                 # 開発者向けドキュメント
├── pyproject.toml        # Python設定
└── package.json          # npm設定
```

**Operations**:
- ✅ ソースコード変更
- ✅ Git コミット・PR
- ✅ テスト実行
- ✅ ドキュメント作成
- ✅ バージョン管理

---

### 2. インストール後（ユーザー環境・Git管理外）

**Location**: `~/.claude/`

**Role**: 実際に動作する設定・コマンド（ユーザー環境）

```
~/.claude/
├── commands/
│   └── sc/              # スラッシュコマンド（インストール後）
│       ├── pm.md
│       ├── implement.md
│       ├── test.md
│       └── ... (26 commands)
│
├── CLAUDE.md            # グローバル設定（インストール後）
├── *.md                 # モード定義（インストール後）
│   ├── MODE_Brainstorming.md
│   ├── MODE_Orchestration.md
│   └── ...
│
└── .claude.json         # Claude Code設定
```

**Operations**:
- ✅ **読むだけ**（理解・確認用）
- ✅ 動作確認
- ⚠️ テスト時のみ一時変更（**必ず元に戻す！**）
- ❌ 永続的な変更禁止（Git追跡不可）

---

## 🔄 インストールフロー

### ユーザー操作
```bash
# 1. インストール
pipx install SuperClaude
# または
npm install -g @bifrost_inc/superclaude

# 2. セットアップ実行
SuperClaude install
```

### 内部処理（setup/が実行）
```python
# setup/components/*.py が実行される

1. ~/.claude/ ディレクトリ作成
2. commands/sc/ にスラッシュコマンド配置
3. CLAUDE.md と各種 *.md 配置
4. .claude.json 更新
5. MCPサーバー設定
```

### 結果
- **このプロジェクトのファイル** → **~/.claude/ にコピー**
- ユーザーがClaude起動 → `~/.claude/` の設定が読み込まれる
- `/sc:pm` 実行 → `~/.claude/commands/sc/pm.md` が展開される

---

## 📝 開発ワークフロー

### ❌ 間違った方法
```bash
# Git管理外を直接変更
vim ~/.claude/commands/sc/pm.md  # ← ダメ！履歴追えない

# 変更テスト
claude  # 動作確認

# 変更が ~/.claude/ に残る
# → 元に戻すの忘れる
# → 設定がぐちゃぐちゃになる
# → Gitで追跡できない
```

### ✅ 正しい方法

#### Step 1: 既存実装を理解
```bash
cd ~/github/SuperClaude_Framework

# インストールロジック確認
Read setup/components/commands.py    # コマンドのインストール方法
Read setup/components/modes.py       # モードのインストール方法
Read setup/data/commands.json        # コマンド定義データ

# インストール後の状態確認（理解のため）
ls ~/.claude/commands/sc/
cat ~/.claude/commands/sc/pm.md      # 現在の仕様確認

# 「なるほど、setup/components/commands.py でこう処理されて、
#  ~/.claude/commands/sc/ に配置されるのね」
```

#### Step 2: 改善案をドキュメント化
```bash
cd ~/github/SuperClaude_Framework

# Git管理されているこのプロジェクト内で
Write docs/Development/hypothesis-pm-improvement-YYYY-MM-DD.md

# 内容例:
# - 現状の問題
# - 改善案
# - 実装方針
# - 期待される効果
```

#### Step 3: テストが必要な場合
```bash
# バックアップ作成（必須！）
cp ~/.claude/commands/sc/pm.md ~/.claude/commands/sc/pm.md.backup

# 実験的変更
vim ~/.claude/commands/sc/pm.md

# Claude起動して検証
claude
# ... 動作確認 ...

# テスト完了後、必ず復元！！
mv ~/.claude/commands/sc/pm.md.backup ~/.claude/commands/sc/pm.md
```

#### Step 4: 本実装
```bash
cd ~/github/SuperClaude_Framework

# ソースコード側で変更
Edit setup/components/commands.py    # インストールロジック修正
Edit setup/data/commands/pm.md       # コマンド仕様修正

# テスト追加
Write tests/test_pm_command.py

# テスト実行
pytest tests/test_pm_command.py -v

# コミット（Git履歴に残る）
git add setup/ tests/
git commit -m "feat: enhance PM command with autonomous workflow"
```

#### Step 5: 動作確認
```bash
# 開発版インストール
cd ~/github/SuperClaude_Framework
pip install -e .

# または
SuperClaude install --dev

# 実際の環境でテスト
claude
/sc:pm "test request"
```

---

## 🎯 重要なルール

### Rule 1: Git管理の境界を守る
- **変更**: このプロジェクト内のみ
- **確認**: `~/.claude/` は読むだけ
- **テスト**: バックアップ → 変更 → 復元

### Rule 2: テスト時は必ず復元
```bash
# テスト前
cp original backup

# テスト
# ... 実験 ...

# テスト後（必須！）
mv backup original
```

### Rule 3: ドキュメント駆動開発
1. 理解 → docs/Development/ に記録
2. 仮説 → docs/Development/hypothesis-*.md
3. 実験 → docs/Development/experiment-*.md
4. 成功 → docs/patterns/
5. 失敗 → docs/mistakes/

---

## 📚 理解すべきファイル

### インストーラー側（setup/）
```python
# 優先度: 高
setup/components/commands.py    # コマンドインストール
setup/components/modes.py       # モードインストール
setup/components/agents.py      # エージェント定義
setup/data/commands/*.md        # コマンド仕様（ソース）
setup/data/modes/*.md           # モード仕様（ソース）

# これらが ~/.claude/ に配置される
```

### ランタイム側（superclaude/）
```python
# 優先度: 中
superclaude/__main__.py         # CLIエントリーポイント
superclaude/core/              # コア機能実装
superclaude/agents/            # エージェントロジック
```

### インストール後（~/.claude/）
```markdown
# 優先度: 理解のため（変更不可）
~/.claude/commands/sc/pm.md    # 実際に動くPM仕様
~/.claude/MODE_*.md            # 実際に動くモード仕様
~/.claude/CLAUDE.md            # 実際に読み込まれるグローバル設定
```

---

## 🔍 デバッグ方法

### インストール確認
```bash
# インストール済みコンポーネント確認
SuperClaude install --list-components

# インストール先確認
ls -la ~/.claude/commands/sc/
ls -la ~/.claude/*.md
```

### 動作確認
```bash
# Claude起動
claude

# コマンド実行
/sc:pm "test"

# ログ確認（必要に応じて）
tail -f ~/.claude/logs/*.log
```

### トラブルシューティング
```bash
# 設定が壊れた場合
SuperClaude install --force    # 再インストール

# 開発版に切り替え
cd ~/github/SuperClaude_Framework
pip install -e .

# 本番版に戻す
pip uninstall superclaude
pipx install SuperClaude
```

---

## 💡 よくある間違い

### 間違い1: Git管理外を変更
```bash
# ❌ WRONG
vim ~/.claude/commands/sc/pm.md
git add ~/.claude/  # ← できない！Git管理外
```

### 間違い2: バックアップなしテスト
```bash
# ❌ WRONG
vim ~/.claude/commands/sc/pm.md
# テスト...
# 元に戻すの忘れる → 設定ぐちゃぐちゃ
```

### 間違い3: ソース確認せずに変更
```bash
# ❌ WRONG
「PMモード直したい」
→ いきなり ~/.claude/ 変更
→ ソースコード理解してない
→ 再インストールで上書きされる
```

### 正解
```bash
# ✅ CORRECT
1. setup/components/ でロジック理解
2. docs/Development/ に改善案記録
3. setup/ 側で変更・テスト
4. Git コミット
5. SuperClaude install --dev で動作確認
```

---

## 🚀 次のステップ

このドキュメント理解後:

1. **setup/components/ 読解**
   - インストールロジックの理解
   - どこに何が配置されるか

2. **既存仕様の把握**
   - `~/.claude/commands/sc/pm.md` 確認（読むだけ）
   - 現在の動作理解

3. **改善提案作成**
   - `docs/Development/hypothesis-*.md` 作成
   - ユーザーレビュー

4. **実装・テスト**
   - `setup/` 側で変更
   - `tests/` でテスト追加
   - Git管理下で開発

これで**何百回も同じ説明をしなくて済む**ようになる。
