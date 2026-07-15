"""`python -m btc_agent` 等价于 `python -m btc_agent.run`。"""

from btc_agent.run import main

if __name__ == "__main__":
    raise SystemExit(main())
