---
id: docs-upgrades-upstream-pr-candidates-registry-duplicate-evidence-hooks
kind: plan
status: current
owner: convergence maintainers
scope: 上游 PR 候选(04-M5,整改票 #63):bytedance/deer-flow harness extension registry 的 runtime evidence hooks 重复注册确定性语义;条件性 rider(上游今日无该注册缝),随下轮收敛轨与 P003/P011/P014/P032 并列 reassess,不作为本仓库长期门禁
last-verified: 2026-10-13
verified-against: 上游 deerflow/main(81fa17c15ab)与 v2.1.0(345f08be0)同名文件比对——resolve_runtime_evidence_hooks / runtime_evidence 均不存在于上游(该注册缝为 fork 本地新增,引入提交 ef2ed33dd,台账 PATCH-024);本地回归 tests/test_extension_registry.py、tests/test_extension_loader.py、tests/test_agentplatform_extension_boundary.py
---

# 上游 PR 候选:registry runtime evidence hooks 重复注册确定性语义(04-M5,票 63)

- 状态:候选(条件性 rider;待下轮收敛轨随 P003/P011/P014/P032 一并 reassess;
  提交流程见 `docs/offline-product-line-governance-plan.md` §修复轨/补丁卫生)。
- 目标上游仓库:`bytedance/deer-flow`(分支 `main`)。
- 来源:发现 04-M5(代码复审 2026-10-07);本地修复见票 #63(台账 PATCH-038,
  `UPSTREAM_PATCH_LEDGER.md` 巡检记录 2026-10-13 行)。
- 上游比对结论(与票面"上游同病"预判相反,已按票面要求先比对后定稿):
  `git show deerflow/main:backend/packages/harness/deerflow/extensions/__init__.py`
  与 `.../extensions/registry.py`(81fa17c15ab)、以及 v2.1.0 基线(345f08be0)
  均不含 `resolve_runtime_evidence_hooks` / `runtime_evidence`——runtime evidence
  注册缝为 fork 本地扩展面(引入提交 `ef2ed33dd`,台账 PATCH-024),上游今日没有
  可被此修复直接瞄准的同病代码。因此本候选定位为条件性 rider:若该注册缝
  (或等价的 receipt/evidence contribution 回调面,即台账 PATCH-005 移除条件所
  预期的 seam)未来以任何形式上提上游,单 provider 确定性重复语义必须随提案
  原生携带,不得让"静默取最后一个"的解析语义进入上游。下轮收敛 reassess 时
  若上游仍无该缝,本候选保持待命并复评,不视为可提交状态。

## PR 草稿(条件性:随 runtime evidence 注册缝上提时携带)

- **标题**: `fix(extensions): reject duplicate runtime-evidence-hook registration`
- **动机**: 注册面若接受多个 runtime evidence hooks 提供方,解析侧与全部消费方
  (任务委派、子代理执行器、run worker、工具收据中间件)把 hooks 当单一 provider
  使用;重复注册静默取最后一个会让先注册方的 evidence 投影(工具收据、子代理
  核验、检索引证)无声丢失。装载期显式拒绝(指认既有注册方)优于运行期静默覆盖。
- **修复**: registry 的 runtime evidence 注册方法在桶内已有注册时抛 `ValueError`,
  错误消息命名既有注册 source 与被拒 source;异常经 install() 传播,由装载器
  既有失败路径处置(位置回滚 + error diagnostic,`required: true` 时启动中止),
  不新增任何运行时路径。
- **测试**: registry 合同测试(跨源/同源重复注册拒绝、首个注册存活)+
  装载器测试(双 spec 挂载第二个显式失败并回滚、diagnostic 指认既有 source、
  required 中止启动、resolve 确定性返回首个 provider)。

## diff 草稿(参考实现)

上游无对应代码,无法按上游文件原样给 diff;以下为本仓 fork 内已落地的最小
参考实现(票 #63,commit 见台账),上提任何等价注册缝时按此语义携带:

```diff
--- a/backend/packages/harness/deerflow/extensions/registry.py
+++ b/backend/packages/harness/deerflow/extensions/registry.py
@@
     def runtime_evidence(self, hooks: RuntimeEvidenceHooks) -> None:
-        self._runtime_evidence_hooks.append((self._source(), hooks))
+        source = self._source()
+        if self._runtime_evidence_hooks:
+            # Single-provider seam, unlike the additive buckets above: every
+            # consumer resolves one hooks object, so a second registration
+            # must fail here — with the existing owner named — instead of
+            # being silently last-wins when the snapshot is resolved.
+            raise ValueError(
+                "runtime evidence hooks are a single-provider registration: "
+                f"'{self._runtime_evidence_hooks[0][0]}' already registered them, "
+                f"refusing the registration from '{source}'"
+            )
+        self._runtime_evidence_hooks.append((source, hooks))
```

配套解析侧语义澄清(`resolve_runtime_evidence_hooks` docstring 由
"the latest provider" 收敛为单 provider;解析行为不变):

```diff
--- a/backend/packages/harness/deerflow/extensions/__init__.py
+++ b/backend/packages/harness/deerflow/extensions/__init__.py
@@
 def resolve_runtime_evidence_hooks(extensions: LoadedExtensions | None) -> Any | None:
-    """Return the latest optional evidence hook provider for a run.
+    """Return the run's optional evidence hook provider.
+
+    Runtime evidence hooks are a single-provider registration (a duplicate
+    registration is refused by the registry), so a loaded set carries at most
+    one entry. ...
```

## 本地验证证据(2026-10-13,票 #63)

- 先红后绿:4 条新合同用例(`tests/test_extension_registry.py` 跨源/同源拒绝、
  `tests/test_extension_loader.py` 双 spec 显式失败/required 中止)实现前全失败
  (重复注册被静默接受:无 diagnostic、无中止、后者覆盖前者),实现后全绿;
- `tests/test_extension_registry.py` + `tests/test_extension_loader.py` +
  `tests/test_agentplatform_extension_boundary.py` 合计 75 passed;
- 台账 PATCH-024 验证命令复验 35 passed(无扩展/单 provider 行为不变)。
