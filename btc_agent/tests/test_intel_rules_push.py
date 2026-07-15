"""v1 情报层规则引擎 + 推送 离线单测。

规则引擎是纯函数,直接喂 dashboard dict 断言 Alert。推送 monkeypatch sink 的
网络出口/send,验证渲染与派发,不真发消息。
"""

from btc_agent.intel import push, rules
from btc_agent.intel.rules import Alert, evaluate


# ---------------- rules ----------------

def test_fng_extreme_fear_alert():
    alerts = evaluate({"fear_greed": {"value": 12, "classification": "Extreme Fear"}})
    codes = [a.code for a in alerts]
    assert "fng_extreme_fear" in codes


def test_fng_neutral_no_alert():
    alerts = evaluate({"fear_greed": {"value": 50, "classification": "Neutral"}})
    assert all(a.code not in ("fng_extreme_fear", "fng_extreme_greed") for a in alerts)


def test_funding_critical():
    alerts = evaluate({"derivatives": {"funding_rate": 0.0015}})
    crit = [a for a in alerts if a.code == "funding_extreme"]
    assert crit and crit[0].level == "critical"


def test_funding_warning():
    alerts = evaluate({"derivatives": {"funding_rate": 0.0006}})
    warn = [a for a in alerts if a.code == "funding_elevated"]
    assert warn and warn[0].level == "warning"


def test_rsi_and_price_move():
    alerts = evaluate({"rsi": 75, "price_move_pct": -12.0})
    codes = {a.code for a in alerts}
    assert "rsi_overbought" in codes
    assert "price_move_large" in codes


def test_missing_fields_skip_rules():
    # 空快照不该报任何告警,也不崩
    assert evaluate({}) == []


def test_alerts_sorted_by_severity():
    alerts = evaluate({
        "rsi": 75,                          # info
        "price_move_pct": -12.0,            # critical
        "fear_greed": {"value": 10},        # warning
    })
    levels = [a.level for a in alerts]
    assert levels == sorted(levels, key=lambda lv: rules.LEVELS.index(lv), reverse=True)
    assert levels[0] == "critical"


def test_threshold_override():
    # 收紧 F&G 极度贪婪阈值到 60,则 65 触发
    alerts = evaluate({"fear_greed": {"value": 65}}, {"fng_extreme_greed": 60})
    assert any(a.code == "fng_extreme_greed" for a in alerts)


# ---------------- push ----------------

def test_render_message_no_alerts():
    msg = push.render_message("BTC", "2026-07-15", [])
    assert "无触发规则的异常信号" in msg


def test_render_message_with_alerts():
    msg = push.render_message("BTC", "2026-07-15", [
        Alert("critical", "x", "剧烈波动"),
        Alert("info", "y", "超买"),
    ])
    assert "CRITICAL" in msg and "剧烈波动" in msg
    assert "INFO" in msg


def test_stdout_sink(capsys):
    push.StdoutSink().send("hello")
    assert "hello" in capsys.readouterr().out


def test_dispatch_counts_delivered():
    class _OK:
        name = "ok"
        def send(self, m): pass
    class _Bad:
        name = "bad"
        def send(self, m): raise RuntimeError("down")
    delivered = push.dispatch("m", [_OK(), _Bad(), _OK()])
    assert delivered == 2  # 坏 sink 不影响其它


def test_telegram_sink_no_env_degrades(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    sinks = push.build_sinks_from_config({"intel_push_sinks": ["stdout", "telegram"]})
    names = [getattr(s, "name", "") for s in sinks]
    assert "stdout" in names
    assert "telegram" not in names  # 缺 env → 降级跳过


def test_telegram_sink_sends(monkeypatch):
    sent = {}
    sink = push.TelegramSink(token="t", chat_id="c")
    monkeypatch.setattr(sink, "_send", lambda m: sent.setdefault("m", m))
    sink.send("hi")
    assert sent["m"] == "hi"


def test_feishu_sink_no_url_degrades(monkeypatch):
    monkeypatch.delenv("FEISHU_WEBHOOK_URL", raising=False)
    sinks = push.build_sinks_from_config({"intel_push_sinks": ["stdout", "feishu"]})
    names = [getattr(s, "name", "") for s in sinks]
    assert "stdout" in names
    assert "feishu" not in names  # 缺 webhook → 降级跳过


def test_feishu_sink_sends(monkeypatch):
    sent = {}
    sink = push.FeishuSink(webhook_url="https://open.feishu.cn/hook/x")
    monkeypatch.setattr(sink, "_send", lambda m: sent.setdefault("m", m))
    sink.send("*BTC 告警*")
    assert sent["m"] == "*BTC 告警*"


def test_feishu_sign_is_deterministic():
    # 同一 timestamp + secret 应得到稳定 base64 签名(飞书算法)
    sink = push.FeishuSink(webhook_url="https://x", secret="s3cret")
    sig1 = sink._sign(1_752_000_000)
    sig2 = sink._sign(1_752_000_000)
    assert sig1 == sig2 and isinstance(sig1, str) and len(sig1) > 0


def test_email_sink_no_creds_degrades(monkeypatch):
    for var in ("SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"):
        monkeypatch.delenv(var, raising=False)
    sinks = push.build_sinks_from_config({"intel_push_sinks": ["stdout", "email"]})
    names = [getattr(s, "name", "") for s in sinks]
    assert "stdout" in names
    assert "email" not in names  # 缺凭据 → 降级跳过


def test_email_build_message_subject_and_strip():
    sink = push.EmailSink(user="a@qq.com", password="code", to="b@qq.com")
    msg = sink._build_message("*BTC 盘面告警 2026-07-15*\n\n🔴 剧烈波动")
    assert msg["Subject"] == "BTC 盘面告警 2026-07-15"   # 首行、去 *
    assert msg["To"] == "b@qq.com"
    assert msg["From"] == "a@qq.com"                       # 未设 EMAIL_FROM → 回退 user
    assert "剧烈波动" in msg.get_content()


def test_email_sink_sends(monkeypatch):
    sent = {}
    sink = push.EmailSink(user="a@qq.com", password="code", to="b@qq.com")
    monkeypatch.setattr(sink, "_send", lambda m: sent.setdefault("m", m))
    sink.send("hi")
    assert sent["m"] == "hi"


def test_feishu_payload_strips_markdown_and_checks_code(monkeypatch):
    """验证:去 * 加粗、带 msg_type=text;body code!=0 时抛错。"""
    captured = {}

    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"code": 19021, "msg": "sign match fail"}

    def _fake_post(url, json, timeout):
        captured["payload"] = json
        return _Resp()

    monkeypatch.setattr(push.requests, "post", _fake_post)
    sink = push.FeishuSink(webhook_url="https://x")
    import pytest
    with pytest.raises(RuntimeError, match="19021"):
        sink.send("*hello*")
    assert captured["payload"]["msg_type"] == "text"
    assert captured["payload"]["content"]["text"] == "hello"  # * 已去掉
