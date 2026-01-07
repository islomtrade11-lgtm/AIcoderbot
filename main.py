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
    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>AI Code Studio</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
body{{margin:0;font-family:monospace;background:#0e0e0e;color:#eee}}
.app{{display:flex;height:100vh}}
#projects{{width:20%;background:#111;padding:10px;overflow:auto}}
#projects div{{padding:5px;cursor:pointer}}
#main{{width:80%;display:flex}}
textarea,pre{{width:50%;padding:15px;border:none;outline:none}}
textarea{{background:#111;color:#fff}}
pre{{background:#000;overflow:auto}}
.controls{{position:fixed;bottom:0;left:20%;right:0;background:#111;padding:10px}}
button{{margin:5px;padding:8px;background:#222;color:#fff;border:none}}
</style>
</head>
<body>
<div class="app">
  <div id="projects"></div>
  <div id="main">
    <textarea id="task" placeholder="Describe what you want to build..."></textarea>
    <pre id="code"></pre>
  </div>
</div>
<div class="controls">
  <button onclick="generate()">Generate</button>
  <button onclick="saveProject()">Save</button>
  <button onclick="deleteProject()">Delete</button>
</div>

<script>
const tg = window.Telegram.WebApp;
tg.expand();
let currentProject=null;

async function loadProjects(){{
  const r=await fetch('/projects/list/'+tg.initDataUnsafe.user.id);
  const data=await r.json();
  projects.innerHTML=data.map(p=>`<div onclick="openProject(${p.id})">📄 ${p.title}</div>`).join('');
}}
loadProjects();

async function openProject(id){{
  currentProject=id;
  const r=await fetch('/projects/'+id);
  const p=await r.json();
  task.value=p.task;
  code.textContent=p.code;
}}

async function generate(){{
  const r=await fetch('/generate',{{
    method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{
      user_id:tg.initDataUnsafe.user.id,
      text:task.value
    }})
  }});
  code.textContent=(await r.json()).code;
}}

async function saveProject(){{
  await fetch('/projects/save',{{
    method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{
      user_id:tg.initDataUnsafe.user.id,
      title:task.value.slice(0,40),
      task:task.value,
      code:code.textContent
    }})
  }});
  loadProjects();
}}

async function deleteProject(){{
  if(!currentProject)return;
  await fetch('/projects/delete',{{
    method:'POST',
    headers:{{'Content-Type':'application/json'}},
    body:JSON.stringify({{
      user_id:tg.initDataUnsafe.user.id,
      project_id:currentProject
    }})
  }});
  task.value='';code.textContent='';
  loadProjects();
}}
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
