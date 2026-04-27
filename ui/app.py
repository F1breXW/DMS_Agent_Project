from __future__ import annotations

import sys
from pathlib import Path

import gradio as gr

# 运行脚本时把项目根目录加入 sys.path，确保可以导入 src.*
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.agent_core import DMSDigitalEngineer


agent = DMSDigitalEngineer()


THEME_CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Serif:wght@500;700&display=swap');

body {
    background: radial-gradient(1200px 600px at 10% -10%, #f7efe0 0%, #f1f7ff 50%, #f5f2ea 100%);
    font-family: 'IBM Plex Sans', system-ui, sans-serif;
}

.app-shell {
    max-width: 1200px;
    margin: 0 auto;
}

.hero-title {
    font-family: 'IBM Plex Serif', serif;
    font-size: 32px;
    font-weight: 700;
    letter-spacing: 0.2px;
    color: #1d2b36;
}

.hero-subtitle {
    color: #4b5a67;
    font-size: 14px;
    margin-top: 6px;
}

.panel {
    background: #ffffff;
    border: 1px solid #e6e7eb;
    border-radius: 16px;
    padding: 18px;
    box-shadow: 0 12px 30px rgba(23, 31, 38, 0.08);
}

.section-title {
    font-weight: 600;
    font-size: 14px;
    color: #314050;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 10px;
}

.status-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: #f2f5f8;
    border-radius: 999px;
    padding: 6px 12px;
    font-size: 12px;
    color: #425466;
}

.report-box {
    min-height: 420px;
}
"""


def on_start():
    return gr.update(interactive=False), "正在生成报告..."


def analyze(
    code_file: list[str] | None,
    log_file: list[str] | None,
    progress=gr.Progress(),
):
    """调用后端分析逻辑并返回报告，带进度提示。"""

    if not code_file or not log_file:
        return "请先上传源码文件和日志文件。", "等待输入", gr.update(interactive=True)

    status_holder = {"value": "正在生成报告..."}
    progress(0.01, desc="准备开始")

    progress_map = {
        "解析日志中...": 0.2,
        "解析源码中...": 0.4,
        "检索国标中...": 0.6,
        "调用大模型生成报告中...": 0.85,
        "报告生成完成": 1.0,
    }

    def update_status(message: str) -> None:
        status_holder["value"] = message
        progress(progress_map.get(message, 0.5), desc=message)

    report = agent.analyze_and_optimize(
        log_file=log_file,
        code_file=code_file,
        status_callback=update_status,
        save_report=True,
    )
    progress(1.0, desc="报告生成完成")
    return report, status_holder["value"], gr.update(interactive=True)


with gr.Blocks(title="DMS 智能评估系统", css=THEME_CSS) as demo:
    with gr.Column(elem_classes="app-shell"):
        gr.Markdown(
            "<div class='hero-title'>DMS 智能评估系统</div>"
            "<div class='hero-subtitle'>上传源码与日志，生成结构化评估报告。</div>"
        )

        with gr.Row():
            with gr.Column(scale=1):
                with gr.Column(elem_classes="panel"):
                    gr.Markdown("<div class='section-title'>输入</div>")
                    code_input = gr.File(
                        label="上传源码文件（可多选或拖拽文件夹）",
                        file_count="multiple",
                        file_types=None,
                        type="filepath",
                    )
                    log_input = gr.File(
                        label="上传日志文件（可多选或拖拽文件夹）",
                        file_count="multiple",
                        file_types=None,
                        type="filepath",
                    )
                    run_btn = gr.Button("开始分析", variant="primary")
                    gr.Markdown(
                        "<div class='status-chip'>状态提示会在右侧显示</div>"
                    )

            with gr.Column(scale=2):
                with gr.Column(elem_classes="panel"):
                    gr.Markdown("<div class='section-title'>评估报告</div>")
                    report_output = gr.Markdown(
                        value="报告将在此处显示。",
                        elem_classes="report-box",
                    )
                    status_output = gr.Markdown(
                        value="等待输入",
                        label="运行状态",
                    )

    run_btn.click(
        fn=on_start,
        outputs=[run_btn, status_output],
        show_progress="full",
    ).then(
        fn=analyze,
        inputs=[code_input, log_input],
        outputs=[report_output, status_output, run_btn],
        show_progress="full",
    )


demo.queue()

demo.launch(share=False)
