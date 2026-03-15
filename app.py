from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
# 注意：如果 run_agent_safe 不是协程函数，需确保同步调用不阻塞 FastAPI
from nanobot.cli.commands import run_agent, run_agent_safe
import uvicorn
import traceback  # 新增：用于捕获异常信息

app = FastAPI()
WORKSPACE = Path.home() / ".nanobot" / "workspace"

# 确保工作目录存在（新增：避免目录不存在导致报错）
WORKSPACE.mkdir(parents=True, exist_ok=True)

# 1. 主页：修复 HTML 中的转义问题 + 优化前端错误处理
@app.get("/", response_class=HTMLResponse)
async def index():
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>nanobot Web 前端</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; }
        .section { margin-bottom: 2em; }
        label { display: block; margin-top: 1em; }
        input, textarea, select { width: 100%; padding: 0.5em; margin-top: 0.2em; }
        button { margin-top: 1em; padding: 0.5em 2em; }
        .file-list { margin: 0.5em 0; }
        .reply { background: #f4f4f4; padding: 1em; border-radius: 5px; margin-top: 1em; }
        .error { color: red; }
    </style>
</head>
<body>
    <h1>nanobot Web 前端</h1>
    <div class="section">
        <label>用户名：<input id="username" type="text" placeholder="请输入用户名"></label>
    </div>
    <div class="section">
        <label>上传文件：<input id="fileInput" type="file" multiple></label>
        <button onclick="uploadFiles()">上传</button>
        <div id="uploadStatus"></div>
    </div>
    <div class="section">
        <button onclick="listFiles()">刷新文件列表</button>
        <div class="file-list" id="fileList"></div>
    </div>
    <div class="section">
        <label>选择要咨询的文件（可多选）：<select id="selectFiles" multiple size="5"></select></label>
        <label>你的问题：<textarea id="question" rows="3"></textarea></label>
        <button onclick="askAI()">咨询AI</button>
        <div class="reply" id="aiReply"></div>
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
            document.getElementById('uploadStatus').innerText = '上传中...';
            fetch(API + '/upload', { method: 'POST', body: formData })
                .then(r => {
                    // 新增：先检查响应状态
                    if (!r.ok) throw new Error(`HTTP错误：${r.status}`);
                    return r.json();
                })
                .then(data => {
                    document.getElementById('uploadStatus').innerText = '上传成功: ' + (data.files || []).join(', ');
                    listFiles();
                })
                .catch(err => {
                    document.getElementById('uploadStatus').innerText = '上传失败：' + err.message;
                    console.error('上传错误：', err);
                });
        }
        function listFiles() {
            const username = getUsername();
            if (!username) { alert('请先输入用户名'); return; }
            fetch(API + '/list_files?username=' + encodeURIComponent(username))
                .then(r => {
                    if (!r.ok) throw new Error(`HTTP错误：${r.status}`);
                    return r.json();
                })
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
                })
                .catch(err => {
                    document.getElementById('fileList').innerText = '获取文件失败：' + err.message;
                    console.error('获取文件错误：', err);
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
            
            const aiReplyEl = document.getElementById('aiReply');
            aiReplyEl.innerText = 'AI 正在思考...';
            
            fetch(API + '/ask', { method: 'POST', body: formData })
                .then(r => {
                    // 关键修复：先检查响应状态，避免解析错误的响应
                    if (!r.ok) throw new Error(`服务器返回错误：${r.status}`);
                    return r.json();
                })
                .then(data => {
                    // 关键修复：明确取 reply 字段，兜底空字符串
                    aiReplyEl.innerText = data.reply || 'AI 暂无回复';
                    // 清除错误样式
                    aiReplyEl.classList.remove('error');
                })
                .catch(err => {
                    // 关键修复：显示具体错误信息，而非 [object Object]
                    aiReplyEl.innerText = '请求失败：' + err.message;
                    aiReplyEl.classList.add('error');
                    console.error('咨询AI错误：', err);
                });
        }
    </script>
</body>
</html>"""

# 2. 新增：上传文件接口（原代码缺失，导致上传功能报错）
@app.post("/upload")
async def upload_files(
    username: str = Form(...),
    files: list[UploadFile] = File(...)
):
    try:
        user_dir = WORKSPACE / "users" / username / "knowledges"
        user_dir.mkdir(parents=True, exist_ok=True)
        uploaded_files = []
        for file in files:
            file_path = user_dir / file.filename
            # 写入文件
            with open(file_path, "wb") as f:
                f.write(await file.read())
            uploaded_files.append(file.filename)
        return JSONResponse({"status": "ok", "files": uploaded_files})
    except Exception as e:
        # 捕获上传异常，返回友好提示
        return JSONResponse(
            {"status": "error", "message": f"上传失败：{str(e)}"},
            status_code=500
        )

# 3. 新增：列出文件接口（原代码缺失，导致刷新文件列表报错）
@app.get("/list_files")
async def list_files(username: str):
    try:
        user_dir = WORKSPACE / "users" / username / "knowledges"
        if not user_dir.exists():
            return JSONResponse({"files": []})
        # 列出所有文件（排除目录）
        files = [f.name for f in user_dir.iterdir() if f.is_file()]
        return JSONResponse({"files": files})
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"获取文件列表失败：{str(e)}"},
            status_code=500
        )

# 4. 修复：合并重复的 /ask 接口，增加异常处理
@app.post("/ask")
async def ask(
    username: str = Form(...),
    message: str = Form(...),
    file_list: str = Form("")  # 逗号分隔的文件名
):
    try:
        user_dir = WORKSPACE / "users" / username / "knowledges"
        context = ""
        
        # 处理选中的文件
        selected_files = []
        if file_list.strip():
            selected_files = [f.strip() for f in file_list.split(",") if f.strip()]
        
        # 拼接文件内容到上下文
        if selected_files and user_dir.exists():
            for fname in selected_files:
                fpath = user_dir / fname
                if fpath.exists() and fpath.is_file():
                    # 读取文件内容，处理编码异常
                    try:
                        context += f"\n\n# 文件：{fname}\n" + fpath.read_text(encoding="utf-8", errors="ignore")
                    except Exception as e:
                        context += f"\n\n# 文件：{fname}\n读取失败：{str(e)}"
        
        # 拼接完整问题
        full_message = context + "\n\n" + message if context else message
        
        # 调用 AI 函数，捕获可能的异常
        # 注意：如果 run_agent_safe 是同步阻塞函数，建议用 asyncio.to_thread 包装，避免阻塞事件循环
        # result = await asyncio.to_thread(run_agent_safe, message=full_message, username=username, logs=True)
        result = run_agent_safe(message=full_message, username=username, logs=True)
        
        # 确保返回的是字符串（关键：避免返回对象导致前端显示 [object Object]）
        reply = str(result) if result is not None else "AI 已处理，但暂无回复"
        return JSONResponse({"status": "ok", "reply": reply})
    
    except Exception as e:
        # 捕获所有异常，返回具体错误信息
        error_msg = f"处理请求失败：{str(e)}\n{traceback.format_exc()[:200]}"  # 限制异常信息长度
        return JSONResponse(
            {"status": "error", "reply": error_msg},
            status_code=500
        )

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)