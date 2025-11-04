import json
import os
from pathlib import Path

from flask import Flask, flash, render_template_string, request

import pwgen


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("PWGEN_WEB_SECRET", os.urandom(16).hex())

VAULT_PATH = Path(os.environ.get("PWGEN_VAULT_PATH", pwgen.DEFAULT_VAULT)).expanduser()


HTML_TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>pwgen web</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, sans-serif; }
    body { margin: 0 auto; padding: 1.5rem; max-width: 720px; }
    h1 { margin-bottom: 1rem; }
    form { display: grid; gap: 1rem; margin-bottom: 1.5rem; }
    label { display: flex; flex-direction: column; gap: 0.35rem; font-weight: 600; }
    input, button, select { font: inherit; padding: 0.5rem; border-radius: 0.5rem; border: 1px solid #9994; }
    button { cursor: pointer; border: 1px solid #6666; background: #eee8; }
    .buttons { display: flex; gap: 0.75rem; flex-wrap: wrap; }
    .flash { margin: 0 0 1rem; padding: 0; list-style: none; }
    .flash li { padding: 0.6rem 0.8rem; border-radius: 0.5rem; margin-bottom: 0.6rem; }
    .flash li.error { background: #ffdddd; color: #700; }
    .flash li.success { background: #ddffdd; color: #074; }
    .flash li.warning { background: #fff4d6; color: #754; }
    .flash li.info { background: #dde9ff; color: #134; }
    .result { padding: 1rem; border: 1px solid #9994; border-radius: 0.75rem; margin-bottom: 1.5rem; }
    .result input { width: 100%; font-family: 'Fira Code', Consolas, monospace; font-size: 1.1rem; }
    table { width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.95rem; }
    th, td { border: 1px solid #9994; padding: 0.4rem 0.5rem; text-align: left; }
    th { font-weight: 600; }
    caption { text-align: left; font-weight: 600; margin-bottom: 0.5rem; }
    small { color: #666; }
  </style>
</head>
<body>
  <h1>pwgen web</h1>
  <p><small>Хранилище: {{ vault_path }}</small></p>

  {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
      <ul class="flash">
      {% for category, message in messages %}
        <li class="{{ category }}">{{ message }}</li>
      {% endfor %}
      </ul>
    {% endif %}
  {% endwith %}

  {% if password %}
    <div class="result">
      <label>Сгенерированный пароль
        <input type="text" value="{{ password }}" readonly onclick="this.select();" spellcheck="false">
      </label>
      <small>Версия алгоритма: {{ version }}, использован c={{ used_c }}</small>
    </div>
  {% endif %}

  <form method="post" autocomplete="off">
    <label>
      Мастер-пароль
      <input type="password" name="master" placeholder="Введите мастер-пароль" required autocomplete="current-password">
    </label>
    <label>
      Сайт / домен
      <input type="text" name="site" value="{{ site }}" placeholder="example.com">
    </label>
    <label>
      Логин
      <input type="text" name="login" value="{{ login }}" placeholder="you@mail.com">
    </label>
    <label>
      Переопределить длину (опционально)
      <input type="number" min="4" max="128" name="length" value="{{ length_override }}">
    </label>
    <div class="buttons">
      <button type="submit" name="action" value="generate">Сгенерировать</button>
      <button type="submit" name="action" value="list">Обновить список</button>
    </div>
  </form>

  {% if entries %}
    <table>
      <caption>Сайты в хранилище</caption>
      <thead>
        <tr>
          <th>Сайт</th>
          <th>Логин</th>
          <th>Длина</th>
          <th>Классы</th>
          <th>c</th>
          <th>Версия</th>
        </tr>
      </thead>
      <tbody>
      {% for item in entries %}
        <tr>
          <td>{{ item.site_id }}</td>
          <td>{{ item.login }}</td>
          <td>{{ item.policy.length }}</td>
          <td>{{ ','.join(item.policy.classes) }}</td>
          <td>{{ item.c }}</td>
          <td>{{ item.v }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  {% endif %}
</body>
</html>
"""


def load_vault(master: str) -> dict:
    blob = pwgen.vault_load(str(VAULT_PATH))
    plaintext = pwgen.vault_decrypt(blob, master)
    return json.loads(plaintext.decode("utf-8"))


def format_entries(raw_sites: dict) -> list:
    entries = []
    for entry in raw_sites.values():
        entries.append({
            "site_id": entry["site_id"],
            "login": entry["login"],
            "policy": entry["policy"],
            "c": entry.get("c", 0),
            "v": entry.get("v", pwgen.ALGO_VERSION),
        })
    entries.sort(key=lambda x: (x["site_id"], x["login"]))
    return entries


@app.route("/", methods=["GET", "POST"])
def index():
    password = None
    used_c = None
    version = None
    entries = []

    site_field = request.form.get("site", "")
    login_field = request.form.get("login", "")
    length_field = request.form.get("length", "")
    action = request.form.get("action", "generate")

    if request.method == "POST":
        master = request.form.get("master", "")
        if not master:
            flash("Введите мастер-пароль.", "error")
        else:
            try:
                data = load_vault(master)
            except Exception as exc:
                flash(f"Не удалось расшифровать {VAULT_PATH}: {exc}", "error")
            else:
                entries = format_entries(data["sites"])
                if action == "generate":
                    if not site_field or not login_field:
                        flash("Укажите сайт и логин.", "error")
                    else:
                        site_id = pwgen.normalize_site_id(site_field)
                        key = f"{site_id}|{login_field.strip()}"
                        entry = data["sites"].get(key)
                        if not entry:
                            flash("Такой пары сайт/логин нет в хранилище.", "error")
                        else:
                            policy = entry["policy"]
                            if length_field:
                                try:
                                    override_len = int(length_field)
                                except ValueError:
                                    flash("Длина должна быть целым числом.", "error")
                                    entry = None
                                else:
                                    if override_len < 4 or override_len > 128:
                                        flash("Длина должна быть в диапазоне 4..128.", "error")
                                        entry = None
                                    else:
                                        policy = dict(policy)
                                        policy["length"] = override_len
                            if entry:
                                capsule = pwgen.b64d(data["capsule"])
                                version = entry.get("v", pwgen.ALGO_VERSION)
                                try:
                                    password, used_c = pwgen.gen_password_with_retries(
                                        master,
                                        capsule,
                                        site_id,
                                        login_field.strip(),
                                        policy,
                                        version,
                                        int(entry.get("c", 0)),
                                        bytes.fromhex(entry["rseed"]),
                                    )
                                except ValueError as exc:
                                    flash(str(exc), "error")
                                else:
                                    if used_c != int(entry.get("c", 0)):
                                        flash(
                                            f"Для выполнения требований политики использован c={used_c} "
                                            f"вместо сохранённого c={entry.get('c', 0)}.",
                                            "warning",
                                        )
                                    flash("Пароль сгенерирован.", "success")
                                    site_field = site_id
                else:
                    flash("Список записей обновлён.", "info")

    context = {
        "password": password,
        "used_c": used_c,
        "version": version,
        "entries": entries,
        "site": site_field,
        "login": login_field,
        "length_override": length_field,
        "vault_path": VAULT_PATH,
    }
    return render_template_string(HTML_TEMPLATE, **context)


if __name__ == "__main__":
    host = os.environ.get("PWGEN_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("PWGEN_WEB_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
