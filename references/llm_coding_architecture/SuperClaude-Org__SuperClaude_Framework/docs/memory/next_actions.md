# Next Actions

**Updated**: 2025-10-17
**Priority**: Testing & Validation → Metrics Collection

---

## 🎯 Immediate Actions (今週)

### 1. pytest環境セットアップ (High Priority)

**Purpose**: テストスイート実行環境を構築

**Dependencies**: なし
**Owner**: PM Agent + DevOps

**Steps**:
```bash
# Option 1: Docker環境でセットアップ (推奨)
docker compose exec workspace sh
pip install pytest pytest-cov scipy

# Option 2: 仮想環境でセットアップ
python -m venv .venv
source .venv/bin/activate
pip install pytest pytest-cov scipy
```

**Success Criteria**:
- ✅ pytest実行可能
- ✅ scipy (t-test) 動作確認
- ✅ pytest-cov (カバレッジ) 動作確認

**Estimated Time**: 30分

---

### 2. テスト実行 & 検証 (High Priority)

**Purpose**: 品質保証層の実動作確認

**Dependencies**: pytest環境セットアップ完了
**Owner**: Quality Engineer + PM Agent

**Commands**:
```bash
# 全テスト実行
pytest tests/pm_agent/ -v

# マーカー別実行
pytest tests/pm_agent/ -m unit           # Unit tests
pytest tests/pm_agent/ -m integration    # Integration tests
pytest tests/pm_agent/ -m hallucination  # Hallucination detection
pytest tests/pm_agent/ -m performance    # Performance tests

# カバレッジレポート
pytest tests/pm_agent/ --cov=. --cov-report=html
```

**Expected Results**:
```yaml
Hallucination Detection: ≥94%
Token Budget Compliance: 100%
Confidence Accuracy: >85%
Error Recurrence: <10%
All Tests: PASS
```

**Estimated Time**: 1時間

---

## 🚀 Short-term Actions (次スプリント)

### 3. メトリクス収集の実運用開始 (Week 2-3)

**Purpose**: 実際のワークフローでデータ蓄積

**Steps**:
1. **初回データ収集**:
   - 通常タスク実行時に自動記録
   - 1週間分のデータ蓄積 (目標: 20-30タスク)

2. **初回週次分析**:
   ```bash
   python scripts/analyze_workflow_metrics.py --period week
   ```

3. **結果レビュー**:
   - タスクタイプ別トークン使用量
   - 成功率確認
   - 非効率パターン特定

**Success Criteria**:
- ✅ 20+タスクのメトリクス記録
- ✅ 週次レポート生成成功
- ✅ トークン削減率が期待値内 (60%平均)

**Estimated Time**: 1週間 (自動記録)

---

### 4. A/B Testing Framework起動 (Week 3-4)

**Purpose**: 実験的ワークフローの検証

**Steps**:
1. **Experimental Variant設計**:
   - 候補: `experimental_eager_layer3` (Medium tasksで常にLayer 3)
   - 仮説: より多くのコンテキストで精度向上

2. **80/20配分実装**:
   ```yaml
   Allocation:
     progressive_v3_layer2: 80%  # Current best
     experimental_eager_layer3: 20%  # New variant
   ```

3. **20試行後の統計分析**:
   ```bash
   python scripts/ab_test_workflows.py \
     --variant-a progressive_v3_layer2 \
     --variant-b experimental_eager_layer3 \
     --metric tokens_used
   ```

4. **判定**:
   - p < 0.05 → 統計的有意
   - 成功率 ≥95% → 品質維持
   - → 勝者を標準ワークフローに昇格

**Success Criteria**:
- ✅ 各variant 20+試行
- ✅ 統計的有意性確認 (p < 0.05)
- ✅ 改善確認 OR 現状維持判定

**Estimated Time**: 2週間

---

## 🔮 Long-term Actions (Future Sprints)

### 5. Advanced Features (Month 2-3)

**Multi-agent Confidence Aggregation**:
- 複数sub-agentの確信度を統合
- 投票メカニズム (majority vote)
- Weight付き平均 (expertise-based)

**Predictive Error Detection**:
- 過去エラーパターン学習
- 類似コンテキスト検出
- 事前警告システム

**Adaptive Budget Allocation**:
- タスク特性に応じた動的予算
- ML-based prediction (過去データから学習)
- Real-time adjustment

**Cross-session Learning Patterns**:
- セッション跨ぎパターン認識
- Long-term trend analysis
- Seasonal patterns detection

---

### 6. Integration Enhancements (Month 3-4)

**mindbase Vector Search Optimization**:
- Semantic similarity threshold tuning
- Query embedding optimization
- Cache hit rate improvement

**Reflexion Pattern Refinement**:
- Error categorization improvement
- Solution reusability scoring
- Automatic pattern extraction

**Evidence Requirement Automation**:
- Auto-evidence collection
- Automated test execution
- Result parsing and validation

**Continuous Learning Loop**:
- Auto-pattern formalization
- Self-improving workflows
- Knowledge base evolution

---

## 📊 Success Metrics

### Phase 1: Testing (今週)
```yaml
Goal: 品質保証層確立
Metrics:
  - All tests pass: 100%
  - Hallucination detection: ≥94%
  - Token efficiency: 60% avg
  - Error recurrence: <10%
```

### Phase 2: Metrics Collection (Week 2-3)
```yaml
Goal: データ蓄積開始
Metrics:
  - Tasks recorded: ≥20
  - Data quality: Clean (no null errors)
  - Weekly report: Generated
  - Insights: ≥3 actionable findings
```

### Phase 3: A/B Testing (Week 3-4)
```yaml
Goal: 科学的ワークフロー改善
Metrics:
  - Trials per variant: ≥20
  - Statistical significance: p < 0.05
  - Winner identified: Yes
  - Implementation: Promoted or deprecated
```

---

## 🛠️ Tools & Scripts Ready

**Testing**:
- ✅ `tests/pm_agent/` (2,760行)
- ✅ `pytest.ini` (configuration)
- ✅ `conftest.py` (fixtures)

**Metrics**:
- ✅ `docs/memory/workflow_metrics.jsonl` (initialized)
- ✅ `docs/memory/WORKFLOW_METRICS_SCHEMA.md` (spec)

**Analysis**:
- ✅ `scripts/analyze_workflow_metrics.py` (週次分析)
- ✅ `scripts/ab_test_workflows.py` (A/Bテスト)

---

## 📅 Timeline

```yaml
Week 1 (Oct 17-23):
  - Day 1-2: pytest環境セットアップ
  - Day 3-4: テスト実行 & 検証
  - Day 5-7: 問題修正 (if any)

Week 2-3 (Oct 24 - Nov 6):
  - Continuous: メトリクス自動記録
  - Week end: 初回週次分析

Week 3-4 (Nov 7 - Nov 20):
  - Start: Experimental variant起動
  - Continuous: 80/20 A/B testing
  - End: 統計分析 & 判定

Month 2-3 (Dec - Jan):
  - Advanced features implementation
  - Integration enhancements
```

---

## ⚠️ Blockers & Risks

**Technical Blockers**:
- pytest未インストール → Docker環境で解決
- scipy依存 → pip install scipy
- なし（その他）

**Risks**:
- テスト失敗 → 境界条件調整が必要
- メトリクス収集不足 → より多くのタスク実行
- A/B testing判定困難 → サンプルサイズ増加

**Mitigation**:
- ✅ テスト設計時に境界条件考慮済み
- ✅ メトリクススキーマは柔軟
- ✅ A/Bテストは統計的有意性で自動判定

---

## 🤝 Dependencies

**External Dependencies**:
- Python packages: pytest, scipy, pytest-cov
- Docker環境: (Optional but recommended)

**Internal Dependencies**:
- pm.md specification (Line 870-1016)
- Workflow metrics schema
- Analysis scripts

**None blocking**: すべて準備完了 ✅

---

**Next Session Priority**: pytest環境セットアップ → テスト実行

**Status**: Ready to proceed ✅
