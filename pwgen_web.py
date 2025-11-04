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
    /* =========================
       Доступная цветовая схема
       ========================= */
    :root{
      /* База */
      --bg:#0b0f1a;                /* глубже и темнее: лучше контраст */
      --surface:#0f1722;           /* карточки/поля */
      --glass: rgba(255,255,255,.06);
      --stroke: #253043;           /* чёткий бордер на тёмном фоне */
      --text:#e6eaf0;              /* основной текст */
      --muted:#b0bbcc;             /* вторичный текст */
      --muted-weak:#8a97ad;
      --ok:#10b981; --warn:#f59e0b; --err:#ef4444; --info:#38bdf8;

      /* Градиенты и кнопки */
      --g1:#22d3ee; --g2:#6366f1;  /* контраст с белым текстом AA */
      --btn-text:#0b1220;
      --radius:14px;
      --shadow: 0 10px 28px rgba(0,0,0,.35);

      /* Фокусы (видимые) */
      --ring:#38bdf8;
      --ring-outer: #38bdf82a;     /* мягкая подсветка вокруг */
    }
    *{box-sizing:border-box}
    html,body{height:100%}
    body{
      margin:0; padding:32px; display:grid; place-items:start center;
      background: var(--bg);
      color:var(--text);
      font: 16px/1.5 system-ui, -apple-system, "Segoe UI", Roboto, Inter, sans-serif;
      -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;
    }

    /* Анимированный фон — с уважением prefers-reduced-motion */
    .backdrop, .backdrop::after{
      content:""; position:fixed; inset:-20% -10% auto -10%; height:80%;
      background:
        radial-gradient(60% 60% at 18% 22%, #4758ff33 0%, transparent 60%),
        radial-gradient(48% 48% at 82% 28%, #00d3ff33 0%, transparent 62%),
        radial-gradient(38% 38% at 28% 84%, #10b9812e 0%, transparent 65%);
      filter: blur(70px) saturate(120%);
      pointer-events:none; z-index:0; opacity:.7;
      animation: backdropFloat 26s cubic-bezier(.2,.6,.1,1) infinite alternate;
    }
    .backdrop::after{ inset:auto -10% -22% -10%; height:72%; transform:scaleX(-1); opacity:.55; }
    @keyframes backdropFloat { from{transform:translateY(-2%) rotate(0deg)} to{transform:translateY(2%) rotate(2deg)} }
    @media (prefers-reduced-motion:reduce){ .backdrop, .backdrop::after{ animation:none } }

    .wrap{ width:min(980px,100%); position:relative; z-index:1 }
    .card{
      background: linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.02)) , var(--surface);
      border:1px solid var(--stroke);
      border-radius:var(--radius);
      box-shadow: var(--shadow), inset 0 1px 0 rgba(255,255,255,.05);
      padding:22px 22px 18px;
      transition: transform .3s cubic-bezier(.2,.6,.1,1), box-shadow .3s;
    }
    .card:hover{ transform:translateY(-1px); box-shadow: 0 16px 36px rgba(0,0,0,.45) }

    h1{margin:0 0 8px; font-size:28px; letter-spacing:.2px}
    .subtle{color:var(--muted); font-size:13px}

    /* ======= форма ======= */
    form{display:grid; gap:14px; grid-template-columns:1fr 1fr; margin-top:16px}
    label{display:flex; flex-direction:column; gap:8px; font-weight:600; font-size:14px}
    input, select{
      font:inherit; padding:12px 14px; border-radius:12px; outline:none;
      border:1px solid var(--stroke);
      background: #151e2b;        /* темнее для AA контраста */
      color:var(--text);
      transition: box-shadow .28s, border-color .28s, transform .06s;
    }
    input::placeholder{color:#9db0c6}   /* заметный placeholder */
    input:focus-visible, select:focus-visible{
      border-color:var(--ring);
      box-shadow: 0 0 0 2px var(--ring), 0 0 0 8px var(--ring-outer);
    }
    input:active{ transform:scale(.996) }

    /* ======= кнопки ======= */
    .actions{grid-column:1 / -1; display:flex; flex-wrap:wrap; gap:10px}
    .btn{
      position:relative; border:none; padding:12px 16px; border-radius:12px; cursor:pointer;
      color:var(--btn-text); background:#e6eef7; font-weight:700; letter-spacing:.2px;
      transition: transform .08s ease, filter .2s ease, box-shadow .25s ease;
      box-shadow: 0 8px 16px rgba(0,0,0,.22);
      user-select:none;
    }
    .btn:hover{ filter:brightness(1.06) }
    .btn:active{ transform: translateY(1px) scale(.995) }
    .btn:focus-visible{ outline:2px solid var(--ring); outline-offset:2px }
    .btn.primary{
      background:linear-gradient(135deg, var(--g1), var(--g2));
      color:white; text-shadow:0 1px 0 rgba(0,0,0,.35);
      box-shadow: 0 12px 24px rgba(99,102,241,.32);
    }
    .btn.ghost{ background:#141c28; color:var(--text); border:1px solid var(--stroke) }

    /* мягкий ripple — отключаем при reduced-motion */
    .btn .ink{ position:absolute; border-radius:999px; transform:scale(0); opacity:.35; background:#fff;
               animation:ripple .7s cubic-bezier(.2,.7,.1,1); pointer-events:none }
    @keyframes ripple{ to{ transform:scale(18); opacity:0 } }
    @media (prefers-reduced-motion:reduce){ .btn .ink{ display:none } }

    /* ======= результат ======= */
    .result{ margin:14px 0 18px; }
    .pwd-row{ display:flex; gap:10px; align-items:center }
    .pwd{
      flex:1; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size:15px; padding:12px 14px; border-radius:12px;
      border:1px solid var(--stroke); background:#121a25; color:var(--text);
    }
    .iconbtn{
      min-width:44px; height:44px; border-radius:12px; border:1px solid var(--stroke);
      background:#141c28; color:var(--text); cursor:pointer; transition: filter .2s, transform .08s;
    }
    .iconbtn:hover{ filter:brightness(1.07) }
    .iconbtn:active{ transform:translateY(1px) }
    .iconbtn:focus-visible{ outline:2px solid var(--ring); outline-offset:2px }
    .meta{ margin-top:6px; color:var(--muted-weak); font-size:12px }

    /* ======= тосты ======= */
    .toasts{ position:fixed; top:16px; right:16px; display:grid; gap:10px; z-index:10 }
    .toast{
      padding:10px 12px; border-radius:12px; border:1px solid var(--stroke);
      background:#101826; color:var(--text);
      box-shadow:var(--shadow); backdrop-filter: blur(10px);
      animation: slidein .35s cubic-bezier(.2,.7,.1,1);
    }
    .toast.success{ border-color:#0e5; box-shadow:0 10px 28px rgba(16,185,129,.25) }
    .toast.error  { border-color:#f55; box-shadow:0 10px 28px rgba(239,68,68,.25) }
    .toast.warning{ border-color:#fb0; box-shadow:0 10px 28px rgba(245,158,11,.25) }
    .toast.info   { border-color:#4cf; box-shadow:0 10px 28px rgba(56,189,248,.25) }
    @keyframes slidein{ from{transform:translateY(-8px); opacity:0} to{transform:none; opacity:1} }
    @media (prefers-reduced-motion:reduce){ .toast{ animation:none } }

    /* ======= таблица ======= */
    .hint{ color:var(--muted); font-size:12px; margin-top:6px }
    table{ width:100%; border-collapse:separate; border-spacing:0 10px; margin-top:10px }
    th{ text-align:left; font-size:12px; color:#c5d0e0; padding:0 10px }
    td{
      background:#0f1724; border:1px solid var(--stroke); padding:10px 12px;
      color:var(--text);
    }
    td:first-child{ border-radius:12px 0 0 12px }
    td:last-child { border-radius:0 12px 12px 0 }
    .badge{ display:inline-flex; align-items:center; gap:6px; padding:4px 8px; border-radius:999px;
            font-size:12px; background:#121a27; border:1px solid var(--stroke); color:#d9e3ef }

    .pill{ padding:.2rem .5rem; border-radius:999px; border:1px solid var(--stroke); background:#121a27; color:#d9e3ef }

    /* ======= доступность: фокус только для клавиатуры ======= */
    :focus{ outline:none }
    :focus-visible{ outline:2px solid var(--ring); outline-offset:2px }

  </style>
</head>
<body>
  <div class="backdrop" aria-hidden="true"></div>

  <div class="wrap">
    <div class="card" role="region" aria-label="Генератор паролей">
      <h1>pwgen web</h1>
      <div class="subtle">Хранилище: <span class="pill">{{ vault_path }}</span></div>

      <!-- тосты -->
      <div class="toasts" id="toasts" role="status" aria-live="polite">
        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, message in messages %}
              <div class="toast {{ category }}">{{ message|safe }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}
      </div>

      {% if password %}
        <div class="result">
          <div class="pwd-row">
            <input id="pwd" class="pwd" type="password" value="{{ password }}" readonly spellcheck="false" aria-label="Сгенерированный пароль">
            <button class="iconbtn" id="toggle" title="Показать/скрыть пароль" aria-label="Показать или скрыть пароль">👁</button>
            <button class="iconbtn" id="copy"   title="Копировать пароль" aria-label="Копировать пароль">📋</button>
          </div>
          <div class="meta">Версия алгоритма: <b>{{ version }}</b>, использован <code>c={{ used_c }}</code></div>
        </div>
      {% endif %}

      <form method="post" autocomplete="off">
        <label style="grid-column:1/-1">
          Мастер-пароль
          <input type="password" name="master" placeholder="Введите мастер-пароль" required autocomplete="current-password">
        </label>

        <label>
          Сайт / домен
          <input type="text" name="site" value="{{ site }}" placeholder="example.com" inputmode="url" autocomplete="url">
        </label>

        <label>
          Логин
          <input type="text" name="login" value="{{ login }}" placeholder="you@mail.com" autocomplete="username">
        </label>

        <label>
          Профиль (для создания записи)
          <select name="profile" aria-label="Профиль">
            {% for p in profiles %}
              <option value="{{ p }}" {% if profile==p %}selected{% endif %}>{{ p }}</option>
            {% endfor %}
          </select>
        </label>

        <label>
          Переопределить длину при генерации (опц.)
          <input type="number" min="4" max="128" name="length" value="{{ length_override }}">
        </label>

        <div class="actions">
          <button class="btn primary" type="submit" name="action" value="generate">Сгенерировать</button>
          <button class="btn" type="submit" name="action" value="add_entry">Создать запись (по профилю)</button>
          <button class="btn ghost" type="submit" name="action" value="rotate_c">Ротация c+1</button>
          <button class="btn ghost" type="submit" name="action" value="rotate_rseed">Новый rseed</button>
          <button class="btn ghost" type="submit" name="action" value="list">Обновить список</button>
          <button class="btn ghost" type="submit" name="action" value="init_vault">Создать вольт (если отсутствует)</button>
        </div>
      </form>

      {% if entries %}
        <div class="hint">Сайты в хранилище</div>
        <table role="table" aria-label="Сайты в хранилище">
          <thead>
            <tr>
              <th>Сайт</th><th>Логин</th><th>Длина</th><th>Классы</th><th>c</th><th>Версия</th>
            </tr>
          </thead>
          <tbody>
          {% for item in entries %}
            <tr>
              <td>{{ item.site_id }}</td>
              <td>{{ item.login }}</td>
              <td>{{ item.policy.length }}</td>
              <td>{{ ','.join(item.policy.classes) }}</td>
              <td><span class="badge">c={{ item.c }}</span></td>
              <td>{{ item.v }}</td>
            </tr>
          {% endfor %}
          </tbody>
        </table>
      {% endif %}
    </div>
  </div>

  <script>
    // Ripple (мягкий)
    for (const b of document.querySelectorAll('.btn')) {
      b.addEventListener('click', e => {
        if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        const r = document.createElement('span');
        r.className = 'ink';
        const rect = b.getBoundingClientRect();
        const x = e.clientX - rect.left, y = e.clientY - rect.top;
        r.style.left = (x-10)+'px'; r.style.top = (y-10)+'px';
        r.style.width = r.style.height = Math.max(rect.width, rect.height)+'px';
        b.appendChild(r); setTimeout(()=>r.remove(), 700);
      }, {passive:true});
    }

    // Тосты: авто-закрытие
    const toasts = document.getElementById('toasts');
    if (toasts) {
      for (const t of [...toasts.children]) {
        setTimeout(()=>{ t.style.transition='opacity .45s, transform .45s';
                         t.style.opacity='0'; t.style.transform='translateY(-6px)';
                         setTimeout(()=>t.remove(), 460); }, 4400);
      }
    }

    // Показать/скрыть и копировать
    const pwd = document.getElementById('pwd');
    const toggle = document.getElementById('toggle');
    const copy = document.getElementById('copy');
    if (pwd && toggle) toggle.onclick = () => { pwd.type = (pwd.type==='password'?'text':'password'); toggle.blur(); };
    if (pwd && copy) copy.onclick = async () => {
      pwd.select(); try { await navigator.clipboard.writeText(pwd.value); pulse(copy, '✔'); } catch(e){ pulse(copy,'⚠'); }
    };
    function pulse(btn, glyph){
      const old = btn.textContent; btn.textContent = glyph;
      btn.style.boxShadow='0 0 0 8px var(--ring-outer), 0 0 0 2px var(--ring)';
      setTimeout(()=>{ btn.style.boxShadow=''; btn.textContent=old; }, 900);
    }
  </script>
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
