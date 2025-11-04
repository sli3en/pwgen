#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pwgen_web.py — веб-интерфейс для детерминированного генератора паролей из pwgen.py
Функции:
  - Создание вольта (init) прямо из UI
  - Создание записи (site+login) по выбранному профилю
  - Генерация пароля, опциональное переопределение длины
  - Ротация (c+1) и новый rseed
  - Список записей
  - PWA: можно «установить как приложение» на телефон/ПК
  - Переключение темы (dark/light), плавные анимации, высокая контрастность

Переменные окружения для деплоя:
  PWGEN_WEB_SECRET   — Flask SECRET_KEY (опционально)
  PWGEN_VAULT_PATH   — путь к вольту, например /data/pwgen_vault.json

Зависимости: Flask, pwgen.py (лежит рядом/в PYTHONPATH), всё остальное в стандартной библиотеке.
"""

import json
import os
from pathlib import Path
from flask import Flask, flash, render_template_string, request, Response

import pwgen  # твой локальный модуль с логикой генерации/хранилища

# ---------------------------------- App config ----------------------------------

APP_NAME = "pwgen web"
APP_THEME_DARK = "#0b0f1a"
APP_THEME_LIGHT = "#f5f7fb"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("PWGEN_WEB_SECRET", os.urandom(16).hex())

VAULT_PATH = Path(os.environ.get("PWGEN_VAULT_PATH", pwgen.DEFAULT_VAULT)).expanduser()

# -------------------------------- HTML Template ---------------------------------

HTML_TEMPLATE = """<!doctype html>
<html lang="ru" data-theme="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>pwgen web</title>

  <!-- PWA -->
  <link rel="manifest" href="/manifest.webmanifest">
  <link rel="icon" href="/icon.svg" type="image/svg+xml">
  <meta id="theme-color" name="theme-color" content="#0b0f1a">

  <style>
    :root{
      --bg:#0b0f1a; --surface:#0f1722; --glass: rgba(255,255,255,.06);
      --stroke:#253043; --text:#e6eaf0; --muted:#b0bbcc; --muted-weak:#8a97ad;
      --ok:#10b981; --warn:#f59e0b; --err:#ef4444; --info:#38bdf8;
      --g1:#22d3ee; --g2:#6366f1; --btn-text:#0b1220;
      --radius:14px; --shadow:0 10px 28px rgba(0,0,0,.35);
      --ring:#38bdf8; --ring-outer:#38bdf82a;
    }
    html[data-theme="light"]{
      --bg:#f5f7fb; --surface:#ffffff; --glass: rgba(0,0,0,.03);
      --stroke:#d9e2ee; --text:#0e1524; --muted:#475569; --muted-weak:#64748b;
      --btn-text:#0b1220; --ring:#2563eb; --ring-outer:#2563eb22;
    }

    *{box-sizing:border-box}
    html,body{height:100%}
    body{
      margin:0; padding:32px; display:grid; place-items:start center;
      background:var(--bg); color:var(--text);
      font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Inter,sans-serif;
      -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;
      transition: background-color .35s ease, color .35s ease;
    }

    .backdrop,.backdrop::after{
      content:""; position:fixed; inset:-20% -10% auto -10%; height:80%;
      background:
        radial-gradient(60% 60% at 18% 22%, #4758ff33 0%, transparent 60%),
        radial-gradient(48% 48% at 82% 28%, #00d3ff33 0%, transparent 62%),
        radial-gradient(38% 38% at 28% 84%, #10b9812e 0%, transparent 65%);
      filter: blur(70px) saturate(120%); pointer-events:none; z-index:0; opacity:.7;
      animation: backdropFloat 26s cubic-bezier(.2,.6,.1,1) infinite alternate;
    }
    .backdrop::after{ inset:auto -10% -22% -10%; height:72%; transform:scaleX(-1); opacity:.55 }
    @keyframes backdropFloat { from{transform:translateY(-2%) rotate(0)} to{transform:translateY(2%) rotate(2deg)} }
    @media (prefers-reduced-motion:reduce){ .backdrop,.backdrop::after{ animation:none } }

    .wrap{ width:min(980px,100%); position:relative; z-index:1 }
    .card{
      background: linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.02)) , var(--surface);
      border:1px solid var(--stroke); border-radius:var(--radius);
      box-shadow: var(--shadow), inset 0 1px 0 rgba(255,255,255,.05);
      padding:22px 22px 18px;
      transition: transform .3s cubic-bezier(.2,.6,.1,1), box-shadow .3s, background-color .35s ease;
    }
    html[data-theme="light"] .card{ background:var(--surface) }
    .card:hover{ transform:translateY(-1px); box-shadow:0 16px 36px rgba(0,0,0,.18) }

    .toolbar{ display:flex; gap:8px; justify-content:flex-end; margin-bottom:6px }
    .iconbtn{
      min-width:40px; height:40px; border-radius:12px; border:1px solid var(--stroke);
      background:#141c28; color:var(--text); cursor:pointer; transition: filter .2s, transform .08s;
    }
    html[data-theme="light"] .iconbtn{ background:#f1f5f9 }
    .iconbtn:hover{ filter:brightness(1.07) }
    .iconbtn:active{ transform:translateY(1px) }
    .iconbtn:focus-visible{ outline:2px solid var(--ring); outline-offset:2px }

    h1{margin:4px 0 8px; font-size:28px; letter-spacing:.2px}
    .subtle{color:var(--muted); font-size:13px}

    form{display:grid; gap:14px; grid-template-columns:1fr 1fr; margin-top:16px}
    label{display:flex; flex-direction:column; gap:8px; font-weight:600; font-size:14px}
    input, select{
      font:inherit; padding:12px 14px; border-radius:12px; outline:none;
      border:1px solid var(--stroke); background:#151e2b; color:var(--text);
      transition: box-shadow .28s, border-color .28s, transform .06s, background-color .35s ease;
    }
    html[data-theme="light"] input, html[data-theme="light"] select{ background:#ffffff }
    input::placeholder{color:#9db0c6}
    html[data-theme="light"] input::placeholder{color:#64748b}
    input:focus-visible, select:focus-visible{ border-color:var(--ring); box-shadow:0 0 0 2px var(--ring), 0 0 0 8px var(--ring-outer) }
    input:active{ transform:scale(.996) }

    .actions{grid-column:1 / -1; display:flex; flex-wrap:wrap; gap:10px}
    .btn{
      position:relative; border:none; padding:12px 16px; border-radius:12px; cursor:pointer;
      color:var(--btn-text); background:#e6eef7; font-weight:700; letter-spacing:.2px;
      transition: transform .08s ease, filter .2s ease, box-shadow .25s ease, background-color .35s ease;
      box-shadow: 0 8px 16px rgba(0,0,0,.22); user-select:none;
    }
    html[data-theme="light"] .btn{ background:#e6eef7 }
    .btn:hover{ filter:brightness(1.06) }
    .btn:active{ transform: translateY(1px) scale(.995) }
    .btn:focus-visible{ outline:2px solid var(--ring); outline-offset:2px }
    .btn.primary{
      background:linear-gradient(135deg, var(--g1), var(--g2)); color:white; text-shadow:0 1px 0 rgba(0,0,0,.35);
      box-shadow: 0 12px 24px rgba(99,102,241,.32);
    }
    .btn.ghost{ background:#141c28; color:var(--text); border:1px solid var(--stroke) }
    html[data-theme="light"] .btn.ghost{ background:#f8fafc }

    .btn .ink{ position:absolute; border-radius:999px; transform:scale(0); opacity:.35; background:#fff;
               animation:ripple .7s cubic-bezier(.2,.7,.1,1); pointer-events:none }
    @keyframes ripple{ to{ transform:scale(18); opacity:0 } }
    @media (prefers-reduced-motion:reduce){ .btn .ink{ display:none } }

    .result{ margin:14px 0 18px }
    .pwd-row{ display:flex; gap:10px; align-items:center }
    .pwd{
      flex:1; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size:15px; padding:12px 14px; border-radius:12px;
      border:1px solid var(--stroke); background:#121a25; color:var(--text);
      transition: background-color .35s ease;
    }
    html[data-theme="light"] .pwd{ background:#ffffff }
    .meta{ margin-top:6px; color:var(--muted-weak); font-size:12px }

    .toasts{ position:fixed; top:16px; right:16px; display:grid; gap:10px; z-index:10 }
    .toast{
      padding:10px 12px; border-radius:12px; border:1px solid var(--stroke);
      background:#101826; color:var(--text);
      box-shadow:var(--shadow); backdrop-filter: blur(10px);
      animation: slidein .35s cubic-bezier(.2,.7,.1,1);
    }
    html[data-theme="light"] .toast{ background:#ffffff }
    .toast.success{ border-color:#0e5; box-shadow:0 10px 28px rgba(16,185,129,.18) }
    .toast.error  { border-color:#f55; box-shadow:0 10px 28px rgba(239,68,68,.18) }
    .toast.warning{ border-color:#fb0; box-shadow:0 10px 28px rgba(245,158,11,.18) }
    .toast.info   { border-color:#4cf; box-shadow:0 10px 28px rgba(56,189,248,.18) }
    @keyframes slidein{ from{transform:translateY(-8px); opacity:0} to{transform:none; opacity:1} }
    @media (prefers-reduced-motion:reduce){ .toast{ animation:none } }

    .hint{ color:var(--muted); font-size:12px; margin-top:6px }
    table{ width:100%; border-collapse:separate; border-spacing:0 10px; margin-top:10px }
    th{ text-align:left; font-size:12px; color:#c5d0e0; padding:0 10px }
    html[data-theme="light"] th{ color:#4b5563 }
    td{ background:#0f1724; border:1px solid var(--stroke); padding:10px 12px; color:var(--text) }
    html[data-theme="light"] td{ background:#f8fafc }
    td:first-child{ border-radius:12px 0 0 12px }
    td:last-child { border-radius:0 12px 12px 0 }

    .badge{ display:inline-flex; align-items:center; gap:6px; padding:4px 8px; border-radius:999px;
            font-size:12px; background:#121a27; border:1px solid var(--stroke); color:#d9e3ef }
    html[data-theme="light"] .badge{ background:#eef2f7; color:#0e1524 }

    .pill{ padding:.2rem .5rem; border-radius:999px; border:1px solid var(--stroke); background:#121a27; color:#d9e3ef }
    html[data-theme="light"] .pill{ background:#eef2f7; color:#0e1524 }

    :focus{ outline:none }
    :focus-visible{ outline:2px solid var(--ring); outline-offset:2px }
  </style>
</head>
<body>
  <div class="backdrop" aria-hidden="true"></div>

  <div class="wrap">
    <div class="card" role="region" aria-label="Генератор паролей">
      <div class="toolbar">
        <button class="iconbtn" id="installBtn" title="Установить как приложение" aria-label="Установить" hidden>⬇︎</button>
        <button class="iconbtn" id="themeBtn" title="Переключить тему" aria-label="Переключить тему">🌙</button>
      </div>

      <h1>pwgen web</h1>
      <div class="subtle">Хранилище: <span class="pill">{{ vault_path }}</span></div>

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
            <tr><th>Сайт</th><th>Логин</th><th>Длина</th><th>Классы</th><th>c</th><th>Версия</th></tr>
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
    for (const b of document.querySelectorAll('.btn')) {
      b.addEventListener('click', e => {
        if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
        const r=document.createElement('span'); r.className='ink';
        const rect=b.getBoundingClientRect(); const x=e.clientX-rect.left, y=e.clientY-rect.top;
        r.style.left=(x-10)+'px'; r.style.top=(y-10)+'px';
        r.style.width=r.style.height=Math.max(rect.width,rect.height)+'px';
        b.appendChild(r); setTimeout(()=>r.remove(),700);
      }, {passive:true});
    }

    const toasts=document.getElementById('toasts');
    if (toasts){ for (const t of [...toasts.children]) {
      setTimeout(()=>{ t.style.transition='opacity .45s, transform .45s';
        t.style.opacity='0'; t.style.transform='translateY(-6px)';
        setTimeout(()=>t.remove(),460); }, 4400); } }

    const THEME_KEY='pwgen_theme';
    const themeBtn=document.getElementById('themeBtn');
    const metaTheme=document.getElementById('theme-color');
    function applyTheme(t){
      document.documentElement.setAttribute('data-theme', t);
      metaTheme && metaTheme.setAttribute('content', t==='light' ? '{{ theme_light }}' : '{{ theme_dark }}');
      localStorage.setItem(THEME_KEY, t);
      themeBtn.textContent = t==='light' ? '🌞' : '🌙';
    }
    const saved = localStorage.getItem(THEME_KEY);
    const sysLight = matchMedia('(prefers-color-scheme: light)').matches ? 'light':'dark';
    applyTheme(saved || sysLight);
    themeBtn.onclick = () => applyTheme(document.documentElement.getAttribute('data-theme')==='light' ? 'dark' : 'light');

    if ('serviceWorker' in navigator){ navigator.serviceWorker.register('/sw.js'); }
    let deferredPrompt=null;
    const installBtn=document.getElementById('installBtn');
    window.addEventListener('beforeinstallprompt', (e)=>{ e.preventDefault(); deferredPrompt=e; installBtn.hidden=false; });
    installBtn?.addEventListener('click', async ()=>{
      if(!deferredPrompt) return;
      deferredPrompt.prompt();
      await deferredPrompt.userChoice; deferredPrompt=null; installBtn.hidden=true;
    });
  </script>
</body>
</html>
"""

# ------------------------------- Helper functions -------------------------------

def load_vault(master: str) -> dict:
    blob = pwgen.vault_load(str(VAULT_PATH))
    plaintext = pwgen.vault_decrypt(blob, master)
    return json.loads(plaintext.decode("utf-8"))

def load_blob_and_plaintext(master: str):
    """Вернёт (blob, pt) c исходными kdf-параметрами."""
    blob = pwgen.vault_load(str(VAULT_PATH))
    plaintext = pwgen.vault_decrypt(blob, master)
    return blob, json.loads(plaintext.decode("utf-8"))

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

# ------------------------------------ Routes -----------------------------------

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

    profiles = list(pwgen.PROFILES.keys())
    if profile_field not in profiles:
        profile_field = "ultra"

    vault_exists = VAULT_PATH.exists()

    if request.method == "POST":
        master = request.form.get("master", "")
        if not master:
            flash("Введите мастер-пароль.", "error")
        else:
            data = None
            blob = None
            if vault_exists:
                try:
                    blob, data = load_blob_and_plaintext(master)
                except Exception as exc:
                    flash(f"Не удалось расшифровать {VAULT_PATH}: {exc}", "error")

            if action == "init_vault":
                if vault_exists:
                    flash("Вольт уже существует.", "info")
                else:
                    try:
                        capsule = pwgen.make_capsule("")
                        pt = pwgen.make_empty_plaintext(pwgen.b64e(capsule))
                        blob_new = pwgen.vault_encrypt(
                            json.dumps(pt, ensure_ascii=False).encode("utf-8"),
                            master,
                            pwgen.DEFAULT_KDF_T,
                            pwgen.DEFAULT_KDF_M,
                            pwgen.DEFAULT_KDF_P,
                        )
                        pwgen.vault_save(str(VAULT_PATH), blob_new)
                        flash("Вольт создан.", "success")
                        vault_exists = True
                        blob, data = load_blob_and_plaintext(master)
                    except Exception as exc:
                        flash(f"Ошибка создания вольта: {exc}", "error")

            elif action == "add_entry":
                if not data:
                    flash("Сначала создайте вольт.", "error")
                else:
                    if not site_field or not login_field:
                        flash("Укажите сайт и логин для создания записи.", "error")
                    else:
                        site_id = pwgen.normalize_site_id(site_field)
                        key = f"{site_id}|{login_field.strip()}"
                        if key in data["sites"]:
                            flash("Запись уже существует.", "warning")
                        else:
                            policy = dict(pwgen.PROFILES[profile_field])
                            data["sites"][key] = {
                                "site_id": site_id,
                                "login": login_field.strip(),
                                "v": pwgen.ALGO_VERSION,
                                "c": 0,
                                "rseed": os.urandom(16).hex(),
                                "policy": policy,
                                "created": pwgen.now_iso(),
                                "notes": "",
                            }
                            try:
                                pwgen.write_plaintext(
                                    str(VAULT_PATH), master, data,
                                    blob["kdf"]["t"], blob["kdf"]["m"], blob["kdf"]["p"]
                                )
                                flash("Запись создана.", "success")
                            except Exception as exc:
                                flash(f"Ошибка сохранения: {exc}", "error")

            elif action in ("rotate_c", "rotate_rseed"):
                if not data:
                    flash("Сначала создайте вольт.", "error")
                else:
                    if not site_field or not login_field:
                        flash("Укажите сайт и логин для ротации.", "error")
                    else:
                        site_id = pwgen.normalize_site_id(site_field)
                        key = f"{site_id}|{login_field.strip()}"
                        entry = data["sites"].get(key)
                        if not entry:
                            flash("Такой пары сайт/логин нет в хранилище.", "error")
                        else:
                            if action == "rotate_c":
                                entry["c"] = int(entry.get("c", 0)) + 1
                                msg = f"Ротация выполнена: c={entry['c']}"
                            else:
                                entry["rseed"] = os.urandom(16).hex()
                                entry["c"] = 0
                                msg = "Сгенерирован новый rseed и сброшен c=0"
                            entry["v"] = pwgen.ALGO_VERSION
                            data["sites"][key] = entry
                            try:
                                pwgen.write_plaintext(
                                    str(VAULT_PATH), master, data,
                                    blob["kdf"]["t"], blob["kdf"]["m"], blob["kdf"]["p"]
                                )
                                flash(msg, "success")
                            except Exception as exc:
                                flash(f"Ошибка сохранения: {exc}", "error")

            elif action in ("generate", "list"):
                if not data:
                    flash("Сначала создайте вольт.", "error")
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
                                        if 4 <= override_len <= 128:
                                            policy = dict(policy); policy["length"] = override_len
                                        else:
                                            flash("Длина должна быть 4..128.", "error")
                                    except ValueError:
                                        flash("Длина должна быть целым числом.", "error")
                                capsule = pwgen.b64d(data["capsule"])
                                version = entry.get("v", pwgen.ALGO_VERSION)
                                try:
                                    password, used_c = pwgen.gen_password_with_retries(
                                        master, capsule, site_id, login_field.strip(),
                                        policy, version, int(entry.get("c", 0)),
                                        bytes.fromhex(entry["rseed"]),
                                    )
                                    flash("Пароль сгенерирован.", "success")
                                    if used_c != int(entry.get("c", 0)):
                                        flash(
                                            f"Для соответствия политике использован c={used_c} "
                                            f"(в хранилище c={entry.get('c', 0)}).", "info"
                                        )
                                except ValueError as exc:
                                    flash(str(exc), "error")

            if data:
                entries = format_entries(data["sites"])

    context = {
        "password": password,
        "used_c": used_c,
        "version": version,
        "entries": entries,
        "site": site_field,
        "login": login_field,
        "length_override": length_field,
        "vault_path": VAULT_PATH,
        "profiles": list(pwgen.PROFILES.keys()),
        "profile": profile_field,
        "theme_light": APP_THEME_LIGHT,
        "theme_dark": APP_THEME_DARK,
    }
    return render_template_string(HTML_TEMPLATE, **context)

# ----------------------------------- PWA stuff ----------------------------------

@app.route("/manifest.webmanifest")
def manifest_webmanifest():
    manifest = {
        "name": APP_NAME,
        "short_name": "pwgen",
        "start_url": "/",
        "display": "standalone",
        "background_color": APP_THEME_DARK,
        "theme_color": APP_THEME_DARK,
        "icons": [
            {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}
        ]
    }
    return Response(json.dumps(manifest), mimetype="application/manifest+json")


@app.route("/icon.svg")
def icon_svg():
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512">
      <defs>
        <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stop-color="#22d3ee"/><stop offset="100%" stop-color="#6366f1"/>
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="512" height="512" rx="96" fill="url(#g)"/>
      <g fill="white" font-family="Inter, system-ui, sans-serif" font-weight="800" font-size="220">
        <text x="86" y="300">pw</text>
      </g>
    </svg>'''
    return Response(svg, mimetype="image/svg+xml")


@app.route("/sw.js")
def service_worker():
    js = """const CACHE='pwgen-shell-v3';
self.addEventListener('install',e=>{
  e.waitUntil(caches.open(CACHE).then(c=>c.addAll(['/','/manifest.webmanifest','/icon.svg'])));
});
self.addEventListener('activate',e=>{
  e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener('fetch',e=>{
  if(e.request.method!=='GET') return;
  if(e.request.mode==='navigate'){
    e.respondWith(fetch(e.request).then(r=>{
      const cr=r.clone(); caches.open(CACHE).then(c=>c.put('/',cr)); return r;
    }).catch(()=>caches.match('/')));
    return;
  }
  e.respondWith(caches.match(e.request).then(m=> m || fetch(e.request)));
});"""
    return Response(js, mimetype="application/javascript", headers={"Cache-Control":"no-cache"})

# ------------------------------------ Main --------------------------------------

if __name__ == "__main__":
    host = os.environ.get("PWGEN_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("PWGEN_WEB_PORT", os.environ.get("PORT", "5000")))
    app.run(host=host, port=port, debug=False)
