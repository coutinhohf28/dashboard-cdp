"""Autenticação do DI. Para cadastrar novas senhas: python di_auth.py."""

import hashlib
import hmac
import os
import secrets
from contextlib import closing
from getpass import getpass

import psycopg2

CONTAS = {
    "alice":    {"nome": "Alice Karine",    "setor": "MARKETING DIGITAL", "perfil": "operacional"},
    "daniel":   {"nome": "Daniel",          "setor": "MARKETING DIGITAL", "perfil": "operacional"},
    "imprensa": {"nome": "Michelle Phiffer","setor": "IMPRENSA",          "perfil": "operacional"},
    "projetos": {"nome": "Viviane Moura",   "setor": "PROJETOS",          "perfil": "operacional"},
    "fernanda": {"nome": "Fernanda Barbosa",  "setor": "APRENDIZ",          "perfil": "operacional"},
    "gerencia": {"nome": "Helder Coutinho", "setor": "GERÊNCIA",          "perfil": "gerencia"},
}

_ITERATIONS = 600_000


def _digest(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)


def _encode(password):
    salt = secrets.token_bytes(16)
    return salt.hex() + ":" + _digest(password, salt).hex()


def _matches(password, stored):
    salt, digest = stored.split(":")
    return hmac.compare_digest(_digest(password, bytes.fromhex(salt)), bytes.fromhex(digest))


def authenticate(url, login, password, new_password=None):
    if not url or login not in CONTAS or not password:
        return False
    with closing(psycopg2.connect(url, connect_timeout=5)) as conn, conn, conn.cursor() as cur:
        cur.execute("SELECT verifier FROM di_private.credentials WHERE login = %s", (login,))
        row = cur.fetchone()
        if not row or not _matches(password, row[0]):
            return False
        if new_password is not None:
            if len(new_password) < 12 or new_password == password:
                return False
            cur.execute(
                "UPDATE di_private.credentials SET verifier = %s WHERE login = %s AND verifier = %s",
                (_encode(new_password), login, row[0]),
            )
            return cur.rowcount == 1
        return True


def provision():
    url = os.environ.get("DATABASE_URL") or getpass("URL privada do PostgreSQL (entrada oculta): ")
    print("Defina uma senha nova e exclusiva para cada conta. As entradas ficam ocultas.")
    records = []
    for login in CONTAS:
        while True:
            password = getpass(f"Nova senha para {login} (mínimo 12 caracteres): ")
            if len(password) >= 12 and password == getpass("Confirmar: "):
                records.append((login, _encode(password)))
                break
            print("Confira o tamanho e a confirmação.")
    with closing(psycopg2.connect(url, connect_timeout=10)) as conn, conn, conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS di_private")
        cur.execute("CREATE TABLE IF NOT EXISTS di_private.credentials (login text PRIMARY KEY, verifier text NOT NULL)")
        cur.execute("REVOKE ALL ON di_private.credentials FROM PUBLIC, anon, authenticated")
        cur.execute("REVOKE ALL ON SCHEMA di_private FROM PUBLIC, anon, authenticated")
        cur.executemany(
            "INSERT INTO di_private.credentials (login, verifier) VALUES (%s, %s) "
            "ON CONFLICT (login) DO UPDATE SET verifier = EXCLUDED.verifier",
            records,
        )
    print("Credenciais configuradas.")


if __name__ == "__main__":
    provision()
