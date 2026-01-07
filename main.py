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
 --bg:#0b0f14;--panel:#0f172a;--panel2:#111827;
 --border:#1f2937;--text:#e5e7eb;--muted:#9ca3af;
 --accent:#6366f1;
}
html,body{
 margin:0;height:100%;background:var(--bg);
 font-family:Inter,system-ui,sans-serif;
 color:var(--text);overflow:hidden
}
.app{height:100vh;display:flex;flex-direction:column}

/* tabs */
.tabs{display:flex;background:var(--panel);border-bottom:1px solid var(--border)}
.tab{
 flex:1;padding:14px 0;text-align:center;
 color:var(--muted);font-size:14px
}
.tab.active{color:#fff;border-bottom:2px solid var(--accent)}

/* views */
.view{flex:1;display:none;padding:16px;overflow-y:auto}
.view.active{display:block}

/* ui */
.card{
 background:var(--panel);border-radius:14px;
 padding:18px;margin-bottom:14px
}
textarea{
 width:100%;height:200px;background:var(--panel2);
 border:none;border-radius:12px;padding:14px;
 color:var(--text);font-size:15px;resize:none
}
pre{
 background:#020617;border-radius:12px;
 padding:14px;font-size:13px;min-height:250px
}
button{
 width:100%;padding:16px;border:none;
 border-radius:14px;font-size:16px;
 font-weight:600;margin-bottom:12px
}
.primary{background:var(--accent);color:#fff}
.secondary{background:var(--panel);color:var(--text)}
</style>
</head>

<body>
<div class="app">

<div class="tabs">
  <div class="tab active" data-tab="projects">Projects</div>
  <div class="tab" data-tab="task">Task</div>
  <div class="tab" data-tab="code">Code</div>
  <div class="tab" data-tab="actions">Actions</div>
</div>

<div id="projects" class="view active">
  <div class="card"><b>Your projects</b><br>
  <span style="color:var(--muted)">Select or create a project</span></div>
  <div id="projectsList"></div>
</div>

<div id="task" class="view">
  <div class="card"><b>Describe your task</b></div>
  <textarea id="taskText"></textarea>
</div>

<div id="code" class="view">
  <div class="card"><b>Generated code</b></div>
  <pre id="codeText">// Waiting for generation…</pre>
</div>

<div id="actions" class="view">
  <button class="primary" id="btnGenerate">Generate Code</button>
  <button class="secondary" id="btnSave">Save Project</button>
  <button class="secondary" id="btnDelete">Delete Project</button>
</div>

</div>

<script>
const tg=window.Telegram.WebApp;
tg.expand();tg.ready();

let currentProject=null;

function showTab(id){
 document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
 document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
 document.getElementById(id).classList.add('active');
 document.querySelector(`.tab[data-tab="${id}"]`).classList.add('active');
}

document.querySelectorAll('.tab').forEach(tab=>{
 tab.addEventListener('click',()=>{
   showTab(tab.dataset.tab);
 });
});

async function loadProjects(){
 const r=await fetch('/projects/list/'+tg.initDataUnsafe.user.id);
 const data=await r.json();
 projectsList.innerHTML=data.length
  ? data.map(p=>`<div class="card" data-id="${{p.id}}">📄 ${{p.title}}</div>`).join('')
  : '<div class="card">No projects yet</div>';

 document.querySelectorAll('#projectsList .card').forEach(el=>{
   el.addEventListener('click',()=>openProject(el.dataset.id));
 });
}

async function openProject(id){
 currentProject=id;
 const r=await fetch('/projects/'+id);
 const p=await r.json();
 taskText.value=p.task;
 codeText.textContent=p.code;
 showTab('task');
}

async function generate(){
 const r=await fetch('/generate',{
  method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({user_id:tg.initDataUnsafe.user.id,text:taskText.value})
 });
 codeText.textContent=(await r.json()).code;
 showTab('code');
}

async function saveProject(){
 await fetch('/projects/save',{
  method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({
   user_id:tg.initDataUnsafe.user.id,
   title:taskText.value.slice(0,40)||'Untitled',
   task:taskText.value,
   code:codeText.textContent
  })
 });
 loadProjects();
}

async function deleteProject(){
 if(!currentProject)return;
 await fetch('/projects/delete',{
  method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({
   user_id:tg.initDataUnsafe.user.id,
   project_id:currentProject
  })
 });
 taskText.value='';codeText.textContent='';
 loadProjects();showTab('projects');
}

document.getElementById('btnGenerate').addEventListener('click',generate);
document.getElementById('btnSave').addEventListener('click',saveProject);
document.getElementById('btnDelete').addEventListener('click',deleteProject);

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






