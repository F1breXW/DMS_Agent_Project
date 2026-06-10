# src/ 模块说明

## 概览

```
src/
├── agent_core.py      # AI Agent 核心
├── tools.py           # Agent 工具集
├── code_analyzer.py   # AST 代码结构分析
├── rag_engine.py      # 国标知识库 RAG 引擎
├── parsers.py         # 日志与源码解析器
├── config.py          # 配置与日志
└── models.py          # 数据模型
```

## 各模块功能

### agent_core.py — AI Agent 核心

- 定义 DMS 领域的 System Prompt（指标体系、国标要求、对话风格、工具使用原则）
- 基于 LangGraph StateGraph 构建 Agent 图（model → tools → after_tools → model 循环）
- 9 个 LangChain 工具绑定到 DeepSeek LLM
- 工具调用硬限制：最多 12 轮 / 20 次调用 / 禁止无意义重复调用
- 防御 DeepSeek XML 幻觉（`<function_calls>` / `<tool_calls>` 文本输出转真实 tool_calls 或噪声清洗）
- 提供 `run()`（同步）和 `stream_with_context()`（流式 + 会话上下文注入）两种执行方式

### tools.py — Agent 工具集

提供 9 个 `@tool` 装饰的 LangChain 工具函数：

| 类型 | 工具 | 功能 |
|------|------|------|
| 探索 | `scan_codebase` | 扫描目录，列出所有 .py 文件树和大小 |
| 探索 | `analyze_code_structure` | AST 解析，提取类/方法/函数/导入/常量骨架 |
| 探索 | `read_code_file` | 读取指定文件内容，支持行范围 |
| 探索 | `parse_performance_logs` | 解析日志 CSV，输出 FPS/延迟/CPU/内存统计 + DMS 判定 |
| 探索 | `search_standards` | 检索国标 GB/T FAISS 知识库 |
| 探索 | `search_web` | DuckDuckGo 搜索 DMS 技术资料 |
| 行动 | `modify_code` | 替换代码片段，生成 diff，安全检查后写入文件 |
| 行动 | `compare_metrics` | 对比优化前后两份日志，输出指标变化表 |
| 行动 | `save_report` | 保存 Markdown 评估报告到 `reports/` |

### code_analyzer.py — AST 代码结构分析

- 递归扫描目录，输出 .py 文件树和大小
- AST 解析 Python 源文件，提取类名、基类、方法、函数、导入依赖、常量
- 按行范围读取文件内容
- 归纳高频 DMS 相关模块依赖（torch、cv2、numpy 等）

### rag_engine.py — 国标知识库 RAG 引擎

- 解析国标 PDF（如 `疲劳驾驶检测国标.pdf`）
- 文本切分（500 字符块 + 50 字符重叠）
- 用 sentence-transformers 向量化，构建 FAISS 向量索引
- 支持优先加载本地缓存索引，首次无索引时自动构建
- 离线优先：检测本地 HuggingFace 模型快照，避免重复下载
- 提供 `search_standard(query, k)` Top-K 语义检索接口

### parsers.py — 日志与源码解析器

- `LogParser`：读取 CSV 日志目录，解析为结构化 `DMSLogData` 对象，计算平均 FPS 和延迟
- `CodeParser`：读取源码目录下所有 .py 文件内容

### config.py — 配置与日志

- 加载 `.env` 环境变量（API 地址、密钥、模型参数）
- 导出全局常量：`DEEPSEEK_API_BASE`、`DEEPSEEK_API_KEY`、`DMS_LLM_MODEL`、温度/采样/最大 token 等
- `get_logger()` 创建统一的日志记录器（DEBUG 级别、带时间戳格式）
- `get_config()` 打包关键配置为字典

### models.py — 数据模型

- `DMSLogData`：单条日志记录（时间戳、FPS、延迟、CPU、内存）
- `EvaluationReport`：评估报告（合规得分、问题列表、优化建议、总结、评估时间）
