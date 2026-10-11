# 容器非 root 运行评估(08-M5,Issue #60)

状态:**本轮明确不改** — backend 镜像(`backend/Dockerfile`)继续以 root 运行;宿主 Docker socket 的
默认挂载已同步收敛(见 `docker/docker-compose.dood.yaml` opt-in overlay 与 Issue 08-H2 整改)。
本文记录证据、阻碍与后续改非 root 的前置条件,供后续独立变更直接引用。

## 现状证据

- `backend/Dockerfile` 三个 stage(builder/dev/runtime)均无 `USER` 指令,production gateway 与
  workflow-worker 以 root 运行 uvicorn。
- 监听端口均非特权:gateway 8001、frontend 3000(上游 node 镜像)、nginx 2026(独立 nginx 容器)。
  端口本身不构成非 root 障碍。
- runtime 镜像内 docker CLI 连接宿主 socket(DooD);`AioSandboxProvider` 本地模式经
  `local_backend.py` 以 subprocess 调 docker CLI 拉起沙箱容器,读 `/var/run/docker.sock`。
- 本次整改 smoke 复现:root 容器在宿主 bind mount 目录(`IDEER_HOME`)下创建 root 属主的
  `data/deerflow.db(-shm/-wal)`;既有部署的数据目录因此普遍为 root 属主。

## 不改的理由(阻碍清单)

1. **DooD socket 依赖(权重最高)**:`config.intranet.yaml` 默认
   `sandbox.use: deerflow.community.aio_sandbox:AioSandboxProvider`,内网交付默认路径依赖宿主
   socket。宿主 socket 属主为 `root:docker`,非 root 容器进程默认无权读写;可用做法是按宿主机
   docker GID 注入 `group_add` 或改用 socket 代理,两者都把部署机特定值引入内网离线 bundle,
   破坏「bundle 自包含、同包同行为」的确定性。
2. **bind mount 属主迁移**:`IDEER_HOME`(sqlite、threads、skills views)、
   `extensions_config.json`(rw)、officecli vendor 二进制(可执行位)等宿主路径现有属主为
   root/部署用户。切非 root 需要一次性 chown 迁移加部署脚本/runbook 配合,否则升级后立即不可写,
   属于破坏性部署变更。
3. **`/root` 固定挂载点**:prod base compose 把宿主 CLI 凭据只读挂到 `/root/.claude`、
   `/root/.codex`(08-M5 其余项,不在 #60 范围)。非 root 用户 HOME 不在 `/root`,必须先把挂载
   目标参数化并按 opt-in 原则移入 overlay,才能谈非 root。
4. **收益/成本比**:socket 默认移除后,默认部署面最大的「root 等价宿主控制」暴露已经关闭;非 root
   的剩余收益是纵深防御(应用层 RCE 后容器内提权受限),不阻塞任何当前功能。

## 可行性核查(未来改动的落点)

- `uv run --no-sync` 只读使用镜像内 `.venv`;clang-tidy/cppcheck、node/npx、lark-cli 均只读使用;
  healthcheck 为 python urllib。这些在非 root 下可行。
- 镜像需:创建专用用户(建议 uid/gid 10001)、`HOME` 参数化、构建期 `chown` 应用目录与 venv。
- 沙箱容器不受影响:ideer-sandbox 镜像自带「root 启动 → 建 gem 账户 → chown → 降权」启动路径,
  且 `local_backend.py` 以 `--cap-drop=ALL` + 兼容能力白名单 + `no-new-privileges` 运行沙箱;
  gateway 是否非 root 与该链路无关,只是 gateway 自身需要 socket 读取权。

## 后续改为非 root 的前置条件

1. CLI 凭据挂载移出 `/root` 并入 opt-in overlay(08-M5 剩余项)。
2. 部署脚本提供数据目录属主迁移与运行时 UID/GID 参数(或 ENTRYPOINT 启动期 chown 方案)。
3. DooD 场景 socket 访问策略定型(`group_add` 注入宿主 docker GID,或 socket 代理),并在内网
   bundle 指纹中固化。

三者齐备后作为独立变更实施,并跑完整容器 smoke(gateway/worker 健康检查、aio 沙箱拉起、
`check-intranet.sh`)。当前以「默认不挂 socket + overlay 显式 opt-in」收敛容器暴露面。
