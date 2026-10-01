# AI自动阅卷系统 — 技术架构设计

> 版本：V1.0  
> 对应PRD版本：V1.3

## 1. 技术选型

| 层级 | 选型 | 说明 |
|------|------|------|
| 前端框架 | Vue 3 + TypeScript | 组合式API，配合Element Plus组件库 |
| 前端构建 | Vite 5 | 快速开发与热更新 |
| 状态管理 | Pinia | 管理用户、考试、阅卷任务等状态 |
| 路由 | Vue Router 4 | 按角色动态路由 |
| UI组件库 | Element Plus | 表格、表单、上传、弹窗、分页等 |
| 图表 | ECharts / Vue-ECharts | 学情分析报表可视化 |
| 后端框架 | Python 3.11 + FastAPI | 高性能异步API，自动生成OpenAPI文档 |
| ORM/迁移 | SQLAlchemy 2.0 + Alembic | 数据库模型与版本迁移 |
| 数据校验 | Pydantic v2 | 请求/响应模型校验 |
| 数据库 | PostgreSQL 15 | 关系型主数据库 |
| 缓存/消息 | Redis 7 | 会话缓存、任务队列、进度通知 |
| 异步任务 | Celery + Redis Broker | PDF/图片导入、切割、AI评分等耗时任务 |
| 文件存储 | 本地文件系统（可切换MinIO/S3） | 答卷PDF、图片、题块图、原试卷PDF |
| 认证授权 | JWT + RBAC | 四种角色权限控制 |
| PDF处理 | PyMuPDF (fitz) | PDF转图、页面提取 |
| 图像处理 | OpenCV + Pillow | 纠斜、去噪、二值化、透视矫正、切割 |
| OCR识别 | EasyOCR / Tesseract | 手写文字、考号OCR识别 |
| OMR识别 | OpenCV自定义算法 | 填涂块识别 |
| AI大模型 | OpenAI兼容API + 本地模型适配器 | 支持云API与私有化部署（Ollama/vLLM） |
| 日志审计 | 数据库表记录 | 关键操作留痕 |

## 2. 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        前端层 (Vue 3 SPA)                    │
│  答题卡制作 │ 考试管理 │ 模板配置 │ 导入切割 │ 阅卷工作台 │ 学情报表 │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTPS/REST API + WebSocket(进度)
┌──────────────────────────────▼──────────────────────────────┐
│                      API网关层 (Nginx/traefik)               │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                      应用服务层 (FastAPI)                    │
│  认证模块 │ 考试模块 │ 模板模块 │ 导入模块 │ 评分模块 │ 报表模块 │
└──────────────────────────────┬──────────────────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        │                      │                      │
┌───────▼───────┐  ┌───────────▼───────────┐  ┌──────▼──────┐
│  Celery Worker │  │  AI/OCR/OMR Services  │  │ PostgreSQL  │
│  异步任务执行  │  │  本地模型/云API调用    │  │  主数据库   │
└───────────────┘  └───────────────────────┘  └─────────────┘
        │                      │                      │
        └──────────────────────┼──────────────────────┘
                               │
                        ┌──────▼──────┐
                        │    Redis    │
                        │ 缓存/队列   │
                        └─────────────┘
                               │
                        ┌──────▼──────┐
                        │ 文件存储    │
                        │ PDF/图片    │
                        └─────────────┘
```

## 3. 项目目录结构

```
/workspace/ai-auto-grader/
├── frontend/                          # Vue 3 前端
│   ├── src/
│   │   ├── api/                       # 接口请求封装
│   │   ├── assets/                    # 静态资源
│   │   ├── components/                # 公共组件
│   │   │   ├── AnswerCardDesigner/    # 答题卡设计器
│   │   │   ├── TemplateEditor/        # 模板框选编辑器
│   │   │   ├── ImageViewer/           # 答卷/题块预览
│   │   │   ├── ScorePanel/            # 打分面板
│   │   │   └── ExceptionPanel/        # 异常处理面板
│   │   ├── composables/               # 组合式函数
│   │   ├── layouts/                   # 布局组件
│   │   ├── router/                    # 路由配置
│   │   ├── stores/                    # Pinia状态管理
│   │   ├── utils/                     # 工具函数
│   │   ├── views/                     # 页面视图
│   │   │   ├── auth/                  # 登录
│   │   │   ├── dashboard/             # 首页看板
│   │   │   ├── exams/                 # 考试管理
│   │   │   ├── templates/             # 答题卡与模板
│   │   │   ├── imports/               # 答卷导入
│   │   │   ├── precheck/              # 预阅卷
│   │   │   ├── scoring/               # 阅卷工作台
│   │   │   ├── exceptions/            # 异常中心
│   │   │   ├── analytics/             # 学情分析
│   │   │   └── system/                # 系统设置
│   │   ├── App.vue
│   │   └── main.ts
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── backend/                           # FastAPI 后端
│   ├── alembic/                       # 数据库迁移
│   ├── app/
│   │   ├── api/
│   │   │   ├── v1/
│   │   │   │   ├── auth.py            # 认证
│   │   │   │   ├── users.py           # 用户角色
│   │   │   │   ├── exams.py           # 考试管理
│   │   │   │   ├── students.py        # 考生
│   │   │   │   ├── templates.py       # 模板
│   │   │   │   ├── imports.py         # 导入任务
│   │   │   │   ├── omr.py             # OMR判分
│   │   │   │   ├── scoring.py         # 阅卷评分
│   │   │   │   ├── precheck.py        # 预阅卷
│   │   │   │   ├── exceptions.py      # 异常中心
│   │   │   │   ├── analytics.py       # 学情分析
│   │   │   │   ├── exports.py         # 导出归档
│   │   │   │   └── system.py          # 系统设置
│   │   │   └── deps.py                # 依赖注入
│   │   ├── core/
│   │   │   ├── config.py              # 配置
│   │   │   ├── security.py            # JWT/密码
│   │   │   ├── exceptions.py          # 全局异常
│   │   │   └── permissions.py         # 权限校验
│   │   ├── models/                    # SQLAlchemy模型
│   │   ├── schemas/                   # Pydantic模型
│   │   ├── services/                  # 业务服务
│   │   │   ├── exam_service.py
│   │   │   ├── template_service.py
│   │   │   ├── import_service.py
│   │   │   ├── preprocess_service.py  # 图像预处理
│   │   │   ├── cut_service.py         # 题块切割
│   │   │   ├── omr_service.py         # OMR识别
│   │   │   ├── ai_service.py          # AI评分引擎
│   │   │   ├── scoring_service.py
│   │   │   ├── analytics_service.py
│   │   │   └── export_service.py
│   │   ├── tasks/                     # Celery异步任务
│   │   │   ├── import_tasks.py
│   │   │   ├── cut_tasks.py
│   │   │   ├── omr_tasks.py
│   │   │   ├── ai_tasks.py
│   │   │   └── analytics_tasks.py
│   │   ├── utils/                     # 工具
│   │   │   ├── pdf.py                 # PDF处理
│   │   │   ├── image.py               # 图像处理
│   │   │   ├── ocr.py                 # OCR
│   │   │   ├── file_storage.py        # 文件存储
│   │   │   └── websocket.py           # 进度推送
│   │   ├── main.py                    # FastAPI入口
│   │   └── init_db.py                 # 初始化数据
│   ├── requirements.txt
│   ├── Dockerfile
│   └── alembic.ini
├── docker-compose.yml                 # 一键启动
├── README.md
└── .env.example
```

## 4. 核心接口分组

| 分组 | 前缀 | 主要职责 |
|------|------|----------|
| 认证 | `/api/v1/auth` | 登录、登出、刷新Token、获取当前用户 |
| 用户权限 | `/api/v1/users` | 用户CRUD、角色分配 |
| 考试管理 | `/api/v1/exams` | 考试CRUD、原试卷上传、考生导入、权限分配 |
| 答题卡模板 | `/api/v1/templates` | 答题卡设计、模板框选、答案配置、AI规则 |
| 答卷导入 | `/api/v1/imports` | PDF/图片上传、导入任务、预处理、切割 |
| 异常中心 | `/api/v1/exceptions` | 异常列表、处理、日志 |
| 选择题判分 | `/api/v1/omr` | OMR识别、异常复核、统计 |
| 阅卷评分 | `/api/v1/scoring` | 任务分发、人工/AI评分、双评仲裁、批注 |
| 预阅卷 | `/api/v1/precheck` | 样卷上传、测试、清空 |
| 学情分析 | `/api/v1/analytics` | 多维报表、原试卷查看 |
| 导出归档 | `/api/v1/exports` | 成绩导出、答卷导出、归档 |
| 系统设置 | `/api/v1/system` | 大模型配置、水印、通知 |
| 审计日志 | `/api/v1/audit-logs` | 操作日志查询导出 |

## 5. AI大模型集成设计

### 5.1 抽象接口

所有AI调用统一通过 `AIServiceProvider` 抽象：

```python
class AIServiceProvider(ABC):
    @abstractmethod
    async def score_answer(
        self,
        image_base64: str,
        question_text: str,
        answer_text: str,        # OCR提取的手写文本
        standard_answer: str,
        scoring_points: list[str],
        max_score: float,
    ) -> AIScoreResult:
        ...
```

### 5.2 两种实现

1. **OpenAICompatibleProvider**：调用 OpenAI-compatible API（GPT-4、Claude、DeepSeek、Qwen 等）。
2. **LocalModelProvider**：调用本地部署模型（Ollama / vLLM / Xinference）。

### 5.3 AI评分结果

```python
class AIScoreResult(BaseModel):
    score: float
    comment: str
    confidence: float          # 0.0 ~ 1.0
    low_confidence: bool       # confidence < threshold
    reasoning: str | None      # 模型思考过程（可选）
```

### 5.4 安全约束

- 系统级置信度默认阈值可在系统设置中配置。
- 每场考试可单独覆盖阈值、Prompt、采分点。
- **低置信度结果禁止直接保存为有效分数**，自动进入人工复核队列。

## 6. 文件存储规范

```
/storage/
├── exams/{exam_id}/
│   ├── original_paper.pdf           # 原试卷PDF
│   ├── source_pdfs/                 # 导入的原始PDF
│   ├── source_images/               # 导入的原始图片
│   ├── preprocessed/                # 预处理后图像
│   ├── cut_blocks/                  # 切割后题块图
│   ├── precheck/                    # 预阅卷临时文件
│   └── exports/                     # 导出文件
├── templates/{template_id}/
│   └── template_config.json         # 模板配置
└── archives/{exam_id}/
    └── archive.zip                  # 归档包
```

## 7. 关键技术约束

1. **同步与异步分离**：文件上传、PDF转图、预处理、切割、AI评分、学情计算全部走Celery异步任务。
2. **进度推送**：导入、切割、AI评分等长任务通过WebSocket或轮询接口实时推送进度。
3. **异常不可绕过**：所有识别/AI低置信/切割失败统一进入异常中心；异常总数 > 0 时考试不可进入归档。
4. **预阅卷隔离**：预阅卷数据独立存储，测试完成后可一键清空，不混入正式数据。
5. **原试卷只读**：原试卷PDF仅作为附件用于查看、分析、归档，不参与识别与切割逻辑。
