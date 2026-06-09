# DMS Agent — NotebookLM 风格改版设计规范

## 概述

将 DMS Agent 前端从暗色工业风双栏布局，迁移到 NotebookLM 风格的浅色三栏布局。核心目标：更干净、更现代、更实用。

## 设计目标

1. 用户可感知 Agent 回答状态（进行中 / 已完成）
2. 代码修改 diff 直接可见、可下载、可对照
3. 右侧操作面板：一键生成报告、导出对话等
4. 整体 NotebookLM 浅色杂志风格
5. 右上角语言切换（简体中文 / EN）

---

## 1. 布局架构

三栏布局：

```
┌──────┬──────────────────────────────┬─────────────┐
│ 左栏 │        中间对话区             │   右栏      │
│ 72px │        flex: 1               │   260px     │
│      │                              │             │
│ 导航  │  ┌─ 顶部栏（标题+语言切换）─┐ │  Actions    │
│ 图标  │  │                          │ │             │
│      │  │  对话消息流               │ │  生成报告   │
│ 上传  │  │  - 用户气泡               │ │  导出对话   │
│ 对话  │  │  - Agent 气泡             │ │  下载文件   │
│ 文件  │  │    - 内嵌 Diff 卡片       │ │  对比指标   │
│      │  │    - Thinking 指示器       │ │  修改摘要   │
│      │  │                          │ │  保存 PDF   │
│      │  │  输入框                   │ │  分享链接   │
│      │  │                          │ │  清空会话   │
│      │  │                          │ │             │
│      │  │                          │ │  会话文件   │
└──────┴──────────────────────────────┴─────────────┘
```

**左栏（72px）**：极窄导航栏，仅图标按钮。包含：上传文件、会话列表、设置。

**中间（flex: 1）**：对话主区域。顶部标题栏 + 消息流 + 底部输入框。

**右栏（260px）**：操作面板 + 会话文件列表。固定宽度，可折叠。

---

## 2. 配色方案

NotebookLM 暖调米白色系 + 墨绿强调：

| 用途 | 色值 | 说明 |
|------|------|------|
| 页面背景 | `#faf8f5` | 暖米白 |
| 卡片/气泡背景 | `#ffffff` | 纯白 |
| 表面/侧栏 | `#f5f1eb` | 浅米色 |
| 边框 | `#e8e3db` | 暖灰边框 |
| 深色边框 | `#e0d8cc` | 强调边框 |
| 主文字 | `#3d392f` | 深棕黑 |
| 次要文字 | `#6b5f4f` | 中棕 |
| 辅助文字 | `#9c8b74` | 浅棕 |
| 强调色 | `#4a7c59` | 墨绿（替代原金色） |
| 强调色浅 | `#e8f0ea` | 墨绿淡底 |
| 红色（删除/错误） | `#b34a4a` | 暖红 |
| 绿色（添加/成功） | `#4a7c59` | 墨绿 |
| 链接色 | `#2c5f2d` | 深绿 |

## 3. 字体方案

| 用途 | 字体 | 说明 |
|------|------|------|
| 标题 | `'Source Serif 4', Georgia, serif` | 杂志感衬线 |
| 正文 | `'Inter', -apple-system, sans-serif` | 干净无衬线 |
| 代码 | `'JetBrains Mono', monospace` | 等宽代码 |

## 4. 组件详细设计

### 4.1 对话状态指示器

Agent 回答中显示三种状态：

- **Thinking**：灰色脉冲圆点 + "Thinking..." 文字，显示在 Agent 气泡底部。如果已知当前工具名，显示 "Analyzing retinaface.py..."
- **Done**：绿色对勾 + "Response complete"（2 秒后自动消失）
- **Error**：红色叉号 + 错误信息

WebSocket 消息流：`status: started` → 显示 Thinking → `done` → 显示 Done 标记。

### 4.2 内嵌 Diff 卡片

代码修改直接在 Agent 气泡中以卡片形式展示，不隐藏在工具调用下拉框中。

**卡片结构：**

```
┌─────────────────────────────────────────┐
│ retinaface.py                    +3 -2  │  ← 文件头
├──────────────────┬──────────────────────┤
│ - ResNet50(...)  │ + MobileNetV2(...)   │  ← Side-by-side
│ - backbone=resnet│ + backbone=mobilenet │
├──────────────────┴──────────────────────┤
│ [Unified Diff] [Download file] [Apply]  │  ← 操作栏
└─────────────────────────────────────────┘
```

**交互：**
- 默认 side-by-side 视图（左右对照）
- 点击 "Unified Diff" 切换为 +/- 行视图
- 点击 "Download file" 下载修改后的完整文件（通过 `/api/download/{session_id}/{filename}` 端点）
- Diff 卡片始终可见，不折叠

**后端支持：**
- 新增 `GET /api/download/{session_id}/{filename}` 端点，返回修改后的文件
- diff 信息通过新的 WebSocket 消息类型 `diff_card` 传递

### 4.3 右侧操作面板

8 个操作按钮，按功能分组：

**生成类：**
- **Generate Report** — 调用 `save_report` 工具，完成后触发下载
- **Save as PDF** — 将当前对话导出为 PDF（浏览器 `window.print()` 或服务端生成）
- **Export Chat** — 导出完整对话记录为 Markdown 文件

**分析类：**
- **Compare Metrics** — 如果有两份日志，生成优化前后对比表
- **Code Change Summary** — 汇总当前会话中所有代码修改

**工具类：**
- **Download Modified Files** — 打包下载所有修改过的文件（ZIP）
- **Share Link** — 生成可分享的会话快照（或复制当前状态）
- **Clear Session** — 清空当前会话

**额外显示：**
- 当前会话已上传文件列表
- 已修改文件列表（带下载图标）

### 4.4 语言切换

右上角语言切换按钮，下拉选择：
- 简体中文
- English

切换行为：
- 切换后刷新 UI 标签文本（按钮、提示、占位符）
- Agent 回复语言不变（Agent 始终用中文回复，因为系统提示词指定了中文）
- 语言偏好存储在 `localStorage`，刷新页面后保持

需要国际化的文本（约 20-30 条）：
- 按钮标签、占位符、提示信息、状态文字
- Agent 的欢迎消息

### 4.5 工具调用展示

保留当前的可折叠工具调用块，但精简样式适配浅色主题：
- 背景 `#f5f1eb`，边框 `#e0d8cc`
- 工具名用 JetBrains Mono
- 默认折叠（用户可点击展开查看详情）
- 与内嵌 Diff 卡片区分：工具调用块是"过程记录"，Diff 卡片是"结果展示"

---

## 5. 前端架构

单文件 `static/index.html` 保持，但内部结构重组：

```
static/index.html
  ├── <style>     — 完整 CSS（浅色主题变量 + 组件样式）
  ├── <body>
  │   ├── #app
  │   │   ├── #left-nav      — 72px 窄导航
  │   │   ├── #chat-area     — 对话主区域
  │   │   │   ├── #top-bar   — 标题 + 语言切换
  │   │   │   ├── #messages   — 消息流
  │   │   │   └── #input-area — 输入框
  │   │   └── #right-panel   — 260px 操作面板
  │   └── #toast              — 提示
  └── <script>  — WebSocket + UI 逻辑 + i18n
```

## 6. 后端新增端点

```python
# 下载修改后的文件
GET /api/session/{session_id}/download/{filename}

# 导出对话记录
GET /api/session/{session_id}/export?format=md|json

# 打包下载所有修改过的文件
GET /api/session/{session_id}/download-all
```

## 7. WebSocket 消息扩展

新增消息类型：

```jsonc
// diff 卡片（替代在 tool_end 中混合展示）
{
  "type": "diff_card",
  "filename": "retinaface.py",
  "old_snippet": "ResNet50(pretrained=True)\nbackbone = 'resnet'",
  "new_snippet": "MobileNetV2(pretrained=True)\nbackbone = 'mobilenet'",
  "changes": "+3 -2",
  "risk": "low",
  "download_url": "/api/session/abc123/download/retinaface.py"
}

// 操作结果（报告生成完成等）
{
  "type": "action_result",
  "action": "report_generated",
  "url": "/api/session/abc123/download/dms_report_20260609.md"
}
```

## 8. 实施顺序

1. CSS 变量 + 配色重写（暗色 → 浅色）
2. 三栏 HTML 结构调整
3. 对话状态指示器（Thinking/Done/Error）
4. 内嵌 Diff 卡片（HTML + CSS + JS 渲染）
5. 后端下载端点
6. 右侧操作面板（按钮 + 功能实现）
7. 语言切换（i18n 数据 + 切换逻辑）
8. 端到端验证

---

## 自检

- 无 TBD/placeholder 残留
- 配色/字体/布局/组件描述一致
- 范围聚焦：单次 UI 改版，不涉及 Agent 逻辑或工具修改
- 语言切换不影响 Agent 回复语言
