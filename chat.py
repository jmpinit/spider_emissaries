import sqlite3
import threading
import atexit
import time
import markovify
import random

from config import DATABASE, CHAT_MIN_DELAY, CHAT_MAX_DELAY


def get_model(label, db):
    cur = db.cursor()
    cur.execute('''SELECT model FROM models WHERE label=?''', (label,))

    row = cur.fetchone()

    if row is None:
        return None

    model_json = row[0]
    # TODO: use an in-memory cache instead of parsing models every time they are accessed
    return markovify.Text.from_json(model_json)


def interrupt_chat():
    global chat_thread
    chat_thread.cancel()


def someone_say_something_maybe():
    db = sqlite3.connect(DATABASE)
    cur = db.cursor()

    # Pick a user at random
    cur.execute('''SELECT id, name, model_label FROM users ORDER BY RANDOM() LIMIT 1;''')
    row = cur.fetchone()
    user_id = row[0]
    user_name = row[1]
    model_label = row[2]

    # Get their current model
    model = get_model(model_label, db)

    print('Going to say something?')

    if model is None:
        return

    maybe_text = model.make_sentence(tries=100)

    if maybe_text is None:
        return

    print(f'User {user_name} with ID {user_id} using model {model_label} says: {maybe_text}')
    unix_time = round(time.time())
    cur.execute('''INSERT INTO chat(unix_time, user_id, model_label, message)
        VALUES(?, ?, ?, ?)''', (unix_time, user_id, model_label, maybe_text)
                )
    db.commit()


def update_chat():
    someone_say_something_maybe()

    delay = random.randint(CHAT_MIN_DELAY, CHAT_MAX_DELAY)

    global chat_thread
    chat_thread = threading.Timer(delay, update_chat, ())
    chat_thread.start()


if __name__ == '__main__':
    chat_thread = threading.Timer(CHAT_MIN_DELAY, update_chat, ())
    # Start updating the chat
    chat_thread.start()

    # Kill the chat thread when the app is closed
    atexit.register(interrupt_chat)
