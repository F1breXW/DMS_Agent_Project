# DMS Agent Project 运行配置文档

本文档用于帮助小组成员在本地完成环境配置并运行项目。假设你已经拿到单独发放的 .env 文件。

## 1. 环境要求
- Windows 10/11（其他系统也可，但以下命令以 Windows PowerShell 为例）
- Python 3.10 或 3.11
- 能访问学校模型接口的网络环境（校园网或校园 VPN）

## 2. 获取项目代码
1) 克隆仓库到本地
2) 进入项目根目录（与 src、data、ui 同级）

## 3. 创建并激活虚拟环境
在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

## 4. 安装依赖
在已激活的虚拟环境中执行：

```powershell
pip install -r requirements.txt
```

## 5. 放置 .env 文件
将我单独提供的 .env 文件放在项目根目录。至少应包含以下配置：

```
DEEPSEEK_API_BASE=https://llmapi.tongji.edu.cn/v1
DEEPSEEK_API_KEY=你的学校密钥
DMS_LLM_MODEL=DeepSeek-R1
```

可选配置（建议保留默认即可）：
```
DMS_TEMPERATURE=0.2
DMS_TOP_P=0.8
DMS_MAX_TOKENS=4096
DMS_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
HF_HUB_OFFLINE=1
```

说明：
- HF_HUB_OFFLINE=1 表示优先离线使用本地模型；如果本地不存在，程序会允许联网下载一次。
- DMS_LLM_MODEL 可改为 DeepSeek-R1 / DeepSeek-R1-Distill-Llama-70B / DeepSeek-R1-Distill-Qwen-32B。

## 6. 知识库准备（RAG）
知识库位于 data/standards。默认已存在索引，如果需要重建可执行：

```powershell
python src/rag_engine.py
```

若首次运行需要下载嵌入模型，请确保网络可访问 Hugging Face（或已配置镜像）。

可选镜像设置（写入 .env）：
```
HF_ENDPOINT=https://hf-mirror.com
```

## 7. 启动 Web 界面
在项目根目录执行：

```powershell
python ui/app.py
```

浏览器访问：

```
http://127.0.0.1:7860
```

## 8. 使用方法
1) 上传源码文件（可多选或拖拽文件夹）
2) 上传日志 CSV 文件（可多选或拖拽文件夹）
3) 点击“开始分析”

报告将保存到项目根目录的 reports 文件夹中。

## 9. 常见问题
- 连接错误（APIConnectionError）：
  - 确认已连接校园网或校园 VPN
  - 确认 .env 中 DEEPSEEK_API_BASE 与 DEEPSEEK_API_KEY 正确

- Hugging Face 联网校验失败：
  - 确认 .env 中 HF_HUB_OFFLINE=1
  - 如果本地未下载模型，需要临时允许联网或配置 HF_ENDPOINT 镜像

- 报告生成较慢：
  - DeepSeek-R1 模型体量大，生成时间长属正常现象
