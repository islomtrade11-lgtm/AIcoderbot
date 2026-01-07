import os
import asyncio
import aiosqlite
import httpx

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

# ======================= CONFIG =======================
BOT_TOKEN = os.getenv("BOT_TOKEN")                 # BotFather
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
APP_URL = os.getenv("APP_URL")                     # https://xxx.up.railway.app

MODEL = "deepseek/deepseek-coder"
DB_PATH = "db.sqlite"
# =====================================================

# ======================= FASTAPI ======================
app = FastAPI()

SYSTEM_PROMPT = """
You are an elite senior Python developer.
Generate clean, production-ready Python 3.11 code.
Return ONLY full working code.
"""

PROMPT_ENHANCER = """
Rewrite the user's request into a precise software engineering task.
Add missing technical details.
Focus on implementation.
"""

# ======================= DATABASE =====================

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            task TEXT,
            code TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """)
        await db.commit()

# ======================= LLM ==========================

async def call_llm(messages):
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL,
                "messages": messages,
                "temperature": 0.15,
                "max_tokens": 3000
            }
        )
        return r.json()["choices"][0]["message"]["content"]

# ======================= API MODELS ===================

class Generate(BaseModel):
    user_id: int
    text: str

class SaveProject(BaseModel):
    user_id: int
    title: str
    task: str
    code: str

class DeleteProject(BaseModel):
    user_id: int
    project_id: int

# ======================= API ==========================

@app.post("/generate")
async def generate(req: Generate):
    enhanced = await call_llm([
        {"role": "system", "content": PROMPT_ENHANCER},
        {"role": "user", "content": req.text}
    ])

    code = await call_llm([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": enhanced}
    ])
    return {"code": code}

@app.post("/projects/save")
async def save_project(p: SaveProject):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO projects (user_id, title, task, code) VALUES (?, ?, ?, ?)",
            (p.user_id, p.title, p.task, p.code)
        )
        await db.commit()
    return {"status": "ok"}

@app.get("/projects/list/{user_id}")
async def list_projects(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, title FROM projects WHERE user_id=? ORDER BY created_at DESC",
            (user_id,)
        )
        rows = await cur.fetchall()
    return [{"id": r[0], "title": r[1]} for r in rows]

@app.get("/projects/{project_id}")
async def get_project(project_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT title, task, code FROM projects WHERE id=?",
            (project_id,)
        )
        r = await cur.fetchone()
    return {"title": r[0], "task": r[1], "code": r[2]}

@app.post("/projects/delete")
async def delete_project(p: DeleteProject):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM projects WHERE id=? AND user_id=?",
            (p.project_id, p.user_id)
        )
        await db.commit()
    return {"status": "deleted"}

# ======================= MINI APP =====================

@app.get("/", response_class=HTMLResponse)
async def mini_app():
    return """
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport"
content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">

<title>AI Coder</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>

<style>
:root{
 --bg:#0b0f14;
 --card:#111827;
 --border:#1f2937;
 --text:#e5e7eb;
 --muted:#9ca3af;
 --accent:#6366f1;
 --accent2:#22c55e;
 --danger:#ef4444;
}

*{box-sizing:border-box}

html,body{
 margin:0;
 height:100%;
 background:var(--bg);
 color:var(--text);
 font-family:Inter,system-ui,sans-serif;
}

.app{
 padding:14px;
 display:flex;
 flex-direction:column;
 gap:14px;
}

/* ---- cards ---- */
.card{
 background:linear-gradient(180deg,#111827,#0b1220);
 border:1px solid var(--border);
 border-radius:18px;
 padding:16px;
}

/* ---- headers ---- */
.h1{
 font-size:18px;
 font-weight:700;
 margin-bottom:6px;
}
.hint{
 color:var(--muted);
 font-size:13px;
 margin-bottom:10px;
}

/* ---- project selector ---- */
select{
 width:100%;
 padding:14px;
 border-radius:14px;
 border:none;
 background:#020617;
 color:var(--text);
 font-size:15px;
}

/* ---- textarea ---- */
textarea{
 width:100%;
 min-height:140px;
 border-radius:14px;
 border:none;
 background:#020617;
 color:var(--text);
 padding:14px;
 font-size:15px;
 resize:none;
}

/* ---- code ---- */
pre{
 background:#020617;
 border-radius:14px;
 padding:14px;
 font-size:13px;
 line-height:1.5;
 min-height:160px;
 white-space:pre-wrap;
}

/* ---- buttons ---- */
.btn{
 width:100%;
 padding:16px;
 border-radius:16px;
 border:none;
 font-size:16px;
 font-weight:700;
 margin-top:8px;
}

.primary{
 background:linear-gradient(90deg,var(--accent),#818cf8);
 color:white;
}

.success{
 background:linear-gradient(90deg,var(--accent2),#4ade80);
 color:black;
}

.danger{
 background:linear-gradient(90deg,var(--danger),#f87171);
 color:white;
}

.row{
 display:flex;
 gap:10px;
}
</style>
</head>

<body>
<div class="app">

<!-- PROJECT -->
<div class="card">
  <div class="h1">📁 Project</div>
  <div class="hint">Choose existing or create new</div>
  <select id="projectSelect"></select>
</div>

<!-- TASK -->
<div class="card">
  <div class="h1">✍️ Task</div>
  <div class="hint">Describe what you want to build</div>
  <textarea id="taskText"
    placeholder="Example: FastAPI CRUD with JWT auth"></textarea>
</div>

<!-- CODE -->
<div class="card">
  <div class="h1">💻 Code</div>
  <div class="hint">Generated result will appear here</div>
  <pre id="codeText">// waiting for generation…</pre>
</div>

<!-- ACTIONS -->
<div class="card">
  <button class="btn primary" id="btnGenerate">⚡ Generate code</button>
  <div class="row">
    <button class="btn success" id="btnSave">💾 Save</button>
    <button class="btn danger" id="btnDelete">🗑 Delete</button>
  </div>
</div>

</div>

<script>
const tg = window.Telegram.WebApp;
tg.expand(); tg.ready();

let currentProject = null;
const select = document.getElementById("projectSelect");

async function loadProjects(){
 const r = await fetch('/projects/list/' + tg.initDataUnsafe.user.id);
 const data = await r.json();
 select.innerHTML =
   '<option value="">➕ New project</option>' +
   data.map(p=>`<option value="${{p.id}}">${{p.title}}</option>`).join('');
}

select.addEventListener('change', async ()=>{
 if(!select.value){ currentProject=null; return; }
 currentProject = select.value;
 const r = await fetch('/projects/' + currentProject);
 const p = await r.json();
 taskText.value = p.task;
 codeText.textContent = p.code;
});

document.getElementById("btnGenerate").onclick = async ()=>{
 const r = await fetch('/generate',{
  method:'POST',
  headers:{'Content-Type':'application/json'},
  body:JSON.stringify({
   user_id: tg.initDataUnsafe.user.id,
   text: taskText.value
  })
 });
 codeText.textContent = (await r.json()).code;
};

document.getElementById("btnSave").onclick = async ()=>{
 await fetch('/projects/save',{
  method:'POST',
  headers:{'Content-Type':'application/json'},
  body:JSON.stringify({
   user_id: tg.initDataUnsafe.user.id,
   title: taskText.value.slice(0,40)||'Untitled',
   task: taskText.value,
   code: codeText.textContent
  })
 });
 loadProjects();
};

document.getElementById("btnDelete").onclick = async ()=>{
 if(!currentProject) return;
 await fetch('/projects/delete',{
  method:'POST',
  headers:{'Content-Type':'application/json'},
  body:JSON.stringify({
   user_id: tg.initDataUnsafe.user.id,
   project_id: currentProject
  })
 });
 taskText.value=''; codeText.textContent='';
 loadProjects();
};

loadProjects();
</script>
</body>
</html>
"""


# ======================= TELEGRAM BOT =================

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message()
async def start(msg: types.Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(
                text="🚀 Open Code Studio",
                web_app=WebAppInfo(url=APP_URL)
            )
        ]],
        resize_keyboard=True
    )
    await msg.answer(
        "💻 AI Code Studio\n\nJust open and start coding.",
        reply_markup=kb
    )

async def start_bot():
    await dp.start_polling(bot)

@app.on_event("startup")
async def startup():
    await init_db()
    asyncio.create_task(start_bot())







