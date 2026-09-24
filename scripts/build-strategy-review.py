"""Package the real-DB review UI without a checkout, dependency install or DB copy."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'cloudflare-pages/public'
PYTHON_FILES = (
    '__init__.py', 'paper_constants.py', 'strategy_journal_review.py',
    'strategy_lab_market.py', 'strategy_lab_context.py', 'strategy_lab_journal.py',
    'strategy_lab_plan.py', 'strategy_lab_rules.py',
    'event_reaction_view.py', 'event_response_contract.py', 'event_price_archive.py',
    'runtime_review.py', 'runtime_process_contract.py', 'holdings_review.py', 'user_tools.py',
)
LAUNCHER = r'''@echo off
setlocal
cd /d "%~dp0"
title CRYPTO @MODE@ @BUILD@
echo CRYPTO @MODE@ @BUILD@
echo Keep the collection window open. This is a separate read-only check.
set "CRYPTO_REVIEW_REPO=C:\Users\Administrator\Desktop\crypto-event-notifier-live"
set "CRYPTO_REVIEW_DB=%CRYPTO_REVIEW_REPO%\b3_trader\data\auto_demo.sqlite3"
if not "%~1"=="" set "CRYPTO_REVIEW_DB=%~1"
if not exist "%CRYPTO_REVIEW_DB%" (
  echo Existing database not found: %CRYPTO_REVIEW_DB%
  echo Pass the existing DB path as the first argument. No DB will be created.
  pause
  exit /b 1
)
if exist "%CRYPTO_REVIEW_REPO%\.venv\Scripts\python.exe" (
  "%CRYPTO_REVIEW_REPO%\.venv\Scripts\python.exe" -B -S -m b3_trader.strategy_journal_review --db "%CRYPTO_REVIEW_DB%" --report "%~dp0@REPORT@" @EXTRA@
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -B -S -m b3_trader.strategy_journal_review --db "%CRYPTO_REVIEW_DB%" --report "%~dp0@REPORT@" @EXTRA@
  ) else (
    python -B -S -m b3_trader.strategy_journal_review --db "%CRYPTO_REVIEW_DB%" --report "%~dp0@REPORT@" @EXTRA@
  )
)
set "CRYPTO_REVIEW_EXIT=%errorlevel%"
if not "%CRYPTO_REVIEW_EXIT%"=="0" (
  echo Check did not complete. The collection window is separate.
  pause
)
exit /b %CRYPTO_REVIEW_EXIT%
'''
README = '''가상매매 · 실전 계획 검토 화면

이번 실행본: @BUILD@
압축을 풀면 버전이 붙은 새 폴더가 나옵니다. 이전 폴더에 덮어쓰지 마세요.

수집 상태 점검: RUN_CHECK.cmd
수집 창을 열어 둔 채 RUN_CHECK.cmd를 두 번 클릭합니다.
약 30초 뒤 점검 창이 자동으로 닫히고, 같은 폴더에 CRYPTO_CHECK_RESULT.json이 저장됩니다.
기존 조회 화면이 열려 있어도 점검할 수 있습니다. 점검은 브라우저나 서버를 열지 않습니다.
수집 창은 계속 열어 둡니다. 수집 창을 닫으면 자동 누적이 중단됩니다.

코인별 화면 보기: RUN_REVIEW.cmd
브라우저가 열리면 빗썸 / B3 / 공격적 전략이 먼저 표시됩니다.
창을 30초 이상 열어 두면 CRYPTO_B3_REVIEW_RESULT.json에 전후 점검 결과도 저장됩니다.
조회 창을 닫으면 이 조회 화면만 종료됩니다.

Python 3.10 이상을 사용합니다. 기존 프로젝트의 Python 또는 PC의 Python을 자동으로 찾습니다.
별도 설치, Git 변경, 기존 수집기 재시작 없이 실행됩니다.
기본 DB: C:\\Users\\Administrator\\Desktop\\crypto-event-notifier-live\\b3_trader\\data\\auto_demo.sqlite3
주소: http://127.0.0.1:8766/
다른 DB 경로는 RUN_REVIEW.cmd "기존 SQLite 파일 경로"로 지정합니다.

확인할 흐름
코인 선택 → 전략 탭 → 독립 계좌 → 가격·체결 → 전체 체결 원장 → 현재 계획 → 계획으로 계산
BTC·ETH 탭은 동일 시각의 저장된 종가를 비교합니다.
이벤트 탭에서 발표를 선택하면 코인·BTC·ETH 반응을 같은 기간으로 비교합니다.
반응 계산 전 보존된 가격도 표시합니다. 기다리는 구간·미확보 가격·계산 대기를 구분합니다.
반응 수익률은 실제 저장이 끝난 값만 표시하며 조회 화면에서 만들어 채우지 않습니다.
과거 같은 이벤트의 반응과 실제 계산 가격·시각은 펼쳐서 확인합니다.
오래된 가격·계좌는 갱신 지연으로 표시합니다. 빈 기록을 0%로 바꾸지 않습니다.

계획으로 계산은 해당 가상계좌의 수량·평단·전략 조건을 불러옵니다.
매수·익절 회차와 수수료를 변경하면 예상 평단, 실현손익, 잔여 수량이 계산됩니다.
실제 주문이나 보유자산 변경은 발생하지 않습니다.

실제 DB는 읽기 전용으로 열립니다. DB·WAL·SHM 초기화나 교체를 하지 않습니다.
이 폴더에 CRYPTO_B3_REVIEW_RESULT.json이 저장됩니다.
이 파일에는 B3 공격적 전략의 실제 가상계좌·체결 원장과 대조 결과가 들어 있습니다.
두 결과 파일에는 점검본 버전, 시작·종료 시각, 계좌 조회 시각이 기록됩니다.
점검본 버전과 PC 수집 프로그램의 버전은 별개입니다.
30초 전에 Ctrl+C로 점검을 종료하면 완료 대신 중단으로 기록합니다.
창을 강제로 닫거나 PC를 종료한 경우, 미완료 기록이 남을 수 있습니다.
이벤트 검토 표본도 포함됩니다. B3에 반응이 없으면 BTC 표본을 별도로 명시합니다.
실행 중인 프로세스, 저장된 종료 코드, 최근 오류 종류, DB 갱신 시각의 전후 비교도 포함됩니다.
프로세스 조회 실패는 미확인으로 남깁니다. 기록 변화가 없다는 이유만으로 수집 실패라고 판정하지 않습니다.
현재 수집 창을 열어 둔 채 이 검토본을 함께 실행해도 됩니다. 기존 프로그램을 재시작하지 않습니다.
수집을 실제 수행했는지, 잠금 때문에 보류했는지, 이벤트 반응에 기준 가격이 없는지를 결과 파일에 구분해 담습니다.
전략 전체 집계 갱신과 실제 개별 계좌 갱신을 별도로 확인합니다.
원본 명령행·로그 본문·환경변수·인증정보는 결과 파일에 담지 않습니다.
파일은 자동 업로드되지 않습니다. 현재 사이트에도 배포되지 않습니다.

실전 계획 탭
기존 보유자산 DB(기본 crypto_trader.sqlite3)를 별도로 읽습니다.
프로젝트의 B3_JOURNAL_DB 설정이 있으면 해당 경로를 사용합니다.
보유 코인을 고르면 같은 거래소·원화 마켓의 전략별 성과와 원장을 연결합니다.
가상매매 수량·평단·1천만 원 예산을 실제 보유분에 넣지 않습니다.
분할 매수 총예산을 입력하고 전략 가격을 불러오면 내 수량·평단으로 계산합니다.
익절은 내 예상 평단에 전략의 익절 비율을 적용한 계산값입니다.
매수·익절 회차는 직접 조정할 수 있습니다. 합계 비중이 100%를 넘으면 계산을 막습니다.
기존 평단은 저장값을 사용하며 수수료는 새 매수·익절에만 적용합니다.
수수료 입력값은 기존 계산기의 가정입니다. 실제 적용 수수료에 맞게 변경하세요.
원화 외 마켓·미지정 거래소·미확보 가격을 다른 거래소나 원화 가격으로 채우지 않습니다.
수량 0인 매도 완료 기록은 DB에 그대로 남습니다. 보유정보 수정이나 주문은 하지 않습니다.
계산 입력은 조회 창이 열린 동안 유지되며, 페이지 새로고침·창 종료 시 저장되지 않습니다.
결과 파일의 holdings_review는 연결 상태와 건수만 담고 보유자산별 금액은 담지 않습니다.
보유 DB를 찾지 못하면 기존 설정을 확인하며 새 DB를 만들지 않습니다.
명시적 경로가 필요하면 Python 실행 인자 --holdings-db "기존 보유 DB 경로"를 사용할 수 있습니다.
실제 PC의 현재 누적과 화면 확인은 생성된 결과 및 실제 화면을 기준으로 판단합니다.
최대 하락폭은 저장된 계좌 수치이며 체결 원장만으로 재현했다고 표시하지 않습니다.
'''


def build(destination: Path) -> dict:
    if subprocess.check_output(['git','status','--porcelain','--untracked-files=no'], cwd=ROOT, text=True).strip():
        raise ValueError('Commit tracked changes before building a versioned review package.')
    head = subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()
    files = {Path('b3_trader') / name: (ROOT/'b3_trader'/name).read_bytes() for name in PYTHON_FILES}
    pending = [PUBLIC/'modules/pages/paper-workbench.js', PUBLIC/'modules/pages/holdings-workbench.js']
    seen = set()
    while pending:
        path = pending.pop().resolve()
        if path in seen:
            continue
        if PUBLIC not in path.parents or path.suffix != '.js':
            raise ValueError(f'Unexpected frontend dependency: {path}')
        seen.add(path)
        content = path.read_text(encoding='utf-8')
        files[path.relative_to(ROOT)] = content.encode('utf-8')
        for reference in re.findall(r"(?:from\s*|import\s*)['\"]([^'\"]+)['\"]", content):
            if not reference.startswith('.'):
                raise ValueError(f'Nonlocal dependency: {reference}')
            pending.append(path.parent/reference.split('?', 1)[0])
    for name in ('strategy-workbench.css','holdings-workbench.css'):
        css = Path('cloudflare-pages/public/modules/styles')/name
        files[css] = (ROOT/css).read_bytes()
    for name, mode, report, extra in (
            ('RUN_REVIEW.cmd', 'VIEWER', 'CRYPTO_B3_REVIEW_RESULT.json', '--open-browser'),
            ('RUN_CHECK.cmd', 'CHECK', 'CRYPTO_CHECK_RESULT.json', '--report-only')):
        launcher = LAUNCHER.replace('@BUILD@', head[:12]).replace('@MODE@', mode).replace('@REPORT@', report).replace('@EXTRA@', extra)
        files[Path(name)] = launcher.replace('\n', '\r\n').encode('ascii')
    files[Path('README.txt')] = README.replace('@BUILD@', head[:12]).encode('utf-8-sig')
    manifest = {'source_commit': head, 'mode': 'read_only', 'files': {
        path.as_posix(): hashlib.sha256(body).hexdigest() for path, body in sorted(files.items())}}
    files[Path('SOURCE_MANIFEST.json')] = json.dumps(manifest, indent=2).encode()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
        for path, body in sorted(files.items()):
            archive.writestr('CRYPTO_STRATEGY_REVIEW_'+head[:12]+'/'+path.as_posix(), body)
    return {'file': str(destination.resolve()), 'bytes': destination.stat().st_size,
            'files': len(files), 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
            'source_commit': head}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(build(parser.parse_args().output), indent=2))
