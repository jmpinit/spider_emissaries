create table models (id INTEGER PRIMARY KEY, label TEXT, model TEXT);
create table users (id INTEGER PRIMARY KEY, name TEXT, model_label TEXT);
create table chat (id INTEGER PRIMARY KEY, unix_time INTEGER, user_id INTEGER, model_label TEXT, message TEXT);
