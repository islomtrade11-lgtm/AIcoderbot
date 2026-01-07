import os
import asyncio
import aiosqlite
import httpx

from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import Update
from fastapi import Request, HTTPException

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

from pydantic import BaseModel

from pydantic import BaseModel

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

# ======================= CONFIG =======================
BOT_TOKEN = os.getenv("BOT_TOKEN")
APP_URL = os.getenv("APP_URL")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
MINIAPP_URL = os.getenv("MINIAPP_URL")

MODEL = "deepseek/deepseek-coder:instruct"
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
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 2000,
            }
        )

        if r.status_code != 200:
            raise RuntimeError(r.text)

        return r.json()["choices"][0]["message"]["content"]

# ======================= API ==========================

@app.post("/generate")
async def generate(req: Generate):
    try:
        code = await call_llm([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": req.text}
        ])

        if not code:
            return {"error": "Empty response from LLM"}

        return {"code": code}

    except Exception as e:
        print("❌ GENERATE ERROR:", repr(e))
        return {"error": str(e)}


@app.post("/projects/save")
async def save_project(p: SaveProject):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                INSERT INTO projects (user_id, title, task, code)
                VALUES (?, ?, ?, ?)
                """,
                (p.user_id, p.title, p.task, p.code)
            )
            await db.commit()
        return {"status": "ok"}

    except Exception as e:
        print("❌ SAVE PROJECT ERROR:", repr(e))
        return {"error": "Failed to save project"}
        
from aiogram.types import BufferedInputFile
from pydantic import BaseModel

class SendProject(BaseModel):
    user_id: int
    title: str
    code: str

@app.post("/projects/send_to_chat")
async def send_project_to_chat(p: SendProject):
    file_bytes = p.code.encode("utf-8")

    document = BufferedInputFile(
        file=file_bytes,
        filename=f"{p.title or 'project'}.py"
    )

    await bot.send_document(
        chat_id=p.user_id,
        document=document,
        caption=f"📦 {p.title}"
    )

    return {"status": "sent"}


@app.get("/projects/list/{user_id}")
async def list_projects(user_id: int):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """
                SELECT id, title
                FROM projects
                WHERE user_id=?
                ORDER BY created_at DESC
                """,
                (user_id,)
            )
            rows = await cur.fetchall()

        return [{"id": r[0], "title": r[1]} for r in rows]

    except Exception as e:
        print("❌ LIST PROJECTS ERROR:", repr(e))
        return []


@app.get("/projects/{project_id}")
async def get_project(project_id: int):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                """
                SELECT title, task, code
                FROM projects
                WHERE id=?
                """,
                (project_id,)
            )
            r = await cur.fetchone()

        if not r:
            return {"error": "Project not found"}

        return {
            "title": r[0],
            "task": r[1],
            "code": r[2]
        }

    except Exception as e:
        print("❌ GET PROJECT ERROR:", repr(e))
        return {"error": "Failed to load project"}


@app.post("/projects/delete")
async def delete_project(p: DeleteProject):
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                """
                DELETE FROM projects
                WHERE id=? AND user_id=?
                """,
                (p.project_id, p.user_id)
            )
            await db.commit()

        return {"status": "deleted"}

    except Exception as e:
        print("❌ DELETE PROJECT ERROR:", repr(e))
        return {"error": "Failed to delete project"}
        import tempfile
        
import subprocess
import os
import textwrap
from pydantic import BaseModel

class TestRequest(BaseModel):
    code: str

@app.post("/tests/run")
async def run_tests(req: TestRequest):
    with tempfile.TemporaryDirectory() as tmp:
        app_file = os.path.join(tmp, "app.py")
        test_file = os.path.join(tmp, "test_app.py")

        # сохраняем код проекта
        with open(app_file, "w", encoding="utf-8") as f:
            f.write(req.code)

        # простой автотест (проверка, что код хотя бы импортируется)
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent("""
                import app

                def test_import():
                    assert app is not None
            """))

        try:
            result = subprocess.run(
                ["pytest", "-q"],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=10
            )

            return {
                "ok": result.returncode == 0,
                "output": result.stdout + result.stderr
            }

        except Exception as e:
            return {
                "ok": False,
                "output": str(e)
            }


# ======================= MINI APP =====================

@app.get("/", response_class=HTMLResponse)
async def mini_app():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport"
content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">

<title>AI Code Studio</title>
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

/* cards */
.card{
 background:linear-gradient(180deg,#111827,#0b1220);
 border:1px solid var(--border);
 border-radius:18px;
 padding:16px;
}

/* headers */
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

/* inputs */
select, textarea{
 width:100%;
 border-radius:14px;
 border:none;
 background:#020617;
 color:var(--text);
 font-size:15px;
 padding:14px;
}

textarea{
 min-height:140px;
 resize:none;
}

/* code */
pre{
 background:#020617;
 border-radius:14px;
 padding:14px;
 font-size:13px;
 line-height:1.5;
 min-height:160px;
 white-space:pre-wrap;
}

/* buttons */
.btn{
 width:100%;
 padding:16px;
 border-radius:16px;
 border:none;
 font-size:16px;
 font-weight:700;
 margin-top:8px;
 cursor:pointer;
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
  <button type="button" class="btn primary" id="btnGenerate">⚡ Generate code</button>
  <div class="row">
    <button type="button" class="btn success" id="btnSave">💾 Save</button>
    <button type="button" class="btn danger" id="btnDelete">🗑 Delete</button>
    <button type="button" class="btn success" id="btnTests">🧪 Run tests</button>
    <button type="button" class="btn primary" id="btnSend">📤 Send to chat</button>
  </div>
</div>

</div>

<script>
/* ===== SAFE TELEGRAM INIT ===== */
let USER_ID = 0;

if (window.Telegram && window.Telegram.WebApp) {
  const tg = window.Telegram.WebApp;
  tg.expand();
  tg.ready();

  if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
    USER_ID = tg.initDataUnsafe.user.id;
  }
}

/* ===== DOM ===== */
const API = location.origin;

const select = document.getElementById("projectSelect");
const taskText = document.getElementById("taskText");
const codeText = document.getElementById("codeText");
const btnGenerate = document.getElementById("btnGenerate");
const btnSave = document.getElementById("btnSave");
const btnDelete = document.getElementById("btnDelete");
const btnTests = document.getElementById("btnTests");
const btnSend = document.getElementById("btnSend");

let currentProject = null;

/* ===== GUARD ===== */
if (!btnGenerate) {
  alert("btnGenerate NOT FOUND");
}

/* ===== LOAD PROJECTS ===== */
async function loadProjects() {
  if (!USER_ID) return;

  const r = await fetch(API + "/projects/list/" + USER_ID);
  const data = await r.json();

  select.innerHTML =
    '<option value="">➕ New project</option>' +
    data.map(p => `<option value="${p.id}">${p.title}</option>`).join("");
}

/* ===== SELECT ===== */
select.addEventListener("change", async () => {
  if (!select.value) {
    currentProject = null;
    return;
  }

  currentProject = select.value;
  const r = await fetch(API + "/projects/" + currentProject);
  const p = await r.json();

  taskText.value = p.task;
  codeText.textContent = p.code;
});

/* ===== GENERATE ===== */
btnGenerate.addEventListener("click", async () => {
  codeText.textContent = "⏳ Generating code...";

  try {
    const r = await fetch(API + "/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: USER_ID,
        text: taskText.value
      })
    });

    const raw = await r.text();
    const data = JSON.parse(raw);

    codeText.textContent = data.code || "❌ Empty response";
  } catch (e) {
    codeText.textContent = "❌ " + e.message;
  }
});

/* ===== SAVE ===== */
btnSave.addEventListener("click", async () => {
  await fetch(API + "/projects/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: USER_ID,
      title: taskText.value.slice(0, 40) || "Untitled",
      task: taskText.value,
      code: codeText.textContent
    })
  });
  loadProjects();
});

/* ===== DELETE ===== */
btnDelete.addEventListener("click", async () => {
  if (!currentProject) return;

  await fetch(API + "/projects/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: USER_ID,
      project_id: currentProject
    })
  });

  taskText.value = "";
  codeText.textContent = "";
  loadProjects();
});

/* ===== TESTS ===== */
btnTests.addEventListener("click", async () => {
  codeText.textContent = "🧪 Running tests...";

  const r = await fetch(API + "/tests/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code: codeText.textContent })
  });

  const data = await r.json();
  codeText.textContent =
    (data.ok ? "✅ Tests passed\n\n" : "❌ Tests failed\n\n") + data.output;
});

/* ===== SEND TO CHAT ===== */
btnSend.addEventListener("click", async () => {
  await fetch(API + "/projects/send_to_chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: USER_ID,
      title: taskText.value.slice(0, 40) || "project",
      code: codeText.textContent
    })
  });

  alert("📤 Sent to chat");
});

/* ===== INIT ===== */
loadProjects();
</script>
</body>
</html>
"""

# ======================= TELEGRAM BOT =================

from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import Update
from fastapi import Request, HTTPException

session = AiohttpSession(timeout=60)
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()

@dp.message()
async def start(msg: types.Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(
                text="🚀 Open Code Studio",
                web_app=WebAppInfo(url=MINIAPP_URL)
            )
        ]],
        resize_keyboard=True
    )
    await msg.answer(
        "💻 AI Code Studio\n\nJust open and start coding.",
        reply_markup=kb
    )

# ======================= WEBHOOK ======================

@app.post("/webhook")
async def telegram_webhook(request: Request):
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    if secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")

    data = await request.json()
    update = Update.model_validate(data)

    # 🚀 НЕ ЖДЁМ обработку — запускаем в фоне
    asyncio.create_task(dp.feed_update(bot, update))

    # ⚡ СРАЗУ отвечаем Telegram
    return {"ok": True}


# ======================= STARTUP ======================

@app.on_event("startup")
async def on_startup():
    await init_db()

    await bot.set_webhook(
        url=f"{APP_URL}/webhook",
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=True
    )

    print("✅ Webhook enabled")




































