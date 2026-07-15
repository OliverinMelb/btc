"""告警推送(BTC agent v1 情报层)。

可插拔 sink:把 ``Alert`` 列表渲染成一条消息发出去。``StdoutSink``(零依赖、本地可见);
``EmailSink`` 走 SMTP(默认 QQ 邮箱);``FeishuSink`` 走飞书自定义机器人 webhook;
``TelegramSink`` 走 Telegram Bot API。凭据一律从环境变量读,网络出口集中在各自 ``_send``
单点(测试 monkeypatch 即可离线跑,不真发)。

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


class FeishuSink:
    """通过飞书(Feishu/Lark)自定义机器人 webhook 推送。

    webhook 从 ``FEISHU_WEBHOOK_URL`` 读;缺失则构造时报错(调用方决定是否启用)。
    若机器人开了"签名校验",把密钥放 ``FEISHU_WEBHOOK_SECRET``,本 sink 自动按飞书算法
    (``HMAC-SHA256(key=f"{ts}\\n{secret}", msg="")`` → base64)带上 timestamp+sign。
    飞书 text 消息不渲染 Markdown,故发送前去掉 ``*`` 加粗标记(emoji 正常显示)。
    """

    name = "feishu"

    def __init__(self, webhook_url: str | None = None, secret: str | None = None):
        self.webhook_url = webhook_url or os.getenv("FEISHU_WEBHOOK_URL")
        self.secret = secret or os.getenv("FEISHU_WEBHOOK_SECRET")
        if not self.webhook_url:
            raise ValueError("FeishuSink 需要 FEISHU_WEBHOOK_URL 环境变量。")

    def _sign(self, timestamp: int) -> str:
        """按飞书自定义机器人签名算法算 sign(仅在设置了 secret 时调用)。"""
        import base64
        import hashlib
        import hmac

        string_to_sign = f"{timestamp}\n{self.secret}"
        digest = hmac.new(string_to_sign.encode("utf-8"), b"", hashlib.sha256).digest()
        return base64.b64encode(digest).decode("utf-8")

    def _send(self, message: str) -> None:
        """网络唯一出口(测试 patch 此方法)。timestamp 由调用方注入以便可测。"""
        import time

        text = message.replace("*", "")  # 飞书 text 不渲染 Markdown 加粗
        payload: dict = {"msg_type": "text", "content": {"text": text}}
        if self.secret:
            ts = int(time.time())
            payload["timestamp"] = str(ts)
            payload["sign"] = self._sign(ts)
        resp = requests.post(self.webhook_url, json=payload, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        # 飞书 HTTP 200 但业务失败时 body 里 code!=0(如关键词不匹配/签名错),需显式检查。
        body = resp.json()
        if body.get("code") not in (0, None):
            raise RuntimeError(f"飞书 webhook 返回错误 code={body.get('code')}: {body.get('msg')}")

    def send(self, message: str) -> None:
        self._send(message)


class EmailSink:
    """通过 SMTP 发邮件推送(默认 QQ 邮箱 smtp.qq.com:465 SSL)。

    凭据从环境变量读:``SMTP_USER``(发件邮箱)、``SMTP_PASSWORD``(**授权码**,非登录密码)、
    ``EMAIL_TO``(收件人);可选 ``SMTP_HOST``/``SMTP_PORT``/``EMAIL_FROM``。缺必填项则构造
    时报错(调用方决定是否启用)。用 stdlib ``smtplib``,不加依赖;主题取消息首行。
    """

    name = "email"

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        to: str | None = None,
        sender: str | None = None,
    ):
        self.host = host or os.getenv("SMTP_HOST", "smtp.qq.com")
        self.port = int(port or os.getenv("SMTP_PORT", "465"))
        self.user = user or os.getenv("SMTP_USER")
        self.password = password or os.getenv("SMTP_PASSWORD")
        self.to = to or os.getenv("EMAIL_TO")
        self.sender = sender or os.getenv("EMAIL_FROM") or self.user
        if not (self.user and self.password and self.to):
            raise ValueError(
                "EmailSink 需要 SMTP_USER / SMTP_PASSWORD / EMAIL_TO 环境变量"
                "(QQ 邮箱 SMTP_PASSWORD 填授权码,非登录密码)。"
            )

    def _build_message(self, message: str):
        """把推送文本组装成 EmailMessage:去 * 加粗,主题取首行。"""
        from email.message import EmailMessage

        text = message.replace("*", "")
        first_line = next((ln for ln in text.splitlines() if ln.strip()), "BTC 情报")
        msg = EmailMessage()
        msg["Subject"] = first_line.strip()
        msg["From"] = self.sender
        msg["To"] = self.to
        msg.set_content(text)
        return msg

    def _send(self, message: str) -> None:
        """网络唯一出口(测试 patch 此方法)。465 走 SSL,其它端口走 STARTTLS。"""
        import smtplib

        msg = self._build_message(message)
        if self.port == 465:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=REQUEST_TIMEOUT) as s:
                s.login(self.user, self.password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=REQUEST_TIMEOUT) as s:
                s.starttls()
                s.login(self.user, self.password)
                s.send_message(msg)

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
        elif name == "feishu":
            try:
                sinks.append(FeishuSink())
            except ValueError as exc:
                logger.warning("Feishu sink 未启用:%s", exc)
        elif name == "email":
            try:
                sinks.append(EmailSink())
            except ValueError as exc:
                logger.warning("Email sink 未启用:%s", exc)
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
