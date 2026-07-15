"""BTC agent 包骨架（v0）。

架构参照 TradingAgents（LangGraph 编排 + 多 agent 辩论 + 记忆/反思闭环），
数据源换成 crypto vendor（ccxt / CryptoPanic / F&G），交易日历改 7×24 UTC。
详见仓库根目录 BTC-DESIGN-REVIEW.md 的 v0→成熟版路线。

下面的 .env 加载 / 告警过滤逻辑是从 vendored 的 TradingAgents 顶层
``__init__.py`` 原样搬入的编排样板代码（见 ``VENDORED.md``），非本子任务
新增业务逻辑。
"""

import contextlib
import warnings

__version__ = "0.0.0"

# Load .env files at package import so DEFAULT_CONFIG's env-var overlay
# (and every llm_clients consumer) sees the user's keys regardless of
# which entry point started the process. find_dotenv(usecwd=True) walks
# from the CWD, so an installed console script picks up the project's
# .env instead of stepping up from site-packages.
# load_dotenv defaults to override=False, so it never clobbers values
# the caller has already exported.
try:
    from dotenv import find_dotenv, load_dotenv

    load_dotenv(find_dotenv(usecwd=True))
    load_dotenv(find_dotenv(".env.enterprise", usecwd=True), override=False)
except ImportError:
    pass

# langchain-core calls surface_langchain_deprecation_warnings() in its own
# __init__, which prepends default-action filters for its subclassed warning
# categories. To suppress a specific warning we must install our filter AFTER
# langchain-core has installed its own, so import it first. The package is a
# guaranteed transitive dep via langgraph.
with contextlib.suppress(ImportError):
    import langchain_core  # noqa: F401

# langgraph-checkpoint calls Reviver() at module load without an explicit
# allowed_objects, which triggers a noisy pending-deprecation warning from
# langchain-core on every interpreter start (upstream fix pending). Silence it
# here rather than at every call site.
warnings.filterwarnings(
    "ignore",
    message=r"The default value of `allowed_objects`.*",
    category=PendingDeprecationWarning,
)
