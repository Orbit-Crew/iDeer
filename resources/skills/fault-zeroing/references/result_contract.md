<!--
本文件由 scripts/generate_fault_zeroing_contract_artifacts.py 生成。
唯一来源：backend/app/agentplatform/fault_zeroing/contract.py（Result Contract v1.0.0）。
请勿手改：契约规则改动只改契约模块，然后重新运行生成脚本并一并提交。
-->

# Result Contract 声明式内容（生成副本）

工作流节点提示词与 SKILL/SOUL 文案引用本文件，不复述其中的清单与短语；
本文件是契约模块在沙箱内可读的生成副本，随契约重新生成，禁止在此另立规则。

## 五件产物清单（REQUIRED_OUTPUTS）

| # | 产物 |
| --- | --- |
| 1 | `fault_tree.json` |
| 2 | `fault_tree.svg` |
| 3 | `bottom_event_assessment.md` |
| 4 | `analysis_process.svg` |
| 5 | `zeroing_report.md` |

缺任一产物即违反契约（fail-closed）：Run 终态 failed，违规清单记入 Run 记录，产物保留供检查；
含待验证披露的完整披露性结果仍是有效完成。

## zeroing_report.md 必须包含的报告章节（REQUIRED_REPORT_SECTIONS）

- 问题概述
- 输入资料
- 故障现象
- 故障树分析
- 底事件评估
- 根因归因
- 验证计划
- 纠正措施
- 遗留风险
- 证据引用

## 资料覆盖类别（REQUIRED_COVERAGE，资料覆盖矩阵必须逐项检查）

- 问题描述
- 设计约束
- 试验记录或日志
- 总结报告
- 历史或复核记录

任一类别缺失时，必须同时写入报告“输入资料”与“遗留风险”章节。

## 报告关键短语（REQUIRED_REPORT_KEY_PHRASES，报告必须显式包含）

- 资料覆盖矩阵
- 证据台账摘要
- 待验证项
- 遗留风险

## 分析阶段标记（REQUIRED_STAGE_MARKERS，报告与 analysis_process.svg 必须包含）

- 证据提取
- 故障树构建
- 底事件评估
- 根因归因
- 纠正措施
- 文档生产

## 阶段职责说明（REQUIRED_RESPONSIBILITY_PHRASES，报告必须包含）

必须包含：
- 演绎建树阶段不依赖证据台账
- 证据检漏只做添加不做删除
- 文档阶段不修改分析数据

禁止出现反义声明（FORBIDDEN_RESPONSIBILITY_CLAIMS）：
- 演绎建树阶段依赖证据台账
- 证据检漏删除已有证据
- 文档阶段修改分析数据

## 证据缺失侧披露短语（EVIDENCE_SIDE_DISCLOSURE，资料覆盖矩阵与遗留风险必须原样披露）

| 缺失侧 | 披露短语 |
| --- | --- |
| document_evidence | 文档证据未提供 |
| code_evidence_package | 代码证据包未提供 |

## 静态扫描披露（Scanner Status 披露门）

- 扫描记录路径：`artifacts/evidence/scan_summary.json`（代码证据侧在跑时必须有记录；缺失记录不得视作干净扫描）。
- overall 为 `scanners_unavailable` 时，报告“遗留风险”必须原样包含披露短语：静态扫描器不可用。
