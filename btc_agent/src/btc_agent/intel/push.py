"""告警推送(BTC agent v1 情报层)。

可插拔 sink:把 ``Alert`` 列表渲染成一条消息发出去。默认 ``StdoutSink``(零依赖、
本地可见);``TelegramSink`` 走 Telegram Bot API,token/chat_id 从环境变量读,网络
出口集中在 ``_send`` 单点(测试 monkeypatch 即可离线跑,不真发消息)。

推送与规则解耦:规则引擎只产出 Alert,本模块只负责"送达",互不知道对方细节。
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Protocol

import requests

from btc_agent.intel.rules import Alert

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15

# 级别 → emoji 前缀,让推送一眼看出轻重。
_LEVEL_ICON = {"critical": "🔴", "warning": "🟠", "info": "🔵"}


def render_message(asset: str, curr_date: str, alerts: list[Alert]) -> str:
    """把告警列表渲染成一条 Markdown 消息。无告警时给出明确"无异常"文案。"""
    if not alerts:
        return f"*{asset} 盘面告警 {curr_date}*\n\n✅ 无触发规则的异常信号。"
    lines = [f"*{asset} 盘面告警 {curr_date}*", ""]
    for a in alerts:
        icon = _LEVEL_ICON.get(a.level, "•")
        lines.append(f"{icon} [{a.level.upper()}] {a.message}")
    return "\n".join(lines)


class Sink(Protocol):
    """推送目标协议:实现 ``send(message)`` 即可接入。"""

    def send(self, message: str) -> None: ...


class StdoutSink:
    """把消息打到标准输出(默认 sink,本地/日志可见)。

    对控制台编码健壮:Windows 默认 gbk 控制台无法编码告警里的 emoji(🔴/✅),
    直接 ``print`` 会抛 UnicodeEncodeError 让推送失败。这里按 stdout 实际编码做
    有损转换(不可编码字符替换为 ``?``),保证消息一定送达而非崩在渠道层。
    """

    name = "stdout"

    def send(self, message: str) -> None:
        enc = sys.stdout.encoding or "utf-8"
        safe = message.encode(enc, errors="replace").decode(enc, errors="replace")
        sys.stdout.write(safe + "\n")


class TelegramSink:
    """通过 Telegram Bot API 推送。token/chat_id 缺失则构造时报错(调用方决定是否启用)。"""

    name = "telegram"

    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        if not self.token or not self.chat_id:
            raise ValueError(
                "TelegramSink 需要 TELEGRAM_BOT_TOKEN 与 TELEGRAM_CHAT_ID 环境变量。"
            )

    def _send(self, message: str) -> None:
        """网络唯一出口(测试 patch 此方法)。"""
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        resp = requests.post(
            url,
            json={"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()

    def send(self, message: str) -> None:
        self._send(message)


def build_sinks_from_config(config: dict) -> list[Sink]:
    """按 config["intel_push_sinks"](名称列表)构造 sink。

    telegram sink 缺环境变量时降级(记 warning、跳过),不阻断其它 sink——
    情报推送不该因一个渠道未配好而整体失败。未配置时默认只有 stdout。
    """
    names = config.get("intel_push_sinks") or ["stdout"]
    sinks: list[Sink] = []
    for name in names:
        if name == "stdout":
            sinks.append(StdoutSink())
        elif name == "telegram":
            try:
                sinks.append(TelegramSink())
            except ValueError as exc:
                logger.warning("Telegram sink 未启用:%s", exc)
        else:
            logger.warning("未知推送 sink %r,已跳过。", name)
    return sinks


def dispatch(message: str, sinks: list[Sink]) -> int:
    """把消息发往所有 sink,返回成功送达数。单个 sink 失败只记 warning,不影响其它。"""
    delivered = 0
    for sink in sinks:
        try:
            sink.send(message)
            delivered += 1
        except Exception as exc:  # noqa: BLE001 — 一个渠道失败不该拖垮其它
            logger.warning("推送 sink %r 失败:%s", getattr(sink, "name", sink), exc)
    return delivered
