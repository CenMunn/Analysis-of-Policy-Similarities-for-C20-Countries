# 清洗规则阅读指南

总入口仍为 `pipeline.py`，由 `src/data_cleaning.py` 调用。子文件夹按功能分类，不表示严格的执行先后顺序。文件名与函数名保留，便于对照原报告。

| 中文分区 | 代码文件 |
|---|---|
| 读取与规范化 | `ingest.py`、`cleaning.py`、`template_cleaning.py`、`text_normalization.py` |
| 政策内容判定 | `topic_rules.py`、`quality_rules.py`、`assertion_guard.py`、`assertion_scope.py`、`assertion_revision.py`、`current_assertion_guard.py`、`semantic_scope.py`、`policy_boundary.py` |
| 主体与国家归属 | `entities.py`、`role_patterns.py`、`sentence_roles.py`、`role_resolution.py`、`national_scope.py`、`optimized_attribution.py`、`scoped_roles.py` |
| 上下文与证据连接 | `evidence_scope.py`、`context_scope.py`、`linked_policy_resolution.py` |
| 事实修补与补漏 | `content_repair.py`、`recall_rules.py`、`fact_correction.py`、`fact_revision.py`、`coverage_repair.py`、`focused_review.py`、`event_fact_parts.py`、`nested_policy_recall.py`、`final_fact_refiner.py`、`literal_boundary.py`、`terminal_scope.py` |
| 政策归并与导出 | `policy_registry.py`、`registry_primitives.py`、`exports.py` |
| 公共工具 | `identifiers.py`、`io_utils.py`、`reuse_guard.py` |

S(c) 的实现位于 `主体与国家归属/optimized_attribution.py` 的 `score_candidates`。

跨分区依赖使用显式相对导入；请从项目根目录运行 `运行实验.py` 或双击 `一键运行.cmd`，不要单独运行内部模块。中文目录采用 UTF-8，无需新增依赖。

课堂模式复用受校验的识别账本及BGE编码，重新计算后续流程；完整识别使用 `--mode full`。目录整理未改变这两种模式的含义。
