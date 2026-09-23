"""Package a separate, user-started collector recovery; never replace RO review."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("review_builder", ROOT / "scripts/build-strategy-review.py")
review_builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review_builder)

LAUNCHER = r'''@echo off
setlocal
cd /d "%~dp0"
set "CRYPTO_RECOVERY_REPO=C:\Users\Administrator\Desktop\crypto-event-notifier-live"
if not "%~1"=="" set "CRYPTO_RECOVERY_REPO=%~1"
if not exist "%CRYPTO_RECOVERY_REPO%\.venv\Scripts\python.exe" (
  echo Existing project Python not found. No installation or database change was made.
  pause
  exit /b 2
)
"%CRYPTO_RECOVERY_REPO%\.venv\Scripts\python.exe" -B -S -m b3_trader.paper_recovery --repo "%CRYPTO_RECOVERY_REPO%"
set "CRYPTO_RECOVERY_EXIT=%ERRORLEVEL%"
echo Recovery session ended. Result: CRYPTO_RECOVERY_RESULT.json
pause
exit /b %CRYPTO_RECOVERY_EXIT%
'''

README = '''가상매매·데이터 수집 복구 실행본

1. 기존 프로젝트 폴더 밖(예: 다운로드 폴더)에 압축을 풉니다.
2. RUN_RECOVERY.cmd를 두 번 클릭합니다.
3. DB 백업이 검증되면 기존 가상매매와 시세·뉴스·이벤트 수집이 시작됩니다.
4. 시작 약 1분 후 같은 폴더에 CRYPTO_RECOVERY_RESULT.json이 저장되고 이후 매분 갱신됩니다.
   결과 파일을 이 채팅에 첨부하고, 수집하는 동안 실행 창을 열어 둡니다.
   종료는 Ctrl+C입니다. 기존 RUN_REVIEW.cmd로 새 화면을 함께 조회할 수 있습니다.

이 실행본은 조회 전용이 아닙니다. 시작 이후 기존 수집기가 기존 DB에 데이터를 쌓습니다.
실행 전 기존 프로그램이 살아 있거나, 실행 상태를 확인할 수 없거나,
미저장 코드·필수 라이브러리 누락·백업 실패가 있으면 수집을 시작하지 않습니다.
기존 프로그램을 강제 종료하거나 파일을 삭제하지 않습니다.

DB: C:\\Users\\Administrator\\Desktop\\crypto-event-notifier-live\\b3_trader\\data\\auto_demo.sqlite3
백업: 같은 프로젝트의 b3_trader\\data\\recovery-backups\\날짜-식별자\\auto_demo.sqlite3
현재 DB 약 3.1GB 기준 최소 약 3.7GB의 빈 공간이 필요합니다.
SQLite 백업 기능으로 WAL에 남은 기록까지 복사한 뒤 무결성과 계좌·체결 건수를 대조합니다.

소스는 기존 Git 인증으로 지정된 구현 커밋을 가져옵니다. 별도 로그인·라이브러리 설치는 하지 않습니다.
로컬에 recovery/paper-... 브랜치를 만들고 그 소스를 실행합니다.
종료 후에도 이 로컬 브랜치는 유지됩니다. 기존 주 브랜치·원격 브랜치는 변경하지 않습니다.
미저장 변경이 있거나 로컬 코드가 더 새로우면 적용하지 않습니다.

빗썸·업비트 가상매매, 시장 체결, OHLCV, 공식 이벤트, 기존 전략 연구를 실행합니다.
기존 설정에서 꺼 둔 수집 항목은 강제로 켜지 않습니다.
실제 주문·실제 보유정보 변경·텔레그램 발송·사이트 배포·외부 데이터 게시·자동 Git 동기화는 실행하지 않습니다.
DB 초기화·초기 데이터 주입·파괴적 마이그레이션·전략 계산식 변경은 없습니다.
기존 수집기의 데이터 보존 기간과 실행 규칙은 유지됩니다.

복구 성공은 창이 열렸다는 사실로 판단하지 않습니다.
결과 파일에서 실제 프로세스, 두 시점의 DB 갱신, B3 공격적 전략 계좌·원장 대조를 확인합니다.
시장 체결 갱신 표본은 거래소별 BTC·ETH입니다. 전체 코인 갱신으로 표시하지 않습니다.
뉴스나 1일 이벤트 반응은 새 표본/시간이 필요하므로 1분 동안 변화가 없어도 실패라고 단정하지 않습니다.
현재 Windows에서의 실행·수집 증가 확인은 이 실행 결과로 검증해야 합니다.
결과와 백업은 PC에만 저장되며 자동 업로드되지 않습니다.
'''


def build(destination: Path):
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        raise ValueError("Commit the exact source before packaging recovery")
    names = (*review_builder.PYTHON_FILES, "local_process_host.py", "research_work_lock.py", "paper_recovery.py")
    files = {"b3_trader/" + name: (ROOT / "b3_trader" / name).read_bytes() for name in names}
    files["RUN_RECOVERY.cmd"] = LAUNCHER.replace("\n", "\r\n").encode("ascii")
    files["README.txt"] = README.encode("utf-8-sig")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    manifest = {"source_commit": head, "mode": "collection_recovery", "files": {
        name: hashlib.sha256(body).hexdigest() for name, body in sorted(files.items())}}
    files["SOURCE_MANIFEST.json"] = json.dumps(manifest, indent=2).encode()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for name, body in sorted(files.items()):
            archive.writestr("CRYPTO_PAPER_RECOVERY/" + name, body)
    return {"file": str(destination.resolve()), "bytes": destination.stat().st_size,
            "files": len(files), "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(), "source_commit": head}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(build(parser.parse_args().output), indent=2))
