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
    /* ---------- БАЗА / ТЕМЫ ---------- */
    :root{
      --radius:14px;
      --glass: rgba(255,255,255,.08);
      --stroke: rgba(255,255,255,.18);
      --text: #0f172a;
      --muted:#64748b;
      --ok:#10b981; --warn:#f59e0b; --err:#ef4444; --info:#3b82f6;
      color-scheme: light dark;
      font-synthesis-weight:none;
    }
    @media (prefers-color-scheme:dark){
      :root{ --text:#e5e7eb; --muted:#94a3b8; }
    }
    *{box-sizing:border-box}
    html,body{height:100%}
    body{
      margin:0; font: 16px/1.45 system-ui, -apple-system, "Segoe UI", Roboto, "Inter", sans-serif;
      color:var(--text);
      display:grid; place-items:start center; padding:32px;
      background:#0b1220;
      position:relative; overflow-x:hidden;
    }
    /* Анимированный градиентный фон */
    body::before, body::after{
      content:""; position:fixed; inset:-20% -10% auto -10%; height:80%;
      background:
        radial-gradient(60% 60% at 20% 20%, #4f46e5aa 0%, transparent 60%),
        radial-gradient(50% 50% at 80% 30%, #06b6d4aa 0%, transparent 60%),
        radial-gradient(40% 40% at 30% 80%, #22c55e88 0%, transparent 60%);
      filter: blur(60px) saturate(120%);
      animation: float 24s linear infinite alternate;
      pointer-events:none; z-index:0; opacity:.6;
    }
    body::after{ inset:auto -10% -20% -10%; height:70%; transform:scaleX(-1); opacity:.55; }
    @keyframes float { from{transform:translateY(-2%) rotate(0deg)} to{transform:translateY(2%) rotate(2deg)} }

    /* ---------- КОНТЕЙНЕР ---------- */
    .wrap{
      width:min(980px, 100%);
      position:relative; z-index:1;
    }
    .card{
      background:var(--glass); backdrop-filter:saturate(140%) blur(18px);
      border:1px solid var(--stroke);
      border-radius:var(--radius);
      padding:22px;
      box-shadow: 0 10px 30px rgb(0 0 0 / 25%), inset 0 1px 0 rgba(255,255,255,.05);
    }
    h1{margin:0 0 8px; font-size:28px; letter-spacing: .2px;}
    .subtle{color:var(--muted); font-size:13px}

    /* ---------- ФОРМА ---------- */
    form{display:grid; gap:14px; grid-template-columns: 1fr 1fr; margin-top:16px}
    label{display:flex; flex-direction:column; gap:8px; font-weight:600; font-size:14px}
    input, select{
      font:inherit; padding:12px 14px; border-radius:12px; border:1px solid var(--stroke);
      background:rgba(255,255,255,.04); color:inherit; outline:none;
      transition: box-shadow .25s, border-color .25s, transform .06s;
    }
    input:focus, select:focus{ border-color:#7dd3fc88; box-shadow:0 0 0 6px #0ea5e910 }
    input:active{ transform:scale(.995) }

    /* ---------- КНОПКИ ---------- */
    .actions{grid-column: 1 / -1; display:flex; flex-wrap:wrap; gap:10px}
    .btn{
      position:relative; border:none; padding:12px 16px; border-radius:12px; cursor:pointer;
      color:#0b1220; background:#e2e8f0; font-weight:700; letter-spacing:.2px;
      transition: transform .08s ease, filter .2s ease, box-shadow .2s ease;
      box-shadow: 0 8px 16px rgba(0,0,0,.18);
      overflow:hidden; user-select:none;
    }
    .btn:hover{ filter:brightness(1.05) }
    .btn:active{ transform: translateY(1px) scale(.995) }
    .btn.primary{
      background:linear-gradient(135deg, #22d3ee, #818cf8);
      color:white; box-shadow: 0 10px 20px rgba(99,102,241,.35);
    }
    .btn.ghost{ background:transparent; color:var(--text); border:1px solid var(--stroke) }

    /* ripple */
    .btn .ink{ position:absolute; border-radius:999px; transform:scale(0); opacity:.4; background:#fff;
               animation:ripple .6s ease-out; pointer-events:none }
    @keyframes ripple{ to{ transform:scale(16); opacity:0 } }

    /* ---------- РЕЗУЛЬТАТ ---------- */
    .result{ margin:14px 0 18px; }
    .pwd-row{ display:flex; gap:10px; align-items:center }
    .pwd{ flex:1; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
          font-size:15px; padding:12px 14px; border-radius:12px; border:1px solid var(--stroke);
          background:rgba(255,255,255,.06) }
    .iconbtn{ min-width:44px; height:44px; border-radius:12px; border:1px solid var(--stroke);
              background:rgba(255,255,255,.06); color:inherit; cursor:pointer }
    .meta{ margin-top:6px; color:var(--muted); font-size:12px }

    /* ---------- ТОСТЫ (flash) ---------- */
    .toasts{ position:fixed; top:16px; right:16px; display:grid; gap:10px; z-index:10 }
    .toast{ padding:10px 12px; border-radius:12px; border:1px solid var(--stroke); backdrop-filter: blur(12px);
            animation: slidein .3s ease; box-shadow:0 10px 24px rgba(0,0,0,.25) }
    .toast.success{ background:#10b98120; color:#16a34a }
    .toast.error{ background:#ef444420; color:#ef4444 }
    .toast.warning{ background:#f59e0b20; color:#d97706 }
    .toast.info{ background:#3b82f620; color:#2563eb }
    @keyframes slidein{ from{transform:translateY(-10px); opacity:0} to{transform:none; opacity:1} }

    /* ---------- ТАБЛИЦА ---------- */
    table{width:100%; border-collapse:separate; border-spacing:0 10px; margin-top:10px}
    th{ text-align:left; font-size:12px; color:var(--muted); padding:0 10px }
    td{ background:rgba(255,255,255,.05); border:1px solid var(--stroke); padding:10px 12px }
    td:first-child{ border-radius:12px 0 0 12px }
    td:last-child{ border-radius:0 12px 12px 0 }

    .badge{ display:inline-flex; align-items:center; gap:6px; padding:4px 8px; border-radius:999px;
            font-size:12px; background:rgba(255,255,255,.06); border:1px solid var(--stroke) }

    .hint{ color:var(--muted); font-size:12px; margin-top:6px }
    .pill{ padding:.2rem .5rem; border-radius:999px; border:1px solid var(--stroke); background:rgba(255,255,255,.05) }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>pwgen web</h1>
      <div class="subtle">Хранилище: <span class="pill">{{ vault_path }}</span></div>

      <!-- тосты из flash -->
      <div class="toasts" id="toasts">
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
            <input id="pwd" class="pwd" type="password" value="{{ password }}" readonly spellcheck="false">
            <button class="iconbtn" id="toggle" title="Показать/скрыть">👁</button>
            <button class="iconbtn" id="copy"   title="Копировать">📋</button>
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
          <input type="text" name="site" value="{{ site }}" placeholder="example.com">
        </label>

        <label>
          Логин
          <input type="text" name="login" value="{{ login }}" placeholder="you@mail.com">
        </label>

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
        <table>
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
    // Кнопки: ripple-эффект
    for (const b of document.querySelectorAll('.btn')) {
      b.addEventListener('click', e => {
        const r = document.createElement('span');
        r.className = 'ink';
        const rect = b.getBoundingClientRect();
        const x = e.clientX - rect.left, y = e.clientY - rect.top;
        r.style.left = (x-10)+'px'; r.style.top = (y-10)+'px';
        r.style.width = r.style.height = Math.max(rect.width, rect.height)+'px';
        b.appendChild(r); setTimeout(()=>r.remove(), 600);
      }, {passive:true});
    }

    // Тосты: авто-схлопывание
    const toasts = document.getElementById('toasts');
    if (toasts) {
      for (const t of [...toasts.children]) {
        setTimeout(()=>{ t.style.transition='opacity .4s, transform .4s';
                         t.style.opacity='0'; t.style.transform='translateY(-6px)';
                         setTimeout(()=>t.remove(), 420); }, 4200);
      }
    }

    // Пароль: показать/скрыть и копировать
    const pwd = document.getElementById('pwd');
    const toggle = document.getElementById('toggle');
    const copy = document.getElementById('copy');
    if (pwd && toggle) toggle.onclick = () => { pwd.type = (pwd.type==='password'?'text':'password'); };
    if (pwd && copy) copy.onclick = async () => {
      pwd.select(); try { await navigator.clipboard.writeText(pwd.value); pulse(copy, '✔'); } catch(e){ pulse(copy,'⚠'); }
    };
    function pulse(btn, glyph){
      const old = btn.textContent; btn.textContent = glyph;
      btn.style.boxShadow='0 0 0 6px #10b98133'; setTimeout(()=>{ btn.style.boxShadow=''; btn.textContent=old; }, 900);
    }

    // Искры при наличии пароля
    if (pwd) sparkles(pwd.closest('.result'));
    function sparkles(host){
      const N=20; for(let i=0;i<N;i++){
        const s=document.createElement('span'); s.style.position='absolute';
        s.style.width=s.style.height=(6+Math.random()*6)+'px';
        s.style.background=['#22d3ee','#60a5fa','#34d399','#f472b6'][i%4];
        s.style.borderRadius='99px'; s.style.filter='blur(.2px)';
        const b=host.getBoundingClientRect();
        s.style.left=(b.width/2-8)+'px'; s.style.top='-10px';
        s.style.transform=`translate(${(Math.random()*2-1)*220}px, ${40+Math.random()*60}px)`;
        s.style.opacity='0'; s.style.transition='transform .9s cubic-bezier(.2,.7,.1,1), opacity .9s';
        host.style.position='relative'; host.appendChild(s);
        requestAnimationFrame(()=>{ s.style.opacity='.95'; s.style.transform=`translate(${(Math.random()*2-1)*220}px, ${120+Math.random()*80}px)`; });
        setTimeout(()=>s.remove(), 1000);
      }
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
