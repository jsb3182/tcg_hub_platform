"""Enroll a loopback administrator from a controlling Termux terminal."""
import base64
import getpass
import hmac
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
from urllib.parse import quote, urlencode
import warnings

import psycopg


class EnrollmentError(Exception):
    pass


def valid_step(key, code, now):
    if not re.fullmatch(r"[0-9]{6}", code):
        return None
    for step in range(int(now) // 30 - 1, int(now) // 30 + 2):
        if step < 0:
            continue
        mac = hmac.digest(key, step.to_bytes(8, "big"), "sha1")
        offset = mac[-1] & 15
        value = int.from_bytes(mac[offset:offset + 4], "big") & 0x7fffffff
        if hmac.compare_digest(f"{value % 1_000_000:06}", code):
            return step
    return None


def account(db, email):
    # Compare an opaque fingerprint across the human confirmation prompt. A concurrent
    # successful login advances last_step without changing this fingerprint.
    query = """
        SELECT a.id, encode(sha256(convert_to(f.secret_base32, 'UTF8')), 'hex')
          FROM app_user a LEFT JOIN local_admin_factor f ON f.user_id = a.id
         WHERE a.email = %s AND a.enabled AND a.role = 'ROLE_ADMIN'
    """
    row = db.execute(query, (email,)).fetchone()
    if row is None:
        raise EnrollmentError("사용 가능한 관리자 계정을 찾을 수 없습니다.")
    return row


def prompt_for_code(tty, email, secret):
    label = "TCG Hub:" + email
    uri = "otpauth://totp/" + quote(label, safe=":") + "?" + urlencode({
        "secret": secret, "issuer": "TCG Hub", "algorithm": "SHA1", "digits": 6, "period": 30,
    })
    # Termux supports the alternate screen. Keep setup data out of shell scrollback.
    tty.write("\x1b[?1049h\x1b[2J\x1b[H")
    try:
        tty.write(f"인증 앱에 시간 기반 키를 등록하세요.\n\n설정 키  {secret}\n\n{uri}\n\n")
        tty.flush()
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            return getpass.getpass("인증 앱의 6자리 코드 입력  ", stream=tty)
    finally:
        tty.write("\x1b[2J\x1b[?1049l")
        tty.flush()


def enroll(db, email, rotate, prompt):
    original = account(db, email)
    if original[1] is not None and not rotate:
        raise EnrollmentError("이미 등록된 인증 앱이 있습니다. 교체하려면 --rotate를 지정하세요.")
    if original[1] is None and rotate:
        raise EnrollmentError("교체할 인증 앱이 없습니다. --rotate 없이 먼저 등록하세요.")
    key = secrets.token_bytes(20)
    secret = base64.b32encode(key).decode("ascii")
    step = valid_step(key, prompt(email, secret), time.time())
    if step is None:
        raise EnrollmentError("코드를 확인할 수 없습니다. 기기의 자동 시각을 확인하고 다시 등록하세요.")
    with db.transaction():
        # A separate statement gives the subsequent read a fresh READ COMMITTED snapshot
        # even if we waited for another enrollment to release this account lock.
        db.execute("SELECT id FROM app_user WHERE id=%s FOR UPDATE", (original[0],))
        if account(db, email) != original:
            raise EnrollmentError("등록 중 계정이나 인증 앱이 변경되었습니다. 처음부터 다시 실행하세요.")
        if rotate:
            # The FK cascades to all previous local administrator sessions.
            db.execute("DELETE FROM local_admin_factor WHERE user_id=%s", (original[0],))
        db.execute("INSERT INTO local_admin_factor(user_id, secret_base32, last_step) VALUES (%s, %s, %s)",
                   (original[0], secret, step))


def app_password():
    # The installer writes this assignment as 64 hex digits into the app's private file.
    # Keep DB credentials and the TOTP key out of the enrollment process environment.
    with Path("/etc/tcg-hub/runtime.env").open(encoding="utf-8") as config:
        for line in config:
            match = re.fullmatch(r"export DB_PASSWORD=([0-9a-f]{64})\n?", line)
            if match:
                return match[1]
    raise EnrollmentError("앱 전용 DB 인증 설정을 읽을 수 없습니다.")


def setup(db, tty, read=input, change=subprocess.run):
    print("TCG 허브 관리자 설정", file=tty, flush=True)
    email = read("관리자 이메일: ").strip().lower()
    if not email or len(email) > 254:
        raise EnrollmentError("등록한 관리자 이메일을 입력하세요.")
    _, factor = account(db, email)
    print("1. 비밀번호 변경 후 인증 앱 확인\n2. 인증 앱만 확인", file=tty, flush=True)
    choice = read("진행할 번호 (1 또는 2): ").strip()
    if choice not in ("1", "2"):
        raise EnrollmentError("설정을 취소했습니다.")
    if choice == "1":
        print("현재 비밀번호, 새 비밀번호, 새 비밀번호 확인을 차례로 입력하세요. 입력한 글자는 숨겨집니다.", file=tty, flush=True)
        changed = change(["/bin/bash", "/opt/tcg-hub/current/deploy/ubuntu.sh", "password", email], check=False)
        if changed.returncode:
            raise EnrollmentError("비밀번호 변경을 완료하지 못했습니다. 현재 비밀번호를 확인하고 다시 실행하세요.")
    if factor is not None:
        print("기존 인증 앱이 등록돼 있습니다. 그 앱의 다음 코드로 로그인하세요.", file=tty, flush=True)
        return
    enroll(db, email, False, lambda address, secret: prompt_for_code(tty, address, secret))
    print("인증 앱 등록을 마쳤습니다. 다음 코드로 관리자 화면에 로그인하세요.", file=tty, flush=True)


def main(args):
    if len(args) not in (1, 2) or (len(args) == 2 and args[1] != "--rotate"):
        raise EnrollmentError("사용법: tcgctl totp EMAIL [--rotate]")
    if not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)):
        raise EnrollmentError("A90의 대화형 Termux 터미널에서 실행하세요.")
    with open("/dev/tty", "w", encoding="utf-8") as tty:
        with psycopg.connect(host="127.0.0.1", port=5432, dbname="tcg_hub", user="tcg_app",
                             password=app_password(), connect_timeout=5, autocommit=True) as db:
            if args == ["--setup"]:
                setup(db, tty)
                return
            enroll(db, args[0].strip().lower(), len(args) == 2,
                   lambda email, secret: prompt_for_code(tty, email, secret))
        tty.write("인증 앱 등록을 마쳤습니다. 다음 코드로 관리자 화면에 로그인하세요.\n")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except EnrollmentError as error:
        sys.exit(str(error))
    except (KeyboardInterrupt, EOFError, OSError, getpass.GetPassWarning):
        sys.exit("대화형 등록을 완료할 수 없습니다.")
    except psycopg.Error:
        # Database diagnostics can include the failing row; keep its factor secret out of logs.
        sys.exit("등록에 실패했습니다. DB 연결과 마이그레이션 상태를 확인하세요.")
