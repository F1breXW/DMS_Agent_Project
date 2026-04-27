# DMS 智能评估系统项目报告

本文档用于向组内同学介绍当前项目的整体架构、关键技术与运行流程。

## 1. 项目概述
DMS 智能评估系统面向“驾驶员状态监测（DMS）”场景，基于日志数据、源码解析与国标知识库检索，生成结构化评估报告（Markdown），用于诊断合规性、性能问题与优化建议。

项目已具备：
- 多文件日志/源码解析
- 国标 PDF 知识库检索（RAG）
- 大模型自动生成评估报告
- Gradio Web 界面

## 2. 架构总览

整体流程分为四层：
1) 数据输入层：上传日志 CSV 与源码文件/目录
2) 解析与指标层：提取平均 FPS/延迟等指标，读取源码文本
3) 知识检索层（RAG）：从国标 PDF 中检索相关条款（Top-3）
4) 大模型生成层：组合上下文，分段生成报告并合并

关键目录结构：
- src/：核心后端逻辑
- ui/：Web 界面
- data/：标准文档、日志、源码样例
- reports/：输出报告
- docs/：文档

## 3. 技术栈
- Python 3.10/3.11
- Gradio（Web UI）
- LangChain（LLM 统一接口）
- sentence-transformers + FAISS（文本向量化与检索）
- PyPDF（PDF 解析）
- pandas（日志处理）

## 4. 关键模块说明

### 4.1 配置与环境
- 文件：src/config.py
- 作用：读取 .env 环境变量，提供 LLM 配置与向量模型配置
- 典型配置：
  - DEEPSEEK_API_BASE / DEEPSEEK_API_KEY
  - DMS_LLM_MODEL / DMS_MAX_TOKENS
  - DMS_EMBEDDING_MODEL
  - HF_HUB_OFFLINE

### 4.2 日志与源码解析
- 文件：src/parsers.py
- LogParser：读取 CSV 日志，转为结构化对象，计算平均 FPS/延迟
- CodeParser：读取指定目录下 .py 文件为文本

### 4.3 知识库检索（RAG）
- 文件：src/rag_engine.py
- 标准文档来源：data/standards/ 下的 PDF
- 构建流程：
  1) 读取 PDF
  2) 文本切分
  3) Embedding 向量化
  4) FAISS 索引保存
- 检索流程：
  - query 由后端自动生成
  - similarity_search 返回 Top-3 条款

### 4.4 核心推理流程
- 文件：src/agent_core.py
- DMSDigitalEngineer：核心入口类
- 主要步骤：
  1) 解析日志 → 平均 FPS/延迟
  2) 读取源码（或摘要）
  3) 生成检索语句 → RAG 返回 Top-3 条款
  4) 组合上下文 → 分段生成报告 → 合并输出

### 4.5 Web 界面
- 文件：ui/app.py
- 功能：上传日志/源码、多文件支持、进度提示、报告展示
- 特性：
  - 运行中按钮禁用
  - 进度条与状态提示
  - 报告自动落盘（reports/）

## 5. 技术流程（详细）

### 5.1 启动阶段
1) Gradio 启动本地服务
2) 初始化 DMSDigitalEngineer
3) 初始化 StandardKnowledgeBase（加载或构建 FAISS 索引）

### 5.2 分析阶段（点击“开始分析”）
1) 日志解析
   - 读取多个 CSV
   - 统计平均 FPS/延迟
2) 源码解析
   - 读取多个 .py 文件
   - 或使用 docs/dms_prompt_snippet.txt 源码摘要
3) 生成检索语句
   - 根据延迟自动生成（例如“报警延迟 要求”）
4) RAG 检索
   - Top-3 条款返回
5) LLM 分段生成报告
   - 合规性评估
   - 问题清单
   - 优化建议
   - 关键代码修改建议
6) 合并并保存报告
   - reports/ 目录

## 6. 输入与输出

输入：
- 日志 CSV（支持多文件）
- 源码文件或目录（支持多文件）
- 国标 PDF（data/standards）

输出：
- 结构化评估报告（Markdown）
- 输出位置：reports/dms_report_YYYYMMDD_HHMMSS.md

## 7. 质量保障与限制

### 已保障
- 多文件解析能力
- 标准条款检索能力（RAG）
- 分段生成降低截断风险

### 当前限制
- 依赖学校模型接口（需校园网）
- 模型生成时间较长（DeepSeek-R1）
- 源码摘要压缩可能影响细节

## 8. 可扩展方向
- 增加更多标准/规范 PDF
- 扩充源码摘要覆盖范围
- 增加 Top-K 去重与合并策略
- 引入章节重试机制（网络波动时）
- 增加报告质量评估指标（如覆盖率/证据链）


