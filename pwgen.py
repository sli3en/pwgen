#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pwgen.py — детерминированный генератор криптостойких паролей с капсулой энтропии и локальным
зашифрованным хранилищем. Алгоритм: Argon2id -> HKDF -> ChaCha20 DRBG -> rejection sampling.

Команды:
  INIT ВОЛЬТА:      python pwgen.py init
  ДОБАВИТЬ САЙТ:    python pwgen.py add --site example.com --login you@mail.com [--profile strict]
  ПОЛУЧИТЬ ПАРОЛЬ:  python pwgen.py get --site example.com --login you@mail.com [--copy]
  РОТАЦИЯ:          python pwgen.py rotate --site example.com --login you@mail.com [--mode counter|rseed]
  СПИСОК САЙТОВ:    python pwgen.py list
  ПОКАЗАТЬ МЕТА:    python pwgen.py show --site example.com --login you@mail.com

По умолчанию хранилище: ~/.pwgen_vault.json
Python 3.10+
"""

import argparse, base64, json, os, sys, time, getpass, hmac, hashlib, secrets, binascii
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional, Iterable

# --- внешние библиотеки ---
from argon2.low_level import hash_secret_raw, Type as Argon2Type
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
except Exception:
    Cipher = None
    algorithms = None

# tldextract опционален
try:
    import tldextract
    _HAS_TLDEXTRACT = True
except Exception:
    _HAS_TLDEXTRACT = False

# pyperclip для --copy (необязательно)
try:
    import pyperclip
    _HAS_PYPERCLIP = True
except Exception:
    _HAS_PYPERCLIP = False

# --------------- УТИЛИТЫ ---------------

def b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode('ascii')

def b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s.encode('ascii'))

def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()

def sha512_256(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()[:32]

def hkdf_expand_sha512(prk: bytes, info: bytes, L: int) -> bytes:
    # Simplified HKDF-Expand for single-block outputs (L <= 64)
    digest_len = hashlib.sha512().digest_size
    if L > digest_len:
        raise ValueError("Requested HKDF length exceeds SHA-512 digest size")
    return hmac.new(prk, info + b"\x01", hashlib.sha512).digest()[:L]

def hkdf_extract_sha512(salt: bytes, ikm: bytes, L: int = 32) -> bytes:
    if not salt:
        salt = b"\x00" * hashlib.sha512().digest_size
    return hmac.new(salt, ikm, hashlib.sha512).digest()[:L]

def to_punycode(host: str) -> str:
    try:
        return host.encode('idna').decode('ascii').lower().strip('.')
    except Exception:
        return host.lower().strip('.')

def etld_plus_one(host: str) -> str:
    host = to_punycode(host)
    if _HAS_TLDEXTRACT:
        ext = tldextract.extract(host)
        if ext.domain and ext.suffix:
            return f"{ext.domain}.{ext.suffix}".lower()
        return host
    # Фоллбек: последние 2 ярлыка
    parts = host.split('.')
    if len(parts) >= 2:
        return ".".join(parts[-2:]).lower()
    return host

def normalize_site_id(site: str) -> str:
    # Принимает домен или URL, возвращает eTLD+1 (punycode)
    site = site.strip()
    if "://" in site:
        try:
            from urllib.parse import urlparse
            host = urlparse(site).hostname or site
        except Exception:
            host = site
    else:
        host = site
    return etld_plus_one(host)

# --------------- ПАРАМЕТРЫ ПО УМОЛЧАНИЮ ---------------

DEFAULT_VAULT = os.path.expanduser("~/.pwgen_vault.json")
DEFAULT_KDF_T = 3
DEFAULT_KDF_M = 131072  # KiB = 128 MiB
DEFAULT_KDF_P = 1
ALGO_VERSION = "sha512-v1"  # смените при миграциях

SUPPORTED_ALGO_VERSIONS = {ALGO_VERSION}

# Наборы символов
CLASSES = {
    "lower": "abcdefghijklmnopqrstuvwxyz",
    "upper": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "digits": "0123456789",
    "symbols": "!#$%&()*+,-./:;<=>?@[]^_{|}~",
}

PROFILES = {
    "strict": {"length": 24, "classes": ["lower","upper","digits","symbols"], "forbid": ['"', "'", '`', ' ']},
    "legacy": {"length": 16, "classes": ["lower","upper","digits"], "forbid": ['"', "'", '`', ' ']},
    "pin":    {"length": 10, "classes": ["digits"], "forbid": []},

    # Новый режим: практическая пост-квантовая стойкость (~≥128 бит после Гровера)
    "hard":   {"length": 40, "classes": ["lower","upper","digits","symbols"], "forbid": ['"', "'", '`', ' ']},

    # Ещё жёстче (с большим запасом); пригодится там, где нет ограничений длины
    "ultra":  {"length": 64, "classes": ["lower","upper","digits","symbols"], "forbid": ['"', "'", '`', ' ']},
}


# --------------- ВОЛЬТ: ШИФРОВАНИЕ ---------------

def kdf_argon2id(master: str, salt: bytes, t: int, m: int, p: int) -> bytes:
    return hash_secret_raw(secret=master.encode('utf-8'),
                           salt=salt, time_cost=t, memory_cost=m,
                           parallelism=p, hash_len=32, type=Argon2Type.ID)

def vault_encrypt(plaintext: bytes, master: str,
                  t: int, m: int, p: int) -> Dict[str, Any]:
    salt = os.urandom(16)
    key  = kdf_argon2id(master, salt, t, m, p)
    nonce = os.urandom(12)
    aead = ChaCha20Poly1305(key)
    ct = aead.encrypt(nonce, plaintext, b"pwgen|vault|v1")
    return {
        "version": "pwgen_vault_v1",
        "kdf": {"alg":"argon2id","t":t,"m":m,"p":p,"salt": b64e(salt)},
        "aead": {"alg":"chacha20poly1305","nonce": b64e(nonce)},
        "ciphertext": b64e(ct),
        "written_at": now_iso(),
    }

def vault_decrypt(blob: Dict[str, Any], master: str) -> bytes:
    if blob.get("version") != "pwgen_vault_v1":
        raise ValueError("Unsupported vault version")
    kdf = blob["kdf"]; aead = blob["aead"]
    salt = b64d(kdf["salt"])
    key  = kdf_argon2id(master, salt, int(kdf["t"]), int(kdf["m"]), int(kdf["p"]))
    nonce = b64d(aead["nonce"])
    ct    = b64d(blob["ciphertext"])
    a = ChaCha20Poly1305(key)
    return a.decrypt(nonce, ct, b"pwgen|vault|v1")

def vault_load(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def vault_save(path: str, blob: Dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(blob, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass

# --------------- СТРУКТУРА ПЛЕЙНТЕКСТА ---------------

def make_empty_plaintext(capsule_b64: str) -> Dict[str, Any]:
    return {
        "capsule": capsule_b64,   # base64(32 bytes)
        "sites": {},              # key: f"{site_id}|{login}"
        "created": now_iso(),
        "updated": now_iso(),
        "algo": {"version": ALGO_VERSION}
    }

def read_plaintext(vault_path: str, master: str) -> Dict[str, Any]:
    blob = vault_load(vault_path)
    pt = vault_decrypt(blob, master)
    return json.loads(pt.decode('utf-8'))

def write_plaintext(vault_path: str, master: str, data: Dict[str, Any],
                    t:int, m:int, p:int) -> None:
    data["updated"] = now_iso()
    blob = vault_encrypt(json.dumps(data, ensure_ascii=False, separators=(',',':')).encode('utf-8'),
                         master, t, m, p)
    vault_save(vault_path, blob)

# --------------- DRBG (ChaCha20 stream) ---------------

def chacha20_stream(key: bytes, nonce: bytes = b"\x00"*16) -> iter:
    """
    Поток байт на ChaCha20. Основной путь — algorithms.ChaCha20 (nonce=16B, mode=None).
    Фоллбек — ChaCha20-Poly1305 с УНИКАЛЬНЫМ 12B nonce на каждый блок (без повторного использования nonce).
    """
    if Cipher is not None and algorithms is not None:
        # cryptography: ChaCha20 с 16-байтным nonce, режим = None
        cipher = Cipher(algorithms.ChaCha20(key, nonce), mode=None)
        enc = cipher.encryptor()
        while True:
            block = enc.update(b"\x00" * 64)
            for b in block:
                yield b
    else:
        # Фоллбек: ChaCha20-Poly1305, меняем nonce на каждом блоке (12 байт)
        aead = ChaCha20Poly1305(key)
        counter = 0
        while True:
            n12 = nonce[:4] + counter.to_bytes(8, "big")  # 12-byte nonce
            ct = aead.encrypt(n12, b"\x00" * 64, b"pwgen|drbg")
            for b in ct:
                yield b
            counter += 1

def rand_below(byte_iter: Iterable[int], n: int) -> int:
    """Равномерное число из [0, n] включительно."""
    if n <= 0: return 0
    while True:
        # 32-битное значение
        b0 = next(byte_iter); b1 = next(byte_iter); b2 = next(byte_iter); b3 = next(byte_iter)
        val = (b0<<24)|(b1<<16)|(b2<<8)|b3
        limit = (1<<32) - ((1<<32) % (n+1))
        if val < limit:
            return val % (n+1)

def permute_list(items: list, key_for_perm: bytes) -> list:
    it = chacha20_stream(key_for_perm, nonce=b"\x00"*16)
    arr = list(items)
    for i in range(len(arr)-1, 0, -1):
        j = rand_below(it, i)
        arr[i], arr[j] = arr[j], arr[i]
    return arr

# --------------- ПОЛИТИКИ/АЛФАВИТ ---------------

def build_alphabet(policy: Dict[str, Any]) -> Tuple[list, list]:
    allow = []
    required_sets = []
    for cls in policy["classes"]:
        s = CLASSES[cls]
        allow += list(s)
        required_sets.append(set(s))
    for ch in policy.get("forbid", []):
        allow = [c for c in allow if c != ch]
    if not allow:
        raise ValueError("Пустой итоговый алфавит (проверьте forbid/classes)")
    return allow, required_sets

def satisfies_classes(pwd: str, required_sets: list) -> bool:
    S = set(pwd)
    for req in required_sets:
        if not (S & req): return False
    return True

# --------------- ГЕНЕРАЦИЯ ПАРОЛЯ ---------------

def gen_password(master: str, capsule: bytes, site_id: str, login: str,
                 policy: Dict[str,Any], v: str, c: int, rseed: bytes) -> str:
    if v not in SUPPORTED_ALGO_VERSIONS:
        raise ValueError(f"Unsupported password derivation version: {v}")
    # Контекст
    context = (f"pwgen|{v}|{site_id}|{login}|{json.dumps(policy,sort_keys=True)}"
               f"|c={c}|r={rseed.hex()}").encode('utf-8')

    base_salt = sha512_256(b"salt|" + context)
    prk = hash_secret_raw(secret=master.encode('utf-8'),
                          salt=base_salt, time_cost=DEFAULT_KDF_T,
                          memory_cost=DEFAULT_KDF_M, parallelism=DEFAULT_KDF_P,
                          hash_len=32, type=Argon2Type.ID)
    if capsule and len(capsule) >= 32:
        prk = hkdf_extract_sha512(salt=prk, ikm=capsule, L=32)

    Kpwd  = hkdf_expand_sha512(prk, b"password|" + context, 32)
    Kperm = hkdf_expand_sha512(prk, b"alphabet|" + context, 32)

    allow, required_sets = build_alphabet(policy)
    A = permute_list(allow, Kperm)

    L = int(policy["length"])
    it = chacha20_stream(Kpwd, nonce=b"\x00"*16)
    M = len(A)
    T = (256 // M) * M

    out = []
    while len(out) < L:
        b = next(it)
        if b < T:
            out.append(A[b % M])

    # Финальная перестановка позиций
    out = permute_list(out, Kpwd)
    return "".join(out)

def gen_password_with_retries(master: str, capsule: bytes, site_id: str, login: str,
                              policy: Dict[str,Any], v: str, c: int, rseed: bytes,
                              max_tries: int = 8) -> Tuple[str, int]:
    allow, required_sets = build_alphabet(policy)
    for i in range(max_tries):
        pwd = gen_password(master, capsule, site_id, login, policy, v, c+i, rseed)
        if satisfies_classes(pwd, required_sets):
            return pwd, (c+i)
    # крайне маловероятно, но если ни один не подошёл — вернём последний
    return pwd, (c + max_tries - 1)

# --------------- КАПСУЛА ЭНТРОПИИ ---------------

def make_capsule(extra_beacon: Optional[str] = None) -> bytes:
    osrng = os.urandom(64)
    jitter = int(time.time_ns()).to_bytes(8,'big') + os.getpid().to_bytes(4,'big', signed=False)
    ikm = osrng + jitter
    if extra_beacon:
        ikm += sha256(extra_beacon.encode('utf-8'))
    return hkdf_extract_sha512(salt=b"capsule|sha512-v1", ikm=ikm, L=32)

# --------------- CLI КОМАНДЫ ---------------

def cmd_init(args):
    vp = args.vault
    if os.path.exists(vp):
        print(f"Файл вольта уже существует: {vp}")
        sys.exit(1)
    print("Создание вольта...")
    master1 = getpass.getpass("Введите мастер-фразу: ")
    master2 = getpass.getpass("Повторите мастер-фразу: ")
    if master1 != master2 or not master1:
        print("Мастер-фразы не совпадают или пустые.")
        sys.exit(1)
    beacon = args.beacon or ""
    capsule = make_capsule(beacon)
    pt = make_empty_plaintext(b64e(capsule))
    blob = vault_encrypt(json.dumps(pt, ensure_ascii=False).encode('utf-8'),
                         master1, args.time_cost, args.mem_cost, args.parallel)
    vault_save(vp, blob)
    print(f"Готово. Вольт: {vp}")

def load_vault_pt(args) -> Tuple[Dict[str,Any], Dict[str,Any], str]:
    if not os.path.exists(args.vault):
        print(f"Вольт не найден: {args.vault}")
        sys.exit(1)
    master = getpass.getpass("Мастер-фраза: ")
    blob = vault_load(args.vault)
    pt = json.loads(vault_decrypt(blob, master).decode('utf-8'))
    return blob, pt, master

def cmd_add(args):
    blob, pt, master = load_vault_pt(args)
    site_id = normalize_site_id(args.site)
    login = args.login.strip()
    key = f"{site_id}|{login}"
    if key in pt["sites"]:
        print("Запись уже существует.")
        sys.exit(1)

    if args.profile:
        if args.profile not in PROFILES:
            print("Неизвестный профиль. Доступны:", ", ".join(PROFILES.keys()))
            sys.exit(1)
        policy = PROFILES[args.profile].copy()
    else:
        # Пользовательские параметры
        classes = [c.strip() for c in args.classes.split(",")] if args.classes else ["lower","upper","digits","symbols"]
        forbid = list(args.forbid) if args.forbid else ['"', "'", '`', ' ']
        policy = {"length": args.length, "classes": classes, "forbid": forbid}

    rseed = os.urandom(16)
    pt["sites"][key] = {
        "site_id": site_id,
        "login": login,
        "v": ALGO_VERSION,
        "c": 0,
        "rseed": rseed.hex(),
        "policy": policy,
        "created": now_iso(),
        "notes": args.notes or ""
    }
    write_plaintext(args.vault, master, pt,
                    blob["kdf"]["t"], blob["kdf"]["m"], blob["kdf"]["p"])
    print(f"Добавлено: {site_id} ({login})")

def cmd_get(args):
    blob, pt, master = load_vault_pt(args)
    capsule = b64d(pt["capsule"])
    site_id = normalize_site_id(args.site)
    login = args.login.strip()
    key = f"{site_id}|{login}"
    if key not in pt["sites"]:
        print("Запись не найдена. Сначала выполните add.")
        sys.exit(1)
    entry = pt["sites"][key]
    policy = entry["policy"]
    # локальная переопределяемая длина/классы (опционально)
    if args.length:
        policy = policy.copy()
        policy["length"] = args.length
    if args.classes:
        policy = policy.copy()
        policy["classes"] = [c.strip() for c in args.classes.split(",")]
    if args.forbid is not None:
        policy = policy.copy()
        policy["forbid"] = list(args.forbid)

    version = entry.get("v", ALGO_VERSION)
    try:
        pwd, used_c = gen_password_with_retries(
            master, capsule, site_id, login, policy, version,
            int(entry.get("c",0)), bytes.fromhex(entry["rseed"])
        )
    except ValueError as exc:
        print(str(exc))
        print("Rotate the entry to upgrade it to sha512-v1 before generating a password.")
        sys.exit(1)
    print(pwd)
    if _HAS_PYPERCLIP and args.copy:
        try:
            pyperclip.copy(pwd)
            print("(Пароль скопирован в буфер обмена)")
        except Exception:
            pass
    if used_c != entry.get("c",0):
        # Мы НЕ сохраняем увеличение c — генерация всегда детерминирована и повторит тот же used_c путь.
        print(f"(Внутренний счётчик для соответствия политике: c={used_c}, сохранённый c={entry.get('c',0)})")

def cmd_rotate(args):
    blob, pt, master = load_vault_pt(args)
    site_id = normalize_site_id(args.site)
    login = args.login.strip()
    key = f"{site_id}|{login}"
    if key not in pt["sites"]:
        print("Запись не найдена.")
        sys.exit(1)
    entry = pt["sites"][key]
    mode = args.mode
    if mode == "counter":
        entry["c"] = int(entry.get("c",0)) + 1
        print(f"Новый c: {entry['c']}")
    elif mode == "rseed":
        entry["rseed"] = os.urandom(16).hex()
        entry["c"] = 0
        print("Генерация нового rseed и сброс c=0 выполнены.")
    else:
        print("Неизвестный режим ротации.")
        sys.exit(1)
    entry["v"] = ALGO_VERSION
    pt["sites"][key] = entry
    write_plaintext(args.vault, master, pt,
                    blob["kdf"]["t"], blob["kdf"]["m"], blob["kdf"]["p"])

def cmd_list(args):
    _, pt, _ = load_vault_pt(args)
    sites = pt["sites"]
    if not sites:
        print("Пусто.")
        return
    for k, e in sorted(sites.items()):
        print(f"{e['site_id']}\t{e['login']}\tlen={e['policy']['length']}\tclasses={','.join(e['policy']['classes'])}\tc={e['c']}")

def cmd_show(args):
    _, pt, _ = load_vault_pt(args)
    site_id = normalize_site_id(args.site)
    login = args.login.strip()
    key = f"{site_id}|{login}"
    if key not in pt["sites"]:
        print("Запись не найдена.")
        sys.exit(1)
    e = pt["sites"][key]
    print(json.dumps(e, ensure_ascii=False, indent=2))

def cmd_capsule(args):
    _, pt, _ = load_vault_pt(args)
    print(pt["capsule"])

# --------------- АРГУМЕНТЫ CLI ---------------

def build_parser():
    p = argparse.ArgumentParser(description="Детерминированный генератор паролей с Argon2id+HKDF+ChaCha20 и зашифрованным вольтом.")
    p.add_argument("--vault", default=DEFAULT_VAULT, help=f"Путь к вольту (по умолчанию {DEFAULT_VAULT})")
    sub = p.add_subparsers(dest="cmd", required=True)
    # capsule
    sp = sub.add_parser("capsule", help="Показать капсулу (base64)")
    sp.set_defaults(func=cmd_capsule)
    # init
    sp = sub.add_parser("init", help="Создать новый вольт и капсулу энтропии")
    sp.add_argument("--beacon", default="", help="Доп. строка-маяк (опционально, будет смешана в капсулу)")
    sp.add_argument("--time-cost", type=int, default=DEFAULT_KDF_T)
    sp.add_argument("--mem-cost",  type=int, default=DEFAULT_KDF_M, help="KiB (например 131072 = 128MiB)")
    sp.add_argument("--parallel",  type=int, default=DEFAULT_KDF_P)
    sp.set_defaults(func=cmd_init)

    # add
    sp = sub.add_parser("add", help="Добавить сайт (первая генерация rseed, c=0)")
    sp.add_argument("--site", required=True, help="Домен или URL")
    sp.add_argument("--login", required=True, help="Логин/учётка на сайте")
    sp.add_argument("--profile", choices=list(PROFILES.keys()), help="Готовый профиль политики")
    sp.add_argument("--length", type=int, default=24)
    sp.add_argument("--classes", default="lower,upper,digits,symbols")
    sp.add_argument("--forbid", default=None, help="Строка символов для запрета (по умолчанию '\"'\\'`[пробел])")
    sp.add_argument("--notes", default="")
    sp.set_defaults(func=cmd_add)

    # get
    sp = sub.add_parser("get", help="Сгенерировать пароль для сайта/логина")
    sp.add_argument("--site", required=True)
    sp.add_argument("--login", required=True)
    sp.add_argument("--length", type=int, help="Переопределить длину для этой выдачи")
    sp.add_argument("--classes", help="Переопределить классы, напр. lower,upper,digits")
    sp.add_argument("--forbid", default=None, help="Переопределить запретные символы")
    sp.add_argument("--copy", action="store_true", help="Скопировать в буфер обмена")
    sp.set_defaults(func=cmd_get)

    # rotate
    sp = sub.add_parser("rotate", help="Ротация пароля: увеличить c или сгенерировать новый rseed")
    sp.add_argument("--site", required=True)
    sp.add_argument("--login", required=True)
    sp.add_argument("--mode", choices=["counter","rseed"], default="counter")
    sp.set_defaults(func=cmd_rotate)

    # list
    sp = sub.add_parser("list", help="Показать список сайтов")
    sp.set_defaults(func=cmd_list)

    # show
    sp = sub.add_parser("show", help="Показать подробные метаданные записи сайта")
    sp.add_argument("--site", required=True)
    sp.add_argument("--login", required=True)
    sp.set_defaults(func=cmd_show)

    return p

def main():
    parser = build_parser()
    args = parser.parse_args()
    # Нормализация forbid-строки в некоторых командах
    if hasattr(args, "forbid") and isinstance(args.forbid, str):
        # передаём как список символов
        args.forbid = list(args.forbid)
    args.func(args)

if __name__ == "__main__":
    main()
