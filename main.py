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

<title>AI Code Studio</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>

<style>
:root {
  --bg: #0b0f14;
  --panel: #0f172a;
  --panel-2: #111827;
  --border: #1f2937;
  --text: #e5e7eb;
  --muted: #9ca3af;
  --accent: #6366f1;
  --accent-hover: #4f46e5;
}

* {
  box-sizing: border-box;
}

html, body {
  margin: 0;
  padding: 0;
  height: 100%;
  overflow: hidden;
  background: var(--bg);
  color: var(--text);
  font-family: Inter, system-ui, sans-serif;
}

/* ---------- LAYOUT ---------- */
.app {
  display: grid;
  grid-template-columns: 260px 1fr;
  grid-template-rows: 1fr auto;
  height: 100vh;
}

/* ---------- PROJECTS ---------- */
#projects {
  grid-row: 1 / 3;
  background: var(--panel);
  border-right: 1px solid var(--border);
  padding: 14px;
  overflow-y: auto;
}

#projects h3 {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--muted);
  text-transform: uppercase;
}

.project {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 6px;
  background: transparent;
}

.project:hover {
  background: var(--panel-2);
}

/* ---------- TASK + CODE ---------- */
#task-panel {
  display: grid;
  grid-template-rows: 160px 1fr;
  background: var(--panel-2);
}

textarea {
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  padding: 14px;
  font-size: 15px;
  background: #020617;
  color: var(--text);
}

pre {
  margin: 0;
  padding: 14px;
  background: #000;
  overflow: auto;
  font-size: 13px;
  line-height: 1.5;
}

/* ---------- CONTROLS ---------- */
.controls {
  display: flex;
  gap: 14px;
  padding: 14px;
  background: var(--panel);
  border-top: 1px solid var(--border);
}

button {
  flex: 1;
  padding: 14px;
  font-size: 15px;
  font-weight: 600;
  border-radius: 10px;
  border: none;
  cursor: pointer;
}

button.primary {
  background: var(--accent);
  color: white;
}

button.primary:hover {
  background: var(--accent-hover);
}

button.secondary {
  background: #1f2937;
  color: var(--text);
}

button.secondary:hover {
  background: #273449;
}
</style>
</head>

<body>
<div class="app">

  <!-- PROJECTS -->
  <div id="projects">
    <h3>Projects</h3>
  </div>

  <!-- TASK + CODE -->
  <div id="task-panel">
    <textarea id="task"
      placeholder="Describe what you want to build...&#10;Example: FastAPI CRUD with JWT auth"></textarea>
    <pre id="code"></pre>
  </div>

  <!-- CONTROLS -->
  <div class="controls">
    <button class="primary" onclick="generate()">Generate</button>
    <button class="secondary" onclick="saveProject()">Save</button>
    <button class="secondary" onclick="deleteProject()">Delete</button>
  </div>

</div>

<script>
const tg = window.Telegram.WebApp;
tg.expand();

let currentProject = null;
const projectsEl = document.getElementById("projects");
const task = document.getElementById("task");
const code = document.getElementById("code");

async function loadProjects() {
  const r = await fetch('/projects/list/' + tg.initDataUnsafe.user.id);
  const data = await r.json();
  projectsEl.innerHTML =
    '<h3>Projects</h3>' +
    data.map(p =>
      `<div class="project" onclick="openProject(${{p.id}})">📄 ${{p.title}}</div>`
    ).join('');
}

async function openProject(id) {
  currentProject = id;
  const r = await fetch('/projects/' + id);
  const p = await r.json();
  task.value = p.task;
  code.textContent = p.code;
}

async function generate() {
  const r = await fetch('/generate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      user_id: tg.initDataUnsafe.user.id,
      text: task.value
    })
  });
  code.textContent = (await r.json()).code;
}

async function saveProject() {
  await fetch('/projects/save', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      user_id: tg.initDataUnsafe.user.id,
      title: task.value.slice(0, 40) || 'Untitled project',
      task: task.value,
      code: code.textContent
    })
  });
  loadProjects();
}

async function deleteProject() {
  if (!currentProject) return;
  await fetch('/projects/delete', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      user_id: tg.initDataUnsafe.user.id,
      project_id: currentProject
    })
  });
  task.value = '';
  code.textContent = '';
  loadProjects();
}

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



