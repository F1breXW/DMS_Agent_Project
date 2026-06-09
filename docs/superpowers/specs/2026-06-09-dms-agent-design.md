# DMS 数字工程师 Agent 设计文档

## 概述

将现有的固定流程（Pipeline）改造为对话式 AI Agent。Agent 能够自主探索 DMS 系统代码、解析性能日志、检索国标条款、搜索优化方案，并**在用户引导下**直接修改代码和参数。

核心变化：从 "上传→分析→出报告（一次性）" 变为 "对话式数字工程师（可持续交互、可修改代码）"。

## 架构

```
┌─────────────────────────────────────────┐
│           Chainlit UI (自定义CSS)         │
│  ┌──────────┐ ┌──────────┐ ┌─────────┐ │
│  │ 对话面板  │ │ 报告面板  │ │ 工具日志 │ │
│  └──────────┘ └──────────┘ └─────────┘ │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│       Agent Core (LangChain Agent)       │
│                                          │
│  System Prompt: DMS 领域知识 + 强制检查清单 │
│  + 严格修改规范 + DMS 指标判定标准          │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  9 个工具 (Tools)                   │  │
│  │  探索类: scan_codebase,             │  │
│  │    analyze_code_structure,          │  │
│  │    read_code_file,                  │  │
│  │    parse_performance_logs,          │  │
│  │    search_standards, search_web     │  │
│  │  行动类: modify_code,               │  │
│  │    compare_metrics, save_report     │  │
│  └────────────────────────────────────┘  │
│                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │ 现有模块  │ │ 新增模块  │ │ 外部依赖  │ │
│  │ parsers  │ │ code_    │ │ DuckDuckGo│ │
│  │ rag      │ │ analyzer │ │ Chainlit  │ │
│  └──────────┘ └──────────┘ └──────────┘ │
└──────────────────────────────────────────┘
```

## 工具清单

| # | 工具 | 类型 | 输入 | 输出 |
|---|------|------|------|------|
| 1 | scan_codebase | 探索 | 目录路径 | 文件树 + 大小 |
| 2 | analyze_code_structure | 探索 | 目录路径 | 类/函数/导入/常量摘要 |
| 3 | read_code_file | 探索 | 文件路径 + 行范围 | 代码内容 |
| 4 | parse_performance_logs | 探索 | CSV 文件 | 平均/峰值 FPS、延迟、CPU、内存 |
| 5 | search_standards | 探索 | 关键词 | 国标条款 Top-K |
| 6 | search_web | 探索 | 问题描述 | 搜索结果摘要 |
| 7 | modify_code | 行动 | 文件 + 旧代码 + 新代码 | 修改确认 |
| 8 | compare_metrics | 行动 | 旧日志 + 新日志 | 对比报告 |
| 9 | save_report | 行动 | 无 | 保存路径 |

## Agent 专用设计

### DMS 领域知识（内置于 System Prompt）

- DMS 标准架构认知：Camera → Face Detection → Feature Extraction → State Determination → Alert
- 核心指标体系：FPS(≥15合格,≥30优秀), 延迟(<200ms合格), 疲劳检测, 分心检测, 违规检测
- 国标关键要求：告警延迟≤行为持续时间的50%, 至少2种提示方式, 上电自检, 故障降级策略

### 强制检查清单（不可跳过）

- 实时性评估（FPS、端到端延迟）
- 模型选型评估（backbone是否适合嵌入式场景）
- 检测准确性评估（漏检/误检风险）
- 国标合规性评估（逐一比对RAG检索结果）
- 告警机制评估（是否至少2种提示方式）
- 鲁棒性评估（光照/姿态变化适应能力）
- 资源效率评估（CPU/内存占用）

### 修改安全约束

- 禁止：删除安全逻辑、降低告警灵敏度、移除国标要求功能
- 修改前：解释原因（关联指标或国标条款）、评估风险等级
- 修改后：列出受影响环节、建议验证指标

## UI 设计

- 框架：Chainlit
- 风格：工业精密度（深灰底 #1a1d23，暖金强调 #d4994a）
- 字体：IBM Plex Mono（标题），系统无衬线（正文）
- Agent 活动日志：控制台风格，非聊天气泡
- 辅助使用 huashu-design skill 生成自定义主题

## 实施阶段

1. Stage 1：新增 code_analyzer.py + tools.py
2. Stage 2：重写 agent_core.py（LangChain Agent）
3. Stage 3：新建 Chainlit UI
4. Stage 4：集成测试
