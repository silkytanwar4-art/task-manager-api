"""
FastAPI CRUD service for managing Tasks, backed by MySQL (Aiven).

Required environment variables (in fasti.env next to this file):
    DB_HOST      = mysql-1cf54b65-silkytanwar4-a112.c.aivencloud.com
    DB_NAME      = Task_Manager
    DB_USER      = avnadmin
    DB_PASSWORD  = your_actual_password_here
    DB_PORT      = 13912
"""

from contextlib import contextmanager
from pathlib import Path
import os

import mysql.connector
from mysql.connector import Error as MySQLError
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Load variables from fasti.env, located next to this script
load_dotenv(Path(__file__).resolve().parent / "fasti.env")

# --- Configuration -------------------------------------------------------

DB_HOST     = os.getenv("DB_HOST")
DB_NAME     = os.getenv("DB_NAME")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
_DB_PORT_RAW = os.getenv("DB_PORT", "13912")  # Aiven default port

# CA certificate path — place ca.pem in the same folder as this file
CA_CERT = str(Path(__file__).resolve().parent / "ca.pem")

_required = {
    "DB_HOST": DB_HOST,
    "DB_NAME": DB_NAME,
    "DB_USER": DB_USER,
    "DB_PASSWORD": DB_PASSWORD,
}
_missing = [name for name, value in _required.items() if not value]
if _missing:
    raise RuntimeError(f"Missing required environment variable(s): {', '.join(_missing)}")

try:
    DB_PORT = int(_DB_PORT_RAW)
except ValueError as exc:
    raise RuntimeError(f"DB_PORT must be an integer, got {_DB_PORT_RAW!r}") from exc


# --- Database helpers ----------------------------------------------------

@contextmanager
def get_connection():
    """Yield a MySQL connection, guaranteeing it is closed afterwards."""
    conn = mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        ssl_ca=CA_CERT,         # Aiven CA certificate
        ssl_verify_cert=True,   # Verify SSL certificate
    )
    try:
        yield conn
    finally:
        conn.close()


# --- Models --------------------------------------------------------------

class Task(BaseModel):
    id: int
    title: str
    deadline: str
    status: str


class TaskUpdate(BaseModel):
    title: str
    deadline: str
    status: str


# --- App -----------------------------------------------------------------

app = FastAPI()


@app.post("/tasks", status_code=201)
def create_task(task: Task):
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO Tasks (id, title, deadline, status) VALUES (%s, %s, %s, %s)",
                (task.id, task.title, task.deadline, task.status),
            )
            conn.commit()
        except MySQLError as exc:
            conn.rollback()
            if exc.errno == 1062:  # Duplicate primary key
                raise HTTPException(status_code=409, detail=f"Task with id {task.id} already exists") from exc
            raise HTTPException(status_code=500, detail="Database error while creating task") from exc
        finally:
            cursor.close()
    return {"task": "created", "id": task.id}


@app.get("/tasks")
def get_tasks():
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM Tasks")
            return cursor.fetchall()
        except MySQLError as exc:
            raise HTTPException(status_code=500, detail="Database error while fetching tasks") from exc
        finally:
            cursor.close()


@app.get("/tasks/{task_id}")
def get_task(task_id: int):
    with get_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM Tasks WHERE id = %s", (task_id,))
            task = cursor.fetchone()
        except MySQLError as exc:
            raise HTTPException(status_code=500, detail="Database error while fetching task") from exc
        finally:
            cursor.close()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@app.put("/tasks/{task_id}")
def update_task(task_id: int, updated_task: TaskUpdate):
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE Tasks SET title=%s, deadline=%s, status=%s WHERE id=%s",
                (updated_task.title, updated_task.deadline, updated_task.status, task_id),
            )
            conn.commit()
            affected = cursor.rowcount
        except MySQLError as exc:
            conn.rollback()
            raise HTTPException(status_code=500, detail="Database error while updating task") from exc
        finally:
            cursor.close()
    if affected == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": "updated"}


@app.delete("/tasks/{task_id}")
def delete_task(task_id: int):
    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM Tasks WHERE id = %s", (task_id,))
            conn.commit()
            affected = cursor.rowcount
        except MySQLError as exc:
            conn.rollback()
            raise HTTPException(status_code=500, detail="Database error while deleting task") from exc
        finally:
            cursor.close()
    if affected == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task": "deleted"}