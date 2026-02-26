# 工程管理系统 (EMS)

面向工程现场的轻量管理系统，提供工程切换、施工日志、进度计划、材料与库存、机械台账、现场照片等能力。

## 功能概览

- 账号登录与密码修改
- 工程管理（新建 / 进入 / 删除）
- 施工日志（文本 + 图片）
- 进度计划可视化管理
- 材料管理、入库/出库草稿与确认入账
- 库存台账与导出
- 机械台账与导出
- 现场照片筛选、预览、删除

## 技术栈

- Frontend: Vue 3 + Vite + Element Plus + Pinia
- Backend: FastAPI + SQLAlchemy
- DB: SQLite
- Deploy: Docker Compose

## 快速启动（Docker）

```bash
cp deploy/.env.example deploy/.env
docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d --build
```

- 访问地址：`http://<服务器IP>:28888`
- 首次启动无默认账号：请在登录页完成管理员初始化（账号至少 3 位，密码至少 8 位且包含字母和数字）

## 质量门禁（本地）

提交前建议至少通过以下检查（与 CI 保持一致）：

```bash
# 后端测试
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest tests -q

# 前端构建
cd ../frontend
npm ci
npm run build
```

若系统 `python` 命令不可用，可使用仓库内置 Python（Windows）：

```bash
cd backend
..\tools\python312\python.exe -m pip install -r requirements-dev.txt
..\tools\python312\python.exe -m pytest tests -q
```

推荐在 Windows 本地直接执行一键冒烟：

```bash
scripts\smoke.bat
```

若数据库已初始化（已有管理员），执行 `smoke.bat` 前请先设置 E2E 账号环境变量：

```bash
set E2E_USERNAME=你的管理员账号
set E2E_PASSWORD=你的管理员密码
scripts\smoke.bat
```

也可单独执行端到端冒烟脚本：

```bash
tools\python312\python.exe scripts\e2e_smoke.py --username 你的管理员账号 --password 你的管理员密码
```

### 冒烟常见问题

- `401 Unauthorized`：通常是 `E2E_USERNAME / E2E_PASSWORD` 错误，或对应账号已被修改/禁用。
- `system already initialized; pass --username and --password`：数据库已初始化，需显式传管理员账号密码。
- `SECRET_KEY` 未设置告警：开发环境可忽略；生产环境请在环境变量中设置固定强密钥。
- `python / npm not recognized`：请优先使用仓库内置运行时（`tools\python312\python.exe`、`tools\node22\npm.cmd`）。
- 前端构建失败：先在 `frontend/` 执行 `tools\node22\npm.cmd install` 再重试。

发版前可执行完整冒烟（全量校验 + 全量后端测试）：

```bash
scripts\smoke-full.bat
```

## 常用运维命令

```bash
# 状态
docker compose --env-file deploy/.env -f deploy/docker-compose.yml ps

# 日志
docker compose --env-file deploy/.env -f deploy/docker-compose.yml logs -f

# 停止
docker compose --env-file deploy/.env -f deploy/docker-compose.yml down

# 重置数据（危险）
docker compose --env-file deploy/.env -f deploy/docker-compose.yml down -v --remove-orphans
docker compose --env-file deploy/.env -f deploy/docker-compose.yml up -d --build
```

## 仓库结构

- `frontend/` 前端项目
- `backend/` 后端项目
- `deploy/` 部署配置

## 相关说明

- 前端复用规范：`frontend/src/component-reuse-guidelines.md`
