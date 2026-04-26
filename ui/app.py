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


def analyze(
    code_file: list[str] | None,
    log_file: list[str] | None,
    progress=gr.Progress(),
):
    """调用后端分析逻辑并返回报告，带进度提示。"""

    if not code_file or not log_file:
        return "请先上传源码文件和日志文件。", "等待输入"

    status_holder = {"value": "准备开始"}
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
    return report, status_holder["value"]


with gr.Blocks(title="DMS 智能评估系统") as demo:
    gr.Markdown("# DMS 智能评估系统\n上传源码与日志后开始分析。")

    with gr.Row():
        with gr.Column():
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

        with gr.Column():
            report_output = gr.Markdown(label="评估报告")
            status_output = gr.Markdown(label="运行状态")

    run_btn.click(
        fn=analyze,
        inputs=[code_input, log_input],
        outputs=[report_output, status_output],
        show_progress="full",
    )


demo.queue()

demo.launch(share=False)
