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
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            r = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": MODEL,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": 3000,
                }
            )

            # 🔴 LOG FULL RESPONSE
            print("🔵 OpenRouter status:", r.status_code)
            print("🔵 OpenRouter raw:", r.text)

            data = r.json()

            # ❌ OpenRouter error
            if "error" in data:
                raise RuntimeError(data["error"])

            # ❌ No choices
            if "choices" not in data or not data["choices"]:
                raise RuntimeError("No choices in OpenRouter response")

            choice = data["choices"][0]

            # Normal response
            if "message" in choice and "content" in choice["message"]:
                return choice["message"]["content"]

            # Streaming-like delta response
            if "delta" in choice and "content" in choice["delta"]:
                return choice["delta"]["content"]

            raise RuntimeError("Unknown OpenRouter response format")

        except Exception as e:
            print("❌ call_llm ERROR:", repr(e))
            return None

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
    """
    Generate code from user task.
    Never returns empty response silently.
    """
    try:
        # 1. Enhance user prompt
        enhanced = await call_llm([
            {"role": "system", "content": PROMPT_ENHANCER},
            {"role": "user", "content": req.text}
        ])

        if not enhanced or not enhanced.strip():
            return {
                "error": "Prompt enhancement failed. Empty response from model."
            }

        # 2. Generate final code
        code = await call_llm([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": enhanced}
        ])

        if not code or not code.strip():
            return {
                "error": "Code generation failed. Model returned empty response."
            }

        return {"code": code}

    except Exception as e:
        # IMPORTANT: log error in Railway logs
        print("❌ GENERATE ERROR:", repr(e))
        return {
            "error": "Internal generation error. Check server logs."
        }


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

<title>JS TEST</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>

<style>
body {
  margin:0;
  background:#0b0f14;
  color:white;
  font-family:system-ui;
}
button {
  width:90%;
  margin:40px auto;
  display:block;
  padding:20px;
  font-size:18px;
}
</style>
</head>

<body>
<h2 style="text-align:center">JS CLICK TEST</h2>

<button id="testBtn">CLICK ME</button>

<script>
const tg = window.Telegram.WebApp;
tg.expand();
tg.ready();

console.log("JS LOADED");

document.getElementById("testBtn").addEventListener("click", () => {
  alert("BUTTON WORKS");
  console.log("BUTTON CLICKED");
});
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










