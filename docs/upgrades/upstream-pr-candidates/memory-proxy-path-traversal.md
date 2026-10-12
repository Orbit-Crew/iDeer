---
id: docs-upgrades-upstream-pr-candidates-memory-proxy-path-traversal
kind: plan
status: current
owner: convergence maintainers
scope: 上游 PR 候选(07-H1,整改票 #59):bytedance/deer-flow 的 frontend memory 代理 catch-all 路由路径穿越校验修复草稿,含可直接套用的 diff;随下轮收敛轨与 P003/P011/P014/P032 并列 reassess,不作为本仓库长期门禁
last-verified: 2026-10-11
verified-against: 上游 v2.1.0(345f08be0)同名文件比对;本地回归 tests/unit/app/api/memory 路由测试
---

# 上游 PR 候选:memory 代理路径穿越校验(07-H1,票 59)

- 状态:候选(待下轮收敛轨随 P003/P011/P014/P032 一并 reassess;提交流程见
  `docs/offline-product-line-governance-plan.md` §修复轨/补丁卫生)。
- 目标上游仓库:`bytedance/deer-flow`(分支 `main`)。
- 来源:发现 07-H1(`dev-log/code-review-2026-10-07/07-frontend-ui.md`,上游同病);
  本地修复见票 #59(commit 记录于 `UPSTREAM_PATCH_LEDGER.md` 巡检记录 2026-10-11 行)。
- 上游基线:`v2.1.0`(`345f08be0`);该文件在上游与本地唯一差异是
  `BACKEND_BASE_URL` 的环境变量回退链(本地多一层 `IDEER_INTERNAL_GATEWAY_BASE_URL`),
  以下 diff 草稿按上游文件原样给出,可直接套用于上游。

## PR 草稿

- **标题**: `fix(frontend): block path traversal in the memory catch-all proxy`
- **动机**: `frontend/src/app/api/memory/[...path]/route.ts` 把 Next 动态段
  (路由后已解码)直接 join 回 pathname 交给 `new URL(pathname, BACKEND_BASE_URL)`,
  URL 解析器会归一化 `..`/`%2e%2e`,`/api/memory` 前缀约束失效:
  `GET /api/memory/..%2F..%2Fv1%2Fadmin` 被代理到 `BACKEND_BASE_URL/v1/admin`,
  可触达后端任意路径(含 `/docs`、`/openapi.json` 等非 `/api` 挂载点)。
- **修复**: 对每个 path 段做白名单校验(拒绝空段、`.`、`..`、含 `/`、`\`、`%`、`?`、`#`
  的段),段重编码后拼接,并在 URL 构造后断言 `pathname` 仍以 `/api/memory/` 开头,
  否则返回 404,不发起转发。
- **测试**: 与本 PR 同路径补 `..` 穿越用例(多段、`..%2F..` 解码形态、`%2e%2e` 再编码段、
  段中嵌套、反斜杠、空段),断言 404 且未发起上游请求;合法多段路径代理行为不变。

## diff 草稿(对上游 `frontend/src/app/api/memory/[...path]/route.ts`)

```diff
--- a/frontend/src/app/api/memory/[...path]/route.ts
+++ b/frontend/src/app/api/memory/[...path]/route.ts
@@
 const BACKEND_BASE_URL =
   process.env.NEXT_PUBLIC_BACKEND_BASE_URL ?? "http://127.0.0.1:8001";
 
-function buildBackendUrl(pathname: string) {
-  return new URL(pathname, BACKEND_BASE_URL);
-}
+const MEMORY_PROXY_PREFIX = "/api/memory/";
+
+/**
+ * Only plain path segments may reach the backend. Next.js decodes dynamic
+ * segments before routing, so a raw join would let "." / ".." (or percent
+ * forms that normalize to them) escape the memory prefix inside `new URL`.
+ */
+function isSafeMemoryPathSegment(segment: string): boolean {
+  return (
+    segment.length > 0 &&
+    segment !== "." &&
+    segment !== ".." &&
+    !/[/\\%?#]/.test(segment)
+  );
+}
+
+function buildBackendUrl(pathSegments: string[]): URL | null {
+  if (!pathSegments.every(isSafeMemoryPathSegment)) {
+    return null;
+  }
+
+  const url = new URL(
+    `${MEMORY_PROXY_PREFIX}${pathSegments.map(encodeURIComponent).join("/")}`,
+    BACKEND_BASE_URL,
+  );
+
+  // Defense in depth: URL normalization must never escape the memory prefix.
+  if (!url.pathname.startsWith(MEMORY_PROXY_PREFIX)) {
+    return null;
+  }
+
+  return url;
+}
 
-async function proxyRequest(request: NextRequest, pathname: string) {
+async function proxyRequest(request: NextRequest, pathSegments: string[]) {
+  const backendUrl = buildBackendUrl(pathSegments);
+  if (!backendUrl) {
+    return new Response(null, { status: 404 });
+  }
+
   const headers = new Headers(request.headers);
   headers.delete("host");
   headers.delete("connection");
@@
   const hasBody = !["GET", "HEAD"].includes(request.method);
-  const response = await fetch(buildBackendUrl(pathname), {
+  const response = await fetch(backendUrl, {
@@
 export async function GET(
   request: NextRequest,
   { params }: { params: Promise<{ path: string[] }> },
 ) {
-  return proxyRequest(request, `/api/memory/${(await params).path.join("/")}`);
+  return proxyRequest(request, (await params).path);
 }
 
 export async function POST(
   request: NextRequest,
   { params }: { params: Promise<{ path: string[] }> },
 ) {
-  return proxyRequest(request, `/api/memory/${(await params).path.join("/")}`);
+  return proxyRequest(request, (await params).path);
 }
 
 export async function DELETE(
   request: NextRequest,
   { params }: { params: Promise<{ path: string[] }> },
 ) {
-  return proxyRequest(request, `/api/memory/${(await params).path.join("/")}`);
+  return proxyRequest(request, (await params).path);
 }
 
 export async function PATCH(
   request: NextRequest,
   { params }: { params: Promise<{ path: string[] }> },
 ) {
-  return proxyRequest(request, `/api/memory/${(await params).path.join("/")}`);
+  return proxyRequest(request, (await params).path);
 }
```

## 本地验证证据(2026-10-11,票 #59)

- 先红后绿:`tests/unit/app/api/memory/[...path]/route.test.ts` 新增 6 条穿越用例,
  实现前 6/6 失败(200 且 fetch 被调用),实现后全绿(15 用例);
  `tests/unit/app/api/memory/route.test.ts`(单路由版,无穿越面)6 用例保持全绿。
