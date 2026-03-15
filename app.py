from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from nanobot.cli.commands import run_agent, run_agent_safe
import uvicorn

app = FastAPI()
WORKSPACE = Path.home() / ".nanobot" / "workspace"

# 1. 主页：直接返回 HTML 网页前端
@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
    <meta charset=\"UTF-8\">
    <title>nanobot Web 前端</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .section { margin-bottom: 2em; }
        label { display: block; margin-top: 1em; }
        input, textarea, select { width: 100%; padding: 0.5em; margin-top: 0.2em; }
        button { margin-top: 1em; padding: 0.5em 2em; }
        .file-list { margin: 0.5em 0; }
        .reply { background: #f4f4f4; padding: 1em; border-radius: 5px; margin-top: 1em; }
    </style>
</head>
<body>
    <h1>nanobot Web 前端</h1>
    <div class=\"section\">
        <label>用户名：<input id=\"username\" type=\"text\" placeholder=\"请输入用户名\"></label>
    </div>
    <div class=\"section\">
        <label>上传文件：<input id=\"fileInput\" type=\"file\" multiple></label>
        <button onclick=\"uploadFiles()\">上传</button>
        <div id=\"uploadStatus\"></div>
    </div>
    <div class=\"section\">
        <button onclick=\"listFiles()\">刷新文件列表</button>
        <div class=\"file-list\" id=\"fileList\"></div>
    </div>
    <div class=\"section\">
        <label>选择要咨询的文件（可多选）：<select id=\"selectFiles\" multiple size=\"5\"></select></label>
        <label>你的问题：<textarea id=\"question\" rows=\"3\"></textarea></label>
        <button onclick=\"askAI()\">咨询AI</button>
        <div class=\"reply\" id=\"aiReply\"></div>
    </div>
    <script>
        const API = ".";
        function getUsername() {
            return document.getElementById('username').value.trim();
        }
        function uploadFiles() {
            const username = getUsername();
            if (!username) { alert('请先输入用户名'); return; }
            const files = document.getElementById('fileInput').files;
            if (!files.length) { alert('请选择文件'); return; }
            const formData = new FormData();
            formData.append('username', username);
            for (let i = 0; i < files.length; i++) {
                formData.append('files', files[i]);
            }
            fetch(API + '/upload', { method: 'POST', body: formData })
                .then(r => r.json())
                .then(data => {
                    document.getElementById('uploadStatus').innerText = '上传成功: ' + (data.files || []).join(', ');
                    listFiles();
                })
                .catch(() => { document.getElementById('uploadStatus').innerText = '上传失败'; });
        }
        function listFiles() {
            const username = getUsername();
            if (!username) { alert('请先输入用户名'); return; }
            fetch(API + '/list_files?username=' + encodeURIComponent(username))
                .then(r => r.json())
                .then(data => {
                    const files = data.files || [];
                    const fileList = document.getElementById('fileList');
                    fileList.innerText = files.length ? '已上传文件: ' + files.join(', ') : '暂无文件';
                    const select = document.getElementById('selectFiles');
                    select.innerHTML = '';
                    files.forEach(f => {
                        const opt = document.createElement('option');
                        opt.value = f; opt.text = f;
                        select.appendChild(opt);
                    });
                });
        }
        function askAI() {
            const username = getUsername();
            if (!username) { alert('请先输入用户名'); return; }
            const select = document.getElementById('selectFiles');
            const files = Array.from(select.selectedOptions).map(o => o.value);
            const question = document.getElementById('question').value.trim();
            if (!question) { alert('请输入你的问题'); return; }
            const formData = new FormData();
            formData.append('username', username);
            formData.append('message', question);
            formData.append('file_list', files.join(','));
            document.getElementById('aiReply').innerText = 'AI 正在思考...';
            fetch(API + '/ask', { method: 'POST', body: formData })
                .then(r => r.json())
                .then(data => {
                    document.getElementById('aiReply').innerText = data.reply || '无回复';
                })
                .catch(() => { document.getElementById('aiReply').innerText = '请求失败'; });
        }
    </script>
</body>
</html>"""

# 2. 上传文件接口

@app.post("/ask")
async def ask(
    username: str = Form(...),
    message: str = Form(...),
    file_list: str = Form("")  # 逗号分隔的文件名
):
    user_dir = WORKSPACE / "users" / username / "knowledges"
    context = ""
    # 获取所有已上传文件
    all_files = [f.name for f in user_dir.iterdir() if f.is_file()] if user_dir.exists() else []
    # 如果 file_list 为空且有已上传文件，则默认用所有文件
    selected_files = []
    if file_list.strip():
        selected_files = [f.strip() for f in file_list.split(",") if f.strip()]
    elif all_files:
        selected_files = all_files
    # 拼接选中文件内容
    if selected_files:
        for fname in selected_files:
            fpath = user_dir / fname
            if fpath.exists():
                context += f"\n\n# 文件：{fname}\n" + fpath.read_text(encoding="utf-8", errors="ignore")
    # 没有文件时就是普通AI问答
    full_message = (context + "\n\n" + message) if context else message
    result = run_agent_safe(message=full_message, username=username, logs=False)
    # return {"status": "ok", "reply": result if result else "AI已处理，请检查历史"}
    return result
# 4. 咨询AI接口
@app.post("/ask")
async def ask(
    username: str = Form(...),
    message: str = Form(...),
    file_list: str = Form("")  # 逗号分隔的文件名
):
    user_dir = WORKSPACE / "users" / username / "knowledges"
    context = ""
    if file_list:
        for fname in file_list.split(","):
            fpath = user_dir / fname.strip()
            if fpath.exists():
                context += f"\n\n# 文件：{fname}\n" + fpath.read_text(encoding="utf-8", errors="ignore")
    # 将文件内容拼接到 message 前面
    # full_message = (context + "\n\n" + message) if context else message
    full_message = message
    # 让 run_agent 返回 AI 回复内容（需在 commands.py/run_agent 支持返回）
    result = run_agent_safe(message=full_message, username=username, logs=True)
    # 假设 run_agent 返回 AI 回复字符串，否则需调整
    # return JSONResponse({"status": "ok", "reply": result if result else "AI已处理，请检查历史"})
    return result

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
