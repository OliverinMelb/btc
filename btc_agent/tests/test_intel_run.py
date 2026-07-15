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
    # 消息经 stdout sink 打印
    assert "BTC 盘面告警" in capsys.readouterr().out


def test_run_intel_degrades_on_vendor_failure(monkeypatch):
    """所有信号取数失败时,dashboard 全 None、无告警、消息为"无异常",不崩。"""
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
    assert "无触发规则的异常信号" in result["message"]
