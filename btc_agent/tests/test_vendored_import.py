"""ST1 冒烟单测：vendored TradingAgents 骨架能否被干净 import。

只断言 import 成功，不实例化 graph、不调 LLM、不联网。
"""


def test_package_imports():
    import btc_agent  # noqa: F401


def test_trading_graph_imports():
    from btc_agent.graph.trading_graph import GraphSetup, TradingAgentsGraph

    assert TradingAgentsGraph is not None
    assert GraphSetup is not None
