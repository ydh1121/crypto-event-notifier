from b3_trader.telegram_notify import TelegramNotifier


def test_safe_send_only_allows_buy_candidate_events(monkeypatch):
    notifier = TelegramNotifier("token", "chat", enabled=True)
    sent = []

    def fake_send(text, **kwargs):
        sent.append((text, kwargs))
        return True

    monkeypatch.setattr(notifier, "send", fake_send)

    assert notifier.safe_send("risk", event_key="action-KRW-B3-RISK_OFF") is False
    assert notifier.safe_send("wait", event_key="action-KRW-B3-WAIT_PULLBACK") is False
    assert notifier.safe_send("fill", event_key="fill-KRW-B3-123") is False
    assert notifier.safe_send("error", event_key="engine-error-RuntimeError") is False
    assert sent == []

    assert (
        notifier.safe_send(
            "buy",
            event_key="action-KRW-B3-BUY_CANDIDATE",
            min_interval_seconds=600,
        )
        is True
    )
    assert len(sent) == 1
    assert sent[0][0] == "buy"


def test_manual_send_path_is_not_filtered(monkeypatch):
    notifier = TelegramNotifier("token", "chat", enabled=True)

    class Response:
        ok = True
        status_code = 200

    calls = []

    def fake_post(url, data, timeout):
        calls.append((url, data, timeout))
        return Response()

    monkeypatch.setattr(notifier.session, "post", fake_post)
    assert notifier.send("연결 테스트") is True
    assert len(calls) == 1
