import requests
from bs4 import BeautifulSoup
from flask import Flask, request, g, jsonify
import markovify
import sqlite3
import hashlib
from config import DATABASE
import random


app = Flask(__name__)


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
    return db


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def exists_model(label):
    db = get_db()
    cur = db.cursor()
    cur.execute('''SELECT EXISTS(SELECT 1 FROM models WHERE label=?)''', (label,))

    if cur.fetchone():
        return True
    else:
        return False


def get_model(label):
    db = get_db()
    cur = db.cursor()
    cur.execute('''SELECT model FROM models WHERE label=?''', (label,))

    row = cur.fetchone()

    if row is None:
        return None

    model_json = row[0]
    # TODO: use an in-memory cache instead of parsing models every time they are accessed
    return markovify.Text.from_json(model_json)


def get_recent_chat_messages():
    db = get_db()
    cur = db.cursor()
    cur.execute('''SELECT unix_time, users.name, message FROM chat
        JOIN users ON chat.user_id = users.id
        ORDER BY unix_time DESC
        LIMIT 10;'''
    )

    messages = []
    for row in cur.fetchall():
        unix_time = row[0]
        name = row[1]
        message = row[2]

        messages += [{
            'time': unix_time,
            'name': name,
            'message': message,
        }]

    return messages


def create_user(user_name):
    db = get_db()
    cur = db.cursor()

    cur.execute('''INSERT INTO users(name) VALUES (?)''', (user_name,))
    db.commit()


def get_user(user_name):
    cur = get_db().cursor()
    cur.execute('''SELECT id, model_label FROM users WHERE name=?''', (user_name,))

    row = cur.fetchone()

    if row is None:
        return None

    user_id = row[0]
    user_model_label = row[1]

    return {
        'id': user_id,
        'name': user_name,
        'model_label': user_model_label,
    }


def update_user_model_label(user_name, model_label):
    if get_user(user_name) is None:
        raise Exception('User with given ID does not exist')

    db = get_db()
    cur = db.cursor()
    cur.execute('''UPDATE users SET model_label = ? WHERE name = ?''', (model_label, user_name))
    db.commit()


def store_model(label, model):
    if get_model(label) is not None:
        raise Exception('Model with label already exists')

    db = get_db()
    cur = db.cursor()
    cur.execute('''INSERT INTO models(label, model) VALUES(?, ?)''', (label, model.to_json()))
    db.commit()


def update_chat(user_name, model_label, message):
    user = get_user(user_name)

    if user is None:
        raise Exception('User does not exist')

    if not exists_model(model_label):
        raise Exception('Model does not exist')

    db = get_db()
    cur = db.cursor()
    cur.execute('''INSERT INTO chat(user_id, model_label, message)
        VALUES(?, ?, ?)''', (user['id'], model_label, message))
    db.commit()


def get_url(url):
    res = requests.get(url)

    if not res.status_code == 200:
        raise Exception(f'Status code is {res.status_code}')

    return res.text


def scrape(url):
    corpus_html = get_url(url)

    soup = BeautifulSoup(corpus_html)
    return soup.get_text().strip()


@app.route('/api/v1/proxy')
def api_proxy():
    try:
        url = request.args.get('url')
    except Exception as e:
        return str(e), 500

    print(f'Proxying {url}')

    return get_url(url)


@app.route('/api/v1/name')
def api_name():
    with open('data/usernames.csv') as username_file:
        usernames = username_file.readlines()
        return random.choice(usernames).strip()


@app.route('/api/v1/user', methods=['GET', 'POST'])
def api_user():
    if request.method == 'GET':
        user_name = request.args.get('user_name')

        if user_name is None:
            return 'Must specify user_name', 400

        user = get_user(user_name)

        if user is None:
            return 'User does not exist', 400

        return jsonify(user)
    elif request.method == 'POST':
        params = request.json

        if 'user_name' not in params:
            return 'Must specify user_name', 400

        if 'model_label' not in params:
            return 'Must specify model_label', 400

        user_name = params['user_name']
        model_label = params['model_label']

        if not exists_model(model_label):
            return 'Specified model does not exist', 400

        if get_user(user_name) is None:
            create_user(user_name)

        update_user_model_label(user_name, model_label)

        return 'ok'


@app.route('/api/v1/model')
def api_model():
    url = request.args.get('url')
    parent_model_label = request.args.get('model_label')

    if url is None or len(url) == 0:
        return 'Must specify URL to create model for', 400

    model_label = hashlib.sha1(((parent_model_label or '') + url).encode('utf-8')).hexdigest()

    model = get_model(model_label)

    # Create the model if it doesn't exist
    if model is None:
        try:
            corpus = scrape(url)
        except Exception as e:
            return f'Failed to retrieve URL: {e}', 500

        parent_models = []

        if parent_model_label:
            prev_model = get_model(parent_model_label)

            if prev_model is None:
                return 'Specified model does not exist', 400

            parent_models += [prev_model]

        parent_models += [markovify.Text(corpus)]
        model = markovify.combine(parent_models)

        store_model(model_label, model)

    return model_label


@app.route('/api/v1/chat')
def api_chat():
    messages = get_recent_chat_messages()
    return jsonify(messages)

