"""v1 情报层端到端(离线)单测:装配 → 规则 → 推送,全程 mock 网络。"""

from btc_agent.intel import dashboard as dash_mod
from btc_agent.intel import run_intel


def test_run_intel_end_to_end(monkeypatch, capsys):
    # mock 仪表盘装配,避免任何网络
    fake_dashboard = {
        "asset": "BTC",
        "curr_date": "2026-07-15",
        "fear_greed": {"value": 10, "classification": "Extreme Fear"},
        "derivatives": {"funding_rate": 0.0015, "open_interest": 5e9},
        "rsi": 28.0,
        "price_move_pct": -11.0,
        "close": 64000.0,
        "errors": {},
    }
    monkeypatch.setattr(run_intel, "build_dashboard", lambda asset, curr_date: fake_dashboard)

    result = run_intel.run_intel(asset="BTC", curr_date="2026-07-15",
                                 config={"intel_push_sinks": ["stdout"]})

    codes = {a.code for a in result["alerts"]}
    assert "funding_extreme" in codes       # critical
    assert "price_move_large" in codes       # critical
    assert "fng_extreme_fear" in codes       # warning
    assert "rsi_oversold" in codes           # info
    assert result["delivered"] == 1          # stdout sink
    assert result["delivery_complete"] is True
    # 消息经 stdout sink 打印
    assert "BTC 盘面告警" in capsys.readouterr().out


def test_run_intel_degrades_on_vendor_failure(monkeypatch):
    """所有信号取数失败时必须交白卷，不能把未知推送成"无异常"。"""
    monkeypatch.setattr(dash_mod, "get_fear_greed_value", None, raising=False)

    def _empty_dashboard(asset, curr_date):
        return {
            "asset": asset, "curr_date": curr_date,
            "fear_greed": None, "derivatives": None, "rsi": None,
            "price_move_pct": None, "close": None,
            "errors": {"fear_greed": "boom", "derivatives": "boom", "price": "boom"},
        }
    monkeypatch.setattr(run_intel, "build_dashboard", _empty_dashboard)

    result = run_intel.run_intel(asset="BTC", curr_date="2026-07-15",
                                 config={"intel_push_sinks": ["stdout"]})
    assert result["alerts"] == []
    assert "不能判定盘面正常" in result["message"]
    assert "无触发规则的异常信号" not in result["message"]
    assert "fear_greed" in result["message"]


def test_missing_configured_sink_marks_delivery_incomplete(monkeypatch):
    for var in ("SMTP_USER", "SMTP_PASSWORD", "EMAIL_TO"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(
        run_intel,
        "build_dashboard",
        lambda asset, curr_date: {
            "asset": asset,
            "curr_date": curr_date,
            "fear_greed": None,
            "derivatives": None,
            "rsi": None,
            "price_move_pct": None,
            "close": None,
            "errors": {"price": "offline"},
        },
    )
    result = run_intel.run_intel(
        config={"intel_push_sinks": ["stdout", "email"]}, curr_date="2026-07-15"
    )
    assert result["delivered"] == 1
    assert result["active_sinks"] == ["stdout"]
    assert result["delivery_complete"] is False


def test_cli_returns_nonzero_when_delivery_is_incomplete(monkeypatch):
    monkeypatch.setattr(
        run_intel,
        "run_intel",
        lambda **kwargs: {
            "dashboard": {"errors": {}},
            "alerts": [],
            "delivered": 1,
            "requested_sinks": ["stdout", "email"],
            "active_sinks": ["stdout"],
            "delivery_complete": False,
        },
    )
    assert run_intel.main([]) == 1


def _healthy_quiet_dashboard(asset, curr_date):
    """无告警且数据健康的仪表盘(所有信号取到但都不触发规则)。"""
    return {
        "asset": asset, "curr_date": curr_date,
        "fear_greed": {"value": 50, "classification": "Neutral"},
        "derivatives": {"funding_rate": 0.00001, "open_interest": 1e9},
        "rsi": 55.0,
        "price_move_pct": 0.5,
        "close": 64000.0,
        "errors": {},
    }


def test_alerts_only_skips_push_when_quiet(monkeypatch, capsys):
    """--alerts-only:无告警且无取数错误 → 跳过推送,送达按完整计(退出码 0 语义)。"""
    monkeypatch.setattr(run_intel, "build_dashboard", _healthy_quiet_dashboard)
    result = run_intel.run_intel(
        asset="BTC", curr_date="2026-07-15",
        config={"intel_push_sinks": ["stdout"]}, alerts_only=True,
    )
    assert result["alerts"] == []
    assert result["skipped_no_alerts"] is True
    assert result["delivery_complete"] is True
    assert result["active_sinks"] == []
    # stdout sink 未被调用 → 无消息输出
    assert "盘面告警" not in capsys.readouterr().out


def test_alerts_only_still_pushes_on_alerts(monkeypatch, capsys):
    """--alerts-only:有告警照常推送。"""
    def _alerting(asset, curr_date):
        d = _healthy_quiet_dashboard(asset, curr_date)
        d["fear_greed"] = {"value": 5, "classification": "Extreme Fear"}
        return d
    monkeypatch.setattr(run_intel, "build_dashboard", _alerting)
    result = run_intel.run_intel(
        asset="BTC", curr_date="2026-07-15",
        config={"intel_push_sinks": ["stdout"]}, alerts_only=True,
    )
    assert result["skipped_no_alerts"] is False
    assert len(result["alerts"]) >= 1
    assert "盘面告警" in capsys.readouterr().out


def test_alerts_only_still_pushes_on_data_errors(monkeypatch, capsys):
    """--alerts-only:无告警但取数失败 → 白卷消息必须照常推出去,绝不静默。"""
    def _broken(asset, curr_date):
        d = _healthy_quiet_dashboard(asset, curr_date)
        d["fear_greed"] = None
        d["errors"] = {"fear_greed": "boom"}
        return d
    monkeypatch.setattr(run_intel, "build_dashboard", _broken)
    result = run_intel.run_intel(
        asset="BTC", curr_date="2026-07-15",
        config={"intel_push_sinks": ["stdout"]}, alerts_only=True,
    )
    assert result["skipped_no_alerts"] is False
    assert "fear_greed" in result["message"]
    assert "盘面告警" in capsys.readouterr().out
