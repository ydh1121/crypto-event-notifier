import hashlib
import json
import sqlite3
import sys

import pytest

from b3_trader import runtime_review
from b3_trader import strategy_journal_review as review
from b3_trader.tests.test_strategy_lab_journal import fixture_db


def test_report_identifies_actual_package_and_rejects_mixed_versions(tmp_path):
    assert review.review_build(tmp_path)['integrity'] == 'unavailable'
    files = {}
    for name in ('strategy_journal_review.py', 'runtime_review.py'):
        path = tmp_path / 'b3_trader' / name
        path.parent.mkdir(exist_ok=True)
        path.write_text('version-one')
        files[path.relative_to(tmp_path).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {'source_commit': 'a' * 40, 'mode': 'read_only', 'files': files}
    (tmp_path / 'SOURCE_MANIFEST.json').write_text(json.dumps(manifest))
    assert review.review_build(tmp_path)['source_commit'] == 'a' * 40
    path.write_text('version-two')
    result = review.review_build(tmp_path)
    assert result['integrity'] == 'mismatch' and result['source_commit'] is None
    path.unlink()
    assert review.review_build(tmp_path)['integrity'] == 'mismatch'


def test_manifest_cannot_read_outside_package(tmp_path):
    (tmp_path / 'SOURCE_MANIFEST.json').write_text(json.dumps({
        'source_commit': 'a' * 40, 'mode': 'read_only', 'files': {
            '../private': 'ignored', 'b3_trader/strategy_journal_review.py': 'ignored',
            'b3_trader/runtime_review.py': 'ignored'}}))
    result = review.review_build(tmp_path)
    assert result['integrity'] == 'mismatch' and result['source_commit'] is None


def test_one_shot_reports_actual_account_without_socket_browser_or_db_write(tmp_path, monkeypatch):
    db = tmp_path / 'paper.db'
    fixture_db(db)
    with sqlite3.connect(db) as conn:
        for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            if 'market' in {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}:
                conn.execute(f'UPDATE "{table}" SET market=? WHERE market=?', ('KRW-B3', 'KRW-BTC'))
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    report = tmp_path / 'result.json'
    report.write_text('previous attachment')
    original_finish = review.finish_runtime_observation
    def observe_without_publishing(db_path, progress, value, seconds, stop):
        assert not report.exists()
        assert json.loads(progress.read_text())['runtime_review']['status'] == 'waiting_for_second_observation'
        previous = list((tmp_path/'reports/previous').glob('*.json'))
        assert len(previous) == 1 and previous[0].read_text() == 'previous attachment'
        original_finish(db_path, progress, value, seconds, stop)
    monkeypatch.setattr(review,'finish_runtime_observation',observe_without_publishing)
    monkeypatch.setattr(sys, 'argv', ['review', '--db', str(db), '--report', str(report),
                                     '--report-only', '--observe-seconds', '0'])
    monkeypatch.setattr(runtime_review, '_processes', lambda _: {'status': 'unsupported', 'items': []})
    def no_server(*args, **kwargs):
        raise AssertionError('One-shot review must not bind a server')
    monkeypatch.setattr(review, 'ThreadingHTTPServer', no_server)
    assert review.main() == 0
    result = json.loads(report.read_text())
    assert result['runtime_review']['status'] == 'complete'
    assert result['review_started_at'] <= result['account_observed_at'] <= result['review_finished_at']
    assert result['account']['reconciliation']['matches'] is True
    assert result['account']['journal']['total'] > 0
    assert result['review_build']['report_schema'] == 2
    assert 'strategy_lab_metrics' in result['runtime_review']['after']['activity']
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    assert list((tmp_path/'reports/in-progress').glob('*.json')) == []


@pytest.mark.parametrize('keyboard', [False, True])
def test_interruption_retains_first_observation_without_claiming_completion(tmp_path, keyboard):
    class Stop:
        def wait(self, _):
            if keyboard:
                raise KeyboardInterrupt
            return True
    report = {'runtime_review': {'before': {'activity': {'paper': {'latest': 10}}}}}
    path = tmp_path / 'result.json'
    review.finish_runtime_observation(tmp_path / 'absent.db', path, report, 30, Stop())
    saved = json.loads(path.read_text())
    assert saved['runtime_review']['status'] == 'interrupted'
    assert saved['runtime_review']['before'] == report['runtime_review']['before']
    assert 'after' not in saved['runtime_review']
    assert not (tmp_path / 'absent.db').exists()


def test_busy_viewer_port_does_not_overwrite_previous_report(tmp_path, monkeypatch):
    db = tmp_path / 'paper.db'
    db.touch()
    path = tmp_path / 'report.json'
    path.write_text('previous report')
    monkeypatch.setattr(sys, 'argv', ['review', '--db', str(db), '--report', str(path)])
    def busy(*args, **kwargs):
        raise OSError('port occupied')
    monkeypatch.setattr(review, 'ThreadingHTTPServer', busy)
    with pytest.raises(SystemExit):
        review.main()
    assert path.read_text() == 'previous report'


def test_event_market_coverage_is_counted_without_exporting_identifiers():
    result = runtime_review._result_evidence({'event_response_capture': {
        'markets_considered': 400, 'market_selection': 'observed_krw_markets',
        'markets': ['private-list'], 'missing_baseline': 4}})
    assert result['event_response_capture'] == {
        'markets_considered': 400, 'market_selection': 'observed_krw_markets', 'missing_baseline': 4}


def test_launcher_version_mismatch_stops_before_reading_db_or_replacing_report(tmp_path, monkeypatch):
    db = tmp_path/'paper.db';db.touch()
    report = tmp_path/'result.json';report.write_text('previous attachment')
    monkeypatch.setattr(sys,'argv',['review','--db',str(db),'--report',str(report),
        '--report-only','--expected-build','a'*40])
    monkeypatch.setattr(review,'review_build',lambda: {'integrity':'verified','source_commit':'b'*40})
    def no_read(*args,**kwargs): raise AssertionError('Mismatched launcher cannot reach database')
    monkeypatch.setattr(review,'read_detail',no_read)
    with pytest.raises(SystemExit): review.main()
    assert report.read_text() == 'previous attachment'


@pytest.mark.parametrize('state',['interrupted','read_failed','waiting_for_second_observation'])
def test_incomplete_check_cannot_be_published_as_attachment(tmp_path,state):
    from b3_trader.check_report_output import CheckReportOutput
    report=tmp_path/'CRYPTO_CHECK_RESULT.json';report.write_text('old')
    output=CheckReportOutput(report);output.prepare()
    review.write_report(output.progress,{'runtime_review':{'status':state},'review_finished_at':1})
    with pytest.raises(ValueError,match='not completed'): output.publish()
    assert not report.exists()
    assert output.progress.exists()
    assert next((tmp_path/'reports/previous').glob('*.json')).read_text()=='old'


def test_report_history_symlink_cannot_move_an_existing_attachment(tmp_path):
    from b3_trader.check_report_output import CheckReportOutput
    report=tmp_path/'result.json';report.write_text('keep')
    other=tmp_path/'other';other.mkdir()
    (tmp_path/'reports').symlink_to(other,target_is_directory=True)
    with pytest.raises(ValueError,match='symbolic'): CheckReportOutput(report).prepare()
    assert report.read_text()=='keep' and list(other.iterdir())==[]
