"""Small M9 Gradio harness, not the final M11 website."""
import asyncio


def build_demo(interaction):
    import gradio as gr

    async def transcribe(path):
        result = await asyncio.to_thread(interaction.transcribe, path)
        return result["normalized_transcript"], result["raw_transcript"], result, "\n".join(result["warnings"])

    async def submit(text, transcript, speak):
        try:
            result = await interaction.answer(text, transcript, speak)
            timings = {key: value for key, value in result.items() if key.endswith("_ms")}
            return result["rag"]["answer"], result["audio_path"], result["rag"], timings, "\n".join(result["warnings"])
        except Exception as exc:
            return "", None, {}, {}, f"Không tạo được câu trả lời: {exc}"

    with gr.Blocks(title="M9 · Hỏi đáp bằng giọng nói") as demo:
        gr.Markdown("## M9 · Giọng nói tiếng Việt\nThu âm → nhận dạng → sửa câu hỏi → gửi. Có thể nhập văn bản trực tiếp.")
        audio = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Câu hỏi (tối đa 120 giây / 20 MB)")
        recognize = gr.Button("1. Nhận dạng giọng nói")
        original = gr.Textbox(label="Transcript gốc", interactive=False)
        question = gr.Textbox(label="2. Kiểm tra / sửa câu hỏi hoặc nhập trực tiếp", lines=3)
        speak = gr.Checkbox(value=False, label="Đọc câu trả lời (gửi nội dung trả lời tới dịch vụ Edge TTS trực tuyến)")
        send = gr.Button("3. Xác nhận và gửi", variant="primary")
        answer = gr.Textbox(label="Câu trả lời và nguồn", lines=12)
        playback = gr.Audio(label="Giọng đọc", type="filepath")
        details = gr.JSON(label="Evidence / citation / thời gian RAG")
        timings = gr.JSON(label="Thời gian xử lý (ms, không tính thời gian sửa transcript)")
        status = gr.Textbox(label="Trạng thái", interactive=False)
        state = gr.State({})
        recognize.click(transcribe, audio, [question, original, state, status], concurrency_id="m9", concurrency_limit=1)
        audio.change(lambda: ("", "", {}, "", None, {}, {}, ""), outputs=[question, original, state, answer, playback, details, timings, status], queue=False)
        send.click(submit, [question, state, speak], [answer, playback, details, timings, status], concurrency_id="m9", concurrency_limit=1)
    return demo.queue(default_concurrency_limit=1)
