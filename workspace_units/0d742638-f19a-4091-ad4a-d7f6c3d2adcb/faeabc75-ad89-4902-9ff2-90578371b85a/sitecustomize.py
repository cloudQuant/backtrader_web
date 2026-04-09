# Backtrader Web subprocess compatibility
try:
    import backtrader as bt

    _BaseTradeLogger = getattr(bt.observers, "TradeLogger", None)
    if _BaseTradeLogger is not None and not getattr(
        _BaseTradeLogger, "_bt_web_compat", False
    ):
        class BacktraderWebTradeLogger(_BaseTradeLogger):
            params = (
                ("log_data", None),
                ("log_file_enabled", None),
                ("file_format", None),
            )

            def __init__(self):
                super().__init__()
                log_data = getattr(self.p, "log_data", None)
                if log_data is not None and hasattr(self.p, "log_bars"):
                    self.p.log_bars = log_data

                file_format = getattr(self.p, "file_format", None)
                if file_format is not None and hasattr(self.p, "log_format"):
                    normalized = str(file_format).lower()
                    if normalized in {"json", "text"}:
                        self.p.log_format = normalized

        BacktraderWebTradeLogger._bt_web_compat = True
        bt.observers.TradeLogger = BacktraderWebTradeLogger
except Exception:
    pass
