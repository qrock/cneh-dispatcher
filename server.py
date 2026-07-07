"""
Диспетчер цеха — серверная часть
Запуск: python server.py
Открыть: http://localhost:8000
"""
from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import sqlite3
from datetime import datetime
from contextlib import contextmanager
import uvicorn

app = FastAPI(title="Диспетчер цеха")

DB_PATH = "cneh.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                urgency TEXT NOT NULL DEFAULT 'normal',
                up_name TEXT NOT NULL,
                qty INTEGER NOT NULL,
                path TEXT,
                status TEXT NOT NULL DEFAULT 'new',
                worker_id INTEGER,
                comment TEXT,
                created_at TEXT,
                started_at TEXT,
                finished_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS workers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                pin TEXT NOT NULL UNIQUE
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS admin (
                id INTEGER PRIMARY KEY,
                password TEXT NOT NULL
            )
        """)
        cur = conn.execute("SELECT COUNT(*) FROM workers")
        if cur.fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO workers (name, pin) VALUES (?, ?)",
                [
                    ("Иванов И.И.", "1234"),
                    ("Петров П.П.", "2345"),
                    ("Сидоров С.С.", "3456"),
                ]
            )
        cur = conn.execute("SELECT COUNT(*) FROM admin")
        if cur.fetchone()[0] == 0:
            conn.execute("INSERT INTO admin (id, password) VALUES (1, 'admin')")
        print("База данных инициализирована")

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

class TaskCreate(BaseModel):
    urgency: str = "normal"
    up_name: str
    qty: int
    path: Optional[str] = ""
    comment: Optional[str] = ""

class TaskUpdate(BaseModel):
    status: Optional[str] = None
    worker_id: Optional[int] = None
    comment: Optional[str] = None

class Login(BaseModel):
    pin: str

class AdminLogin(BaseModel):
    password: str

def verify_worker(x_worker_id: int = Header(...)):
    with get_db() as conn:
        w = conn.execute("SELECT id FROM workers WHERE id=?", (x_worker_id,)).fetchone()
        if not w:
            raise HTTPException(401, "Рабочий не авторизован")
        return w["id"]

def verify_admin(x_admin: str = Header(default="")):
    if x_admin != "1":
        raise HTTPException(401, "Требуется вход админа")
    return True

@app.get("/api/tasks")
def get_tasks():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT t.*, w.name as worker_name
            FROM tasks t
            LEFT JOIN workers w ON t.worker_id = w.id
            WHERE t.status != 'done' 
               OR t.finished_at > datetime('now', '-1 day')
            ORDER BY 
                CASE t.status WHEN 'new' THEN 0 WHEN 'inwork' THEN 1 ELSE 2 END,
                CASE t.urgency WHEN 'urgent' THEN 0 ELSE 1 END,
                t.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]

@app.post("/api/tasks")
def create_task(task: TaskCreate, admin_ok: bool = Depends(verify_admin)):
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO tasks (urgency, up_name, qty, path, comment, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (task.urgency, task.up_name, task.qty, task.path, task.comment,
             datetime.now().isoformat())
        )
        return {"id": cur.lastrowid, "ok": True}

@app.patch("/api/tasks/{task_id}")
def update_task(task_id: int, upd: TaskUpdate, worker_id: int = Depends(verify_worker)):
    with get_db() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not task:
            raise HTTPException(404, "Задача не найдена")
        now = datetime.now().isoformat()
        if upd.status == "inwork":
            conn.execute(
                "UPDATE tasks SET status='inwork', worker_id=?, started_at=? WHERE id=?",
                (worker_id, now, task_id)
            )
        elif upd.status == "done":
            conn.execute(
                "UPDATE tasks SET status='done', finished_at=? WHERE id=?",
                (now, task_id)
            )
        elif upd.status == "new":
            conn.execute(
                "UPDATE tasks SET status='new', worker_id=NULL, started_at=NULL WHERE id=?",
                (task_id,)
            )
        return {"ok": True}

@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int, admin_ok: bool = Depends(verify_admin)):
    with get_db() as conn:
        conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        return {"ok": True}

@app.post("/api/login/worker")
def login_worker(data: Login):
    with get_db() as conn:
        w = conn.execute("SELECT * FROM workers WHERE pin=?", (data.pin,)).fetchone()
        if not w:
            raise HTTPException(401, "Неверный PIN")
        return {"id": w["id"], "name": w["name"]}

@app.post("/api/login/admin")
def login_admin(data: AdminLogin):
    with get_db() as conn:
        a = conn.execute("SELECT * FROM admin WHERE id=1").fetchone()
        if a["password"] != data.password:
            raise HTTPException(401, "Неверный пароль")
        return {"ok": True}

@app.get("/", response_class=HTMLResponse)
def index():
    with open("index.html", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    init_db()
    print("\n" + "="*50)
    print("ДИСПЕТЧЕР ЦЕХА ЗАПУЩЕН")
    print("="*50)
    print("Открыть в браузере: http://localhost:8000")
    print("Для доступа из цеха: http://<IP-ЭТОГО-КОМПЬЮТЕРА>:8000")
    print("\nВход админа:    пароль 'admin'")
    print("Вход рабочего:  PIN '1234' (Иванов)")
    print("                PIN '2345' (Петров)")
    print("                PIN '3456' (Сидоров)")
    print("="*50 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)