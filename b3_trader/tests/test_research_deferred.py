import threading

from b3_trader import research_supervisor as research


def run_results(monkeypatch, results, *, disable_after_first=False):
    clock = [100.0]
    monkeypatch.setattr(research.time, 'time', lambda: clock[0])
    monkeypatch.setattr(research, '_log', lambda _: None)
    supervisor = research.ResearchSupervisor.__new__(research.ResearchSupervisor)
    supervisor.stop_event = threading.Event()
    state = research.ComponentState('market-ohlcv-history', True, 300, last_success_at=40)
    supervisor.states = {state.name:state}
    supervisor.force_run = {state.name:False}
    observed = []
    class Wake:
        def wait(self, seconds):
            assert seconds > 0
            clock[0] += seconds
            if disable_after_first: supervisor.stop_event.set()
        def clear(self): pass
    supervisor.wake_events = {state.name:Wake()}
    supervisor._safe_write_status = lambda: observed.append(state.to_dict())
    supervisor._close_component_resources = lambda _: None
    calls = []
    def runner():
        index = len(calls); calls.append(clock[0])
        if index == len(results)-1: supervisor.stop_event.set()
        if disable_after_first: state.enabled = False
        return results[index]
    supervisor._component_loop(state.name, runner)
    return state, calls, observed


def test_lock_deferral_is_not_success_and_retries_before_full_collection_interval(monkeypatch):
    deferred={'ok':True,'status':'deferred_forward_research_work_lock_busy','network_fetches':False}
    state, calls, seen = run_results(monkeypatch, [deferred, deferred, {'ok':True,'status':'collected','rows_written':12}])
    deferred_states = [row for row in seen if row['status']=='deferred']
    assert [row['last_success_at'] for row in deferred_states] == [40,40]
    assert calls == [100,105,115]
    assert state.last_success_at == 115 and state.deferred_runs == 2
    assert state.next_due_at == 415 and state.consecutive_deferrals == 0


def test_repeated_lock_probes_are_bounded_and_cancel_with_disabled_control(monkeypatch):
    deferred={'status':'deferred_forward_research_work_lock_busy'}
    state,calls,_=run_results(monkeypatch,[deferred]*5)
    assert calls == [100,105,115,135,155]
    assert state.last_success_at == 40 and state.deferred_runs == 5
    state,calls,_=run_results(monkeypatch,[deferred, {'ok':True}],disable_after_first=True)
    assert calls == [100] and state.status == 'stopped'


def test_explicit_failed_result_keeps_success_clock_and_normal_retry_interval(monkeypatch):
    state,calls,_=run_results(monkeypatch,[{'ok':False,'status':'collected','rows_written':0}])
    assert state.status == 'degraded' and state.last_success_at == 40
    assert state.next_due_at == 400 and calls == [100]
