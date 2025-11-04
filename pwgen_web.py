#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from pathlib import Path

from flask import (
    Flask, flash, render_template_string, request,
    session, redirect, url_for
)

import pwgen  # ваш локальный модуль

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("PWGEN_WEB_SECRET", os.urandom(32).hex())

# Персистентный путь на Railway задавайте переменной окружения:
# PWGEN_VAULT_PATH=/data/pwgen_vault.json  (при примонтированном volume /data)
VAULT_PATH = Path(os.environ.get("PWGEN_VAULT_PATH", pwgen.DEFAULT_VAULT)).expanduser()

# Необязательный PIN для входа (PWGEN_WEB_PIN=123456)
UI_PIN = os.environ.get("PWGEN_WEB_PIN", "").strip() or None


HTML_TEMPLATE = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>pwgen web</title>
  <style>
    :root { color-scheme: light dark; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
    body { margin: 0 auto; padding: 1.5rem; max-width: 820px; }
    h1 { margin-bottom: 0.5rem; }
    form { display: grid; gap: 1rem; margin-bottom: 1.5rem; grid-template-columns: 1fr 1fr; }
    form > label { display: flex; flex-direction: column; gap: 0.35rem; font-weight: 600; grid-column: span 2; }
    input, button, select { font: inherit; padding: 0.6rem 0.7rem; border-radius: 0.5rem; border: 1px solid #9994; }
    .row { display: contents; }
    .row > label { grid-column: span 1; }
    button { cursor: pointer; border: 1px solid #6666; background: #eee8; }
    .buttons { display: flex; gap: 0.6rem; flex-wrap: wrap; grid-column: span 2; }
    .flash { margin: 0 0 1rem; padding: 0; list-style: none; }
    .flash li { padding: 0.6rem 0.8rem; border-radius: 0.5rem; margin-bottom: 0.6rem; }
    .flash li.error { background: #ffdddd; color: #700; }
    .flash li.success { background: #ddffdd; color: #074; }
    .flash li.warning { background: #fff4d6; color: #754; }
    .flash li.info { background: #dde9ff; color: #134; }
    .result { padding: 1rem; border: 1px solid #9994; border-radius: 0.75rem; margin-bottom: 1.5rem; }
    .result input { width: 100%; font-family: 'Fira Code', Consolas, monospace; font-size: 1.05rem; }
    table { width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.95rem; }
    th, td { border: 1px solid #9994; padding: 0.4rem 0.5rem; text-align: left; }
    th { font-weight: 600; }
    caption { text-align: left; font-weight: 600; margin-bottom: 0.5rem; }
    small { color: #666; }
    code { background:#0001; padding:0 .25rem; border-radius:.25rem; }
  </style>
</head>
<body>
  <h1>pwgen web</h1>
  <p><small>Хранилище: <code>{{ vault_path }}</code></small></p>

  {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
      <ul class="flash">
      {% for category, message in messages %}
        <li class="{{ category }}">{{ message|safe }}</li>
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

    <div class="row">
      <label>
        Сайт / домен
        <input type="text" name="site" value="{{ site }}" placeholder="example.com">
      </label>
      <label>
        Логин
        <input type="text" name="login" value="{{ login }}" placeholder="you@mail.com">
      </label>
    </div>

    <div class="row">
      <label>
        Профиль (для создания записи)
        <select name="profile">
          {% for p in profiles %}
            <option value="{{ p }}" {% if profile==p %}selected{% endif %}>{{ p }}</option>
          {% endfor %}
        </select>
      </label>
      <label>
        Переопределить длину при генерации (опц.)
        <input type="number" min="4" max="128" name="length" value="{{ length_override }}">
      </label>
    </div>

    <div class="buttons">
      <button type="submit" name="action" value="generate">Сгенерировать</button>
      <button type="submit" name="action" value="add_entry">Создать запись (по профилю)</button>
      <button type="submit" name="action" value="rotate_c">Ротация c+1</button>
      <button type="submit" name="action" value="rotate_rseed">Новый rseed</button>
      <button type="submit" name="action" value="list">Обновить список</button>
      <button type="submit" name="action" value="init_vault">Создать вольт (если отсутствует)</button>
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

# ---------- утилиты ----------

def load_vault(master: str) -> dict:
    blob = pwgen.vault_load(str(VAULT_PATH))
    plaintext = pwgen.vault_decrypt(blob, master)
    return json.loads(plaintext.decode("utf-8"))

def save_vault(master: str, data: dict) -> None:
    """Сохранить плейнтекст, сохранив текущие параметры KDF из blob (или дефолты)."""
    try:
        blob = pwgen.vault_load(str(VAULT_PATH))
        t = int(blob["kdf"]["t"]); m = int(blob["kdf"]["m"]); p = int(blob["kdf"]["p"])
    except Exception:
        t = pwgen.DEFAULT_KDF_T; m = pwgen.DEFAULT_KDF_M; p = pwgen.DEFAULT_KDF_P
    data["updated"] = pwgen.now_iso()
    enc = pwgen.vault_encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8"),
                              master, t, m, p)
    pwgen.vault_save(str(VAULT_PATH), enc)

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

def create_vault(master: str) -> None:
    capsule = pwgen.make_capsule("")
    pt = pwgen.make_empty_plaintext(pwgen.b64e(capsule))
    enc = pwgen.vault_encrypt(json.dumps(pt, ensure_ascii=False).encode("utf-8"),
                              master, pwgen.DEFAULT_KDF_T, pwgen.DEFAULT_KDF_M, pwgen.DEFAULT_KDF_P)
    VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pwgen.vault_save(str(VAULT_PATH), enc)

# ---------- PIN-guard (опц.) ----------

@app.before_request
def _require_pin():
    if not UI_PIN:
        return
    if request.endpoint in {"login", "static"}:
        return
    if session.get("ok"):
        return
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("pin") == UI_PIN:
            session["ok"] = True
            return redirect(url_for("index"))
        flash("Неверный PIN", "error")
    return render_template_string("""
    <form method="post" style="max-width:320px;margin:48px auto;font:16px system-ui">
      <h3>Вход</h3>
      <label>PIN <input name="pin" type="password" autofocus></label>
      <button>Войти</button>
    </form>""")

# ---------- основной обработчик ----------

@app.route("/", methods=["GET", "POST"])
def index():
    password = None
    used_c = None
    version = None
    entries = []

    site_field = request.form.get("site", "")
    login_field = request.form.get("login", "")
    length_field = request.form.get("length", "")
    profile_field = request.form.get("profile", "ultra")
    action = request.form.get("action", "generate")

    if request.method == "POST":
        master = request.form.get("master", "")
        if not master:
            flash("Введите мастер-пароль.", "error")
        else:
            # создание вольта из UI
            if action == "init_vault":
                if VAULT_PATH.exists():
                    flash(f"Вольт уже существует: <code>{VAULT_PATH}</code>", "info")
                else:
                    try:
                        create_vault(master)
                        flash(f"Вольт создан: <code>{VAULT_PATH}</code>", "success")
                    except Exception as exc:
                        flash(f"Не удалось создать вольт: {exc}", "error")

            # пробуем загрузить вольт
            try:
                data = load_vault(master)
            except FileNotFoundError:
                flash(f"Вольт не найден: <code>{VAULT_PATH}</code>. Нажмите «Создать вольт (если отсутствует)».", "error")
                data = {"sites": {}}
            except Exception as exc:
                flash(f"Не удалось расшифровать {VAULT_PATH}: {exc}", "error")
                data = {"sites": {}}
            else:
                site_ok = bool(site_field.strip())
                login_ok = bool(login_field.strip())

                # --- создать запись ---
                if action == "add_entry":
                    if not (site_ok and login_ok):
                        flash("Укажите сайт и логин для создания записи.", "error")
                    else:
                        site_id = pwgen.normalize_site_id(site_field)
                        key = f"{site_id}|{login_field.strip()}"
                        if key in data["sites"]:
                            flash("Такая запись уже существует.", "info")
                        else:
                            if profile_field not in pwgen.PROFILES:
                                flash("Неизвестный профиль.", "error")
                            else:
                                entry = {
                                    "site_id": site_id,
                                    "login": login_field.strip(),
                                    "v": pwgen.ALGO_VERSION,
                                    "c": 0,
                                    "rseed": os.urandom(16).hex(),
                                    "policy": pwgen.PROFILES[profile_field],
                                    "created": pwgen.now_iso(),
                                    "notes": ""
                                }
                                data["sites"][key] = entry
                                try:
                                    save_vault(master, data)
                                    flash(f"Запись создана: <code>{site_id}</code> | <code>{login_field.strip()}</code> с профилем <b>{profile_field}</b>.", "success")
                                except Exception as exc:
                                    flash(f"Не удалось сохранить вольт: {exc}", "error")

                # --- ротация c+1 ---
                if action == "rotate_c":
                    if not (site_ok and login_ok):
                        flash("Укажите сайт и логин для ротации c.", "error")
                    else:
                        site_id = pwgen.normalize_site_id(site_field)
                        key = f"{site_id}|{login_field.strip()}"
                        entry = data["sites"].get(key)
                        if not entry:
                            flash("Такой пары сайт/логин нет в хранилище.", "error")
                        else:
                            entry["c"] = int(entry.get("c", 0)) + 1
                            entry["v"] = pwgen.ALGO_VERSION
                            try:
                                save_vault(master, data)
                                flash(f"Ротация выполнена: новый c={entry['c']}.", "success")
                            except Exception as exc:
                                flash(f"Не удалось сохранить вольт: {exc}", "error")

                # --- новый rseed ---
                if action == "rotate_rseed":
                    if not (site_ok and login_ok):
                        flash("Укажите сайт и логин для генерации нового rseed.", "error")
                    else:
                        site_id = pwgen.normalize_site_id(site_field)
                        key = f"{site_id}|{login_field.strip()}"
                        entry = data["sites"].get(key)
                        if not entry:
                            flash("Такой пары сайт/логин нет в хранилище.", "error")
                        else:
                            entry["rseed"] = os.urandom(16).hex()
                            entry["c"] = 0
                            entry["v"] = pwgen.ALGO_VERSION
                            try:
                                save_vault(master, data)
                                flash("Сгенерирован новый rseed и сброшен c=0.", "success")
                            except Exception as exc:
                                flash(f"Не удалось сохранить вольт: {exc}", "error")

                # --- генерация пароля ---
                if action == "generate":
                    if not (site_ok and login_ok):
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
                                        master, capsule, site_id, login_field.strip(),
                                        policy, version, int(entry.get("c", 0)),
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

                if action == "list":
                    flash("Список записей обновлён.", "info")

            entries = format_entries(data.get("sites", {}))

    context = {
        "password": password,
        "used_c": used_c,
        "version": version,
        "entries": entries,
        "site": site_field,
        "login": login_field,
        "length_override": length_field,
        "vault_path": str(VAULT_PATH),
        "profiles": list(pwgen.PROFILES.keys()),
        "profile": profile_field,
    }
    return render_template_string(HTML_TEMPLATE, **context)

if __name__ == "__main__":
    host = os.environ.get("PWGEN_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("PWGEN_WEB_PORT", "5000"))
    app.run(host=host, port=port, debug=False)
