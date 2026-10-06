"""Gradio workspace for the M9 voice and legal RAG pipeline."""
import asyncio
import html
import inspect


CSS = """
:root,html,body,.gradio-container {color-scheme:light !important;}
html,body {background:#f4f6f8 !important; color:#202833 !important;}
.gradio-container {max-width:1600px !important; padding:24px !important; color:#202833 !important;
 background:radial-gradient(ellipse at top,#fff3e8,transparent 60%),#f4f6f8 !important;
 --body-background-fill:#f4f6f8; --body-background-fill-dark:#f4f6f8;
 --background-fill-primary:#fff; --background-fill-primary-dark:#fff;
 --background-fill-secondary:#fafbfc; --background-fill-secondary-dark:#fafbfc;
 --block-background-fill:#fff; --block-background-fill-dark:#fff;
 --input-background-fill:#fff; --input-background-fill-dark:#fff;
 --body-text-color:#202833; --body-text-color-dark:#202833;
 --body-text-color-subdued:#697586; --body-text-color-subdued-dark:#697586;
 --border-color-primary:#e6e8ec; --border-color-primary-dark:#e6e8ec;}
#workspace {gap:18px; align-items:stretch;}
#sidebar,#main-panel,#sources-panel {background:#fff; border:1px solid #e6e8ec;
 border-radius:20px; padding:22px; box-shadow:0 8px 30px #18223008; color:#202833;}
#sidebar .block,#main-panel .block,#sources-panel .block,
#sidebar .form,#main-panel .form,#sources-panel .form {background:#fff !important; color:#202833 !important;}
.gradio-container input,.gradio-container textarea,.gradio-container select {
 background:#fff !important; color:#202833 !important; border-color:#d9dde5 !important;}
.gradio-container input::placeholder,.gradio-container textarea::placeholder {color:#98a2b3 !important;}
.gradio-container label,.gradio-container .label-wrap,.gradio-container .info {color:#475467 !important;}
.gradio-container button:not(#send) {background:#fff !important; color:#344054 !important; border-color:#d9dde5 !important;}
.gradio-container button:not(#send):hover {background:#fff7ed !important; border-color:#fdba74 !important;}
.gradio-container .accordion,.gradio-container details {background:#fff !important; color:#202833 !important;}
.brand {font-size:24px; font-weight:750; color:#202833; margin-bottom:12px;}
.brand span {color:#ea580c;} .muted {color:#697586; font-size:13px; line-height:1.7;}
.welcome {padding:18px 0;} .welcome h1 {font-size:28px; color:#202833; line-height:1.3;}
.welcome-grid {display:flex; flex-wrap:wrap; gap:10px; margin-top:20px;}
.welcome-card {flex:1; min-width:120px; padding:14px; border:1px solid #e6e8ec;
 border-radius:12px; background:#fff; text-align:left; color:#202833;}
.welcome-card b {display:block; font-size:13px; margin-bottom:6px; color:#c2410c;}
.welcome-card small {font-size:12px; color:#697586;}
.eyebrow {color:#b45309; font-size:11px; letter-spacing:1.5px; font-weight:700;}
#chat {min-height:260px; border:1px solid #e6e8ec;
 border-radius:14px; background:#fafbfc !important; color:#202833; line-height:1.8; overflow-wrap:anywhere;}
#chat .wrap,#chat .bubble-wrap,#chat .message-row {background:transparent !important;}
#chat .message {color:#202833 !important; border:1px solid #e6e8ec !important; box-shadow:none !important;}
#chat .message.bot,#chat .message-row.bot .message {background:#fff !important;}
#chat .message.user,#chat .message-row.user .message {background:#fff3e8 !important;}
#question textarea {font-size:15px; line-height:1.6;}
#send {background:#ea580c !important; color:white !important; border:0; border-radius:12px;}
#send:hover {background:#c2410c !important;}
.quick {text-align:left; justify-content:flex-start; border-radius:12px !important;}
.source-card {padding:15px; margin:12px 0; background:#fafbfc; border:1px solid #e6e8ec;
 border-radius:12px; overflow-wrap:anywhere; color:#202833; line-height:1.6;}
.source-card b {color:#c2410c; font-size:12px;} .source-card p {font-size:14px;}
.source-card small {color:#697586;}
.gradio-container .json-holder,.gradio-container .json-holder pre,
.gradio-container pre,.gradio-container code {background:#f8fafc !important; color:#344054 !important;}
.gradio-container .audio-container,.gradio-container .waveform-container,
.gradio-container [data-testid="waveform"] {background:#f8fafc !important; color:#202833 !important;}
.gradio-container footer {background:transparent !important; color:#697586 !important;}
@media(max-width:1100px) {#sidebar {min-width:100% !important;}}
@media(max-width:700px) {.gradio-container {padding:10px !important;}
 #sidebar,#main-panel,#sources-panel {min-width:0 !important; flex-basis:100% !important; padding:16px;}}
"""
EMPTY_SOURCES = '<p class="muted">Chưa có nguồn trích dẫn. Đặt câu hỏi để xem căn cứ pháp lý từ kết quả RAG.</p>'
WELCOME = """
<div class="welcome"><div class="eyebrow">TRA CỨU CÓ CĂN CỨ</div>
<h1>Xin chào, tôi là LandLaw AI</h1>
<p class="muted">Bạn muốn tìm hiểu quy định đất đai nào hôm nay?</p>
<div class="welcome-grid">
<div class="welcome-card"><b>⌕ Tra cứu quy định</b><small>Hỏi đáp từ văn bản được truy xuất</small></div>
<div class="welcome-card"><b>⇄ So sánh phiên bản</b><small>Đối chiếu 2013 và hiện hành</small></div>
<div class="welcome-card"><b>🎙 Hỏi bằng giọng nói</b><small>Nhận dạng, kiểm tra rồi gửi</small></div>
</div></div>
"""
QUESTIONS = ["Điều kiện để chuyển nhượng quyền sử dụng đất là gì?",
             "So sánh quyền của người sử dụng đất theo Luật Đất đai 2013 và hiện hành.",
             "Người sử dụng đất có những nghĩa vụ nào?"]


def render_sources(result):
    """Render actual citation metadata, never simulated sources or scores."""
    evidence = {}
    for source in (result or {}).get("sources") or []:
        key = source.get("chunk_id") or (source.get("metadata") or {}).get("chunk_id")
        if key:
            evidence[str(key)] = str(source.get("text") or source.get("content") or "")
    cards = []
    for index, citation in enumerate((result or {}).get("citations") or [], 1):
        number = html.escape(str(citation.get("number", index)))
        text = html.escape(str(citation.get("text", "Nguồn chưa có mô tả")))
        chunks = html.escape(", ".join(str(c) for c in citation.get("chunk_ids", [])))
        excerpts = "".join('<p>' + html.escape(evidence[str(c)]) + '</p>'
                           for c in citation.get("chunk_ids", []) if str(c) in evidence)
        cards.append(f'<article class="source-card"><b>NGUỒN [{number}]</b><p>{text}</p>'
                     f'<details><summary>Xem evidence</summary>{excerpts}<small>Chunk: {chunks}</small></details></article>')
    return "".join(cards) or EMPTY_SOURCES


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

    async def respond(text, transcript, speak, history):
        history = list(history or [])
        answer_text, audio_path, rag, times, warning = await submit(text, transcript, speak)
        if answer_text:
            history.extend([{"role": "user", "content": text},
                            {"role": "assistant", "content": answer_text}])
        return history, history, audio_path, rag, times, warning, render_sources(rag)

    # Colab may install either major version from requirements/audio.txt.
    theme = gr.themes.Soft(primary_hue="orange", neutral_hue="slate").set(
        body_background_fill="#f4f6f8",
        body_background_fill_dark="#f4f6f8",
        block_background_fill="#ffffff",
        block_background_fill_dark="#ffffff",
        input_background_fill="#ffffff",
        input_background_fill_dark="#ffffff",
        body_text_color="#202833",
        body_text_color_dark="#202833",
        body_text_color_subdued="#697586",
        body_text_color_subdued_dark="#697586",
        border_color_primary="#e6e8ec",
        border_color_primary_dark="#e6e8ec",
    )
    styling = {"css": CSS, "theme": theme}
    modern = "css" not in inspect.signature(gr.Blocks.__init__).parameters

    class StyledBlocks(gr.Blocks):
        def launch(self, *args, **kwargs):
            if modern:
                for key, value in styling.items():
                    kwargs.setdefault(key, value)
            return super().launch(*args, **kwargs)

    with StyledBlocks(title="LandLaw AI · Trợ lý pháp luật đất đai", **({} if modern else styling)) as demo:
        state = gr.State({})
        history = gr.State([])
        with gr.Row(elem_id="workspace"):
            with gr.Column(scale=2, min_width=240, elem_id="sidebar"):
                gr.HTML('<div class="brand">⚖ LandLaw <span>AI</span></div><p class="muted">Trợ lý pháp luật đất đai Việt Nam</p>')
                clear = gr.Button("＋ Câu hỏi mới")
                gr.Markdown("### Câu hỏi gợi ý")
                suggestions = [gr.Button(text, elem_classes=["quick"]) for text in QUESTIONS]
                with gr.Accordion("Hỏi bằng giọng nói", open=False):
                    audio = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Thu âm / tải lên (120 giây · 20 MB)")
                    recognize = gr.Button("Chuyển giọng nói thành văn bản")
                    original = gr.Textbox(label="Bản nhận dạng gốc", interactive=False)
                gr.Markdown("Mỗi câu hỏi được xử lý độc lập. Khi hỏi tiếp, hãy nêu đầy đủ bối cảnh.")
            with gr.Column(scale=6, min_width=320, elem_id="main-panel"):
                gr.Markdown("### Trợ lý pháp luật đất đai\nHỏi đáp và đối chiếu dựa trên nguồn được truy xuất.")
                chat_options = {"type": "messages"} if "type" in inspect.signature(gr.Chatbot.__init__).parameters else {}
                if "show_copy_button" in inspect.signature(gr.Chatbot.__init__).parameters:
                    chat_options["show_copy_button"] = True
                answer = gr.Chatbot(label="Hội thoại", height=440, elem_id="chat",
                                    placeholder=WELCOME,
                                    sanitize_html=True, **chat_options)
                question = gr.Textbox(label="Câu hỏi của bạn", placeholder="Nhập câu hỏi hoặc kiểm tra, sửa nội dung vừa nhận dạng…", lines=3, elem_id="question")
                speak = gr.Checkbox(value=False, label="Đọc câu trả lời — gửi nội dung tới dịch vụ Edge TTS trực tuyến")
                send = gr.Button("Gửi câu hỏi →", variant="primary", elem_id="send")
                status = gr.Textbox(label="Trạng thái / thông báo", interactive=False)
                playback = gr.Audio(label="Nghe câu trả lời", type="filepath")
            with gr.Column(scale=3, min_width=260, elem_id="sources-panel"):
                gr.Markdown("### Nguồn pháp lý\nCăn cứ trích dẫn của câu trả lời gần nhất.")
                sources = gr.HTML(EMPTY_SOURCES)
                with gr.Accordion("Chi tiết truy xuất", open=False):
                    details = gr.JSON(label="Evidence và citation")
                with gr.Accordion("Thời gian xử lý", open=False):
                    timings = gr.JSON(label="Đơn vị ms · không tính thời gian sửa câu hỏi")
        recognize.click(transcribe, audio, [question, original, state, status], concurrency_id="m9", concurrency_limit=1)
        audio.change(lambda: ("", {}, ""), outputs=[original, state, status], concurrency_id="m9", concurrency_limit=1)
        for button, text in zip(suggestions, QUESTIONS):
            button.click(lambda value=text: (value, "", {}), outputs=[question, original, state], concurrency_id="m9", concurrency_limit=1)
        for event in (send.click, question.submit):
            event(respond, [question, state, speak, history], [answer, history, playback, details, timings, status, sources], concurrency_id="m9", concurrency_limit=1)
        clear.click(lambda: ("", "", {}, [], None, {}, {}, "", None, EMPTY_SOURCES, []),
                    outputs=[question, original, state, answer, playback, details, timings, status, audio, sources, history],
                    concurrency_id="m9", concurrency_limit=1)
    return demo.queue(default_concurrency_limit=1)
