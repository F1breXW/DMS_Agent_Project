# DMS Agent — 驾驶员监测系统 AI 评估助手

基于 LangGraph + FastAPI 构建的 DMS（Driver Monitoring System）智能评估 Agent。支持对话式交互，可解析性能日志、分析源码结构、检索国标条款、修改代码并生成结构化评估报告。

## 功能概览

- **对话式 Agent**：像同事一样协作，按需深入，不机械填清单
- **9 个专用工具**：源码扫描、AST 结构分析、日志解析、国标 RAG 检索、代码修改、指标对比、报告生成、Web 搜索
- **代码修改与 Diff**：Agent 可直接修改 DMS 源码，修改前后对比卡片内嵌在对话中，支持一键下载
- **多会话管理**：前端支持创建/切换/删除多个对话会话，文件与对话历史独立持久化
- **NotebookLM 风格 UI**：三栏布局，浅色暖调主题，Thinking/Done 状态指示

## 架构

```
用户浏览器                    服务端
┌──────────────────┐        ┌─────────────────────────┐
│ static/index.html │◄─WS──►│ server.py (FastAPI)     │
│ 三栏 SPA          │        │  ├─ SessionManager      │
│  ├─ 左栏导航      │  HTTP  │  ├─ REST /api/*         │
│  ├─ 中间对话区    │◄─────►│  └─ WS  /ws/{id}       │
│  └─ 右栏操作面板  │        │          │               │
└──────────────────┘        │  src/agent_core.py      │
                            │  ├─ LangGraph StateGraph │
                            │  ├─ DeepSeek LLM         │
                            │  └─ 9 LangChain Tools    │
                            │          │               │
                            │  src/tools.py            │
                            │  src/code_analyzer.py    │
                            │  src/rag_engine.py       │
                            │  src/parsers.py          │
                            └─────────────────────────┘
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 .env

在项目根目录创建 `.env`：

```env
DEEPSEEK_API_BASE=https://llmapi.tongji.edu.cn/v1
DEEPSEEK_API_KEY=你的密钥
DMS_LLM_MODEL=DeepSeek-R1
DMS_TEMPERATURE=0.2
DMS_MAX_TOKENS=4096
```

### 3. 启动服务

```bash
uvicorn server:app --reload --port 8000
```

浏览器访问 `http://127.0.0.1:8000`。

> 首次启动时 Agent 在后台初始化（约 13s），状态栏会显示加载进度。

## 使用说明

1. **上传文件**：点击左栏上传按钮，上传 DMS 源码（.py）或性能日志（.csv）
2. **开始对话**：在输入框提问，Agent 会按需调用工具获取数据后回答
3. **代码修改**：Agent 修改代码后，对话中会显示 Diff 卡片，可下载修改后的文件
4. **生成报告**：点击右栏「生成评估报告」，Agent 会基于对话内容生成 Markdown 报告
5. **导出对话**：点击「导出对话」下载 Markdown 格式的完整对话记录
6. **多会话**：右栏 Sessions 区域可新建、切换、删除会话

### 对话深度

- 简单问题（"FPS 最低多少合格"）→ Agent 直接回答
- 分析请求（"帮我看看这个系统"）→ Agent 调用工具获取数据后给出针对性判断
- 完整评估（"做一个全面审查"）→ Agent 系统覆盖所有维度

## 目录结构

```
DMS_Agent_Project/
├── server.py              # FastAPI 服务端（REST + WebSocket）
├── static/
│   └── index.html         # NotebookLM 风格前端 SPA
├── src/
│   ├── agent_core.py      # LangGraph Agent 核心（StateGraph + 系统提示词）
│   ├── tools.py           # 9 个 LangChain 工具
│   ├── code_analyzer.py   # AST 代码结构分析器
│   ├── rag_engine.py      # FAISS 国标知识库 RAG 引擎
│   ├── parsers.py         # 日志 CSV 解析器 + 源码读取器
│   ├── config.py          # 配置加载 + 日志工具
│   └── models.py          # Pydantic 数据模型
├── data/
│   ├── standards/         # 国标 PDF + FAISS 索引
│   ├── logs/              # 示例日志 CSV
│   └── source_code/       # DMS 参考源码（约 30+ 文件）
├── reports/               # 生成的评估报告
├── uploads/               # 用户上传文件（按会话隔离）
├── docs/                  # 项目文档
├── requirements.txt
└── .env                   # 环境配置（不入库）
```

## API 端点

### REST

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/session` | 创建会话，返回 `session_id` |
| `POST` | `/api/upload` | 上传文件（multipart: `session_id` + `file`） |
| `GET` | `/api/session/{id}/status` | 查询 Agent 初始化状态 + 文件列表 |
| `GET` | `/api/session/{id}/files` | 列出已上传文件 |
| `GET` | `/api/session/{id}/modified-files` | 列出已修改文件 |
| `GET` | `/api/session/{id}/download/{filename}` | 下载指定文件 |
| `GET` | `/api/session/{id}/download-all` | 打包下载所有文件（ZIP） |
| `GET` | `/api/session/{id}/export?format=md` | 导出对话记录（md / json） |
| `DELETE` | `/api/session/{id}` | 删除会话并清理文件 |

### WebSocket

| 路径 | 说明 |
|------|------|
| `/ws/{session_id}` | 对话流通道 |

**消息类型（Server → Client）**：`token`（流式文本）、`tool_start` / `tool_end`（工具调用）、`diff_card`（代码修改卡片）、`action_result`（操作结果）、`content_replace`（后处理）、`done`（完成）、`error`（错误）

## Agent 工具

| 工具 | 类型 | 说明 |
|------|------|------|
| `scan_codebase` | 探索 | 扫描目录，列出所有 .py 文件与大小 |
| `analyze_code_structure` | 探索 | AST 解析，提取类/函数/导入/常量 |
| `read_code_file` | 探索 | 读取指定文件内容（支持行范围） |
| `parse_performance_logs` | 探索 | 解析日志 CSV，输出 FPS/延迟/CPU/内存统计与判定 |
| `search_standards` | 探索 | 检索国标 GB/T 知识库（RAG） |
| `search_web` | 探索 | 搜索 DMS 相关技术资料 |
| `modify_code` | 行动 | 替换代码片段，生成 diff，写入文件 |
| `compare_metrics` | 行动 | 对比优化前后两份日志的指标变化 |
| `save_report` | 行动 | 保存 Markdown 评估报告到 `reports/` |

## 配置参考

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `DEEPSEEK_API_BASE` | `https://api.deepseek.com` | API 地址 |
| `DEEPSEEK_API_KEY` | — | API 密钥（必填） |
| `DMS_LLM_MODEL` | `DeepSeek-R1` | 模型名称 |
| `DMS_TEMPERATURE` | `0.2` | 生成温度 |
| `DMS_TOP_P` | `0.8` | 核采样 |
| `DMS_MAX_TOKENS` | `4096` | 最大输出 token |

## 常见问题

**Q: 启动后页面显示 "Agent initializing"？**
A: Agent 在后台线程初始化（模型加载约 13s），等待状态变为 ready 后即可使用。

**Q: RAG 检索无结果？**
A: 确认 `data/standards/` 下有国标 PDF 文件，首次启动会自动构建 FAISS 索引。

**Q: 代码修改后想恢复？**
A: 当前版本不内置版本回退，建议在 Git 管理下使用本工具，修改前先 commit。
