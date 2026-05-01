import sqlite3

def init_db():
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()

    # Создаём таблицу, если её нет
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        question TEXT,
        message_id INTEGER,
        specialist_id INTEGER DEFAULT NULL, 
        specialist_name TEXT DEFAULT NULL
    )
    """)

    # Проверяем, есть ли колонка specialist_id, если нет — добавляем
    cursor.execute("PRAGMA table_info(questions)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if "specialist_id" not in columns:
        cursor.execute("ALTER TABLE questions ADD COLUMN specialist_id INTEGER DEFAULT NULL")
    
    if "specialist_name" not in columns:
        cursor.execute("ALTER TABLE questions ADD COLUMN specialist_name TEXT DEFAULT NULL")

    conn.commit()
    conn.close()

def save_question(user_id, username, question, message_id):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO questions (user_id, username, question, message_id) VALUES (?, ?, ?, ?)", 
                   (user_id, username, question, message_id))
    conn.commit()
    conn.close()

def assign_specialist_to_question(message_id, specialist_id, specialist_name):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE questions SET specialist_id = ?, specialist_name = ? WHERE message_id = ?", 
                   (specialist_id, specialist_name, message_id))
    conn.commit()
    conn.close()

def get_question_by_message_id(message_id):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, question, specialist_id, specialist_name FROM questions WHERE message_id = ?", (message_id,))
    result = cursor.fetchone()
    conn.close()
    return result
