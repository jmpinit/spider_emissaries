import requests
from bs4 import BeautifulSoup
from flask import Flask, request, g
import markovify
import sqlite3
import hashlib

DATABASE = 'spider.db'

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


def store_model(label, model):
    if get_model(label) is not None:
        raise Exception('Model with label already exists')

    db = get_db()
    cur = db.cursor()
    cur.execute('''INSERT INTO models(label, model) VALUES(?, ?)''', (label, model.to_json()))
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


@app.route('/api/v1/model/sentence')
def api_model_sentence():
    label = request.args.get('model_label')

    # TODO: Optionally generate a response to a prompt
    #prompt = request.args.get('prompt')

    if label is None or len(label) == 0:
        return 'Must specify a model label to retrieve text', 400

    model = get_model(label)

    if model is None:
        return 'No model with given label', 400

    maybe_text = model.make_sentence(tries=100)

    if maybe_text is None:
        return ''

    return maybe_text

