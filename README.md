# DMS Agent Project

DMS 智能评估系统：基于日志数据、源码解析与国标知识库检索，生成结构化评估报告。

## 功能概览
- 多日志/多源码文件解析
- 国标 PDF 知识库检索（RAG）
- 大模型生成评估报告（Markdown）
- Gradio Web 界面

## 快速开始
1) 安装依赖

```powershell
pip install -r requirements.txt
```

2) 放置 .env（由老师单独提供）

```text
DEEPSEEK_API_BASE=https://llmapi.tongji.edu.cn/v1
DEEPSEEK_API_KEY=你的学校密钥
DMS_LLM_MODEL=DeepSeek-R1
```

3) 启动 Web 界面

```powershell
python ui/app.py
```

浏览器访问：

```
http://127.0.0.1:7860
```

## 使用说明
- 上传源码文件（可多选或拖拽文件夹）
- 上传日志 CSV 文件（可多选或拖拽文件夹）
- 点击“开始分析”生成报告

报告会保存在 `reports/` 目录。

## 目录结构
```
DMS_Agent_Project/
├─ src/               # 后端核心逻辑
├─ ui/                # Gradio 前端
├─ data/              # 数据与知识库
│  ├─ standards/      # 国标 PDF
│  ├─ logs/           # 日志
│  └─ source_code/    # 源码
├─ reports/           # 生成的评估报告
└─ docs/              # 文档
```

## 常见问题
- RAG 索引
  - `python ui/app.py` 会自动加载/构建 `data/standards/faiss_index`

- 连接失败
  - 需要校园网或校园 VPN
  - 确认 .env 中 `DEEPSEEK_API_BASE` 和 `DEEPSEEK_API_KEY` 正确

## 更多文档
- 详细配置文档见 [docs/setup_guide.md](docs/setup_guide.md)
