
import threading
import time
import random
import numpy as np
from datetime import datetime

from ml_model import MLModel


class BotEngine:
    """
    Bot automático com WATCHLIST TOP N por confiança.
    - Compra REAL apenas após confirmação (ID real).
    - Preferência de mercado: TURBO/BINARY -> DIGITAL.
    - Sincroniza no início do candle.
    - Watchlist dinâmica: só avalia os ativos mais confiáveis do momento.
    """

    def __init__(self, iq_service, config, event_queue=None, analyzer=None):
        self.iq = iq_service
        self.cfg = config or {}
        self.q = event_queue
        self.analyzer = analyzer

        self.running = False
        self.sem = threading.Semaphore(int(self.cfg.get("max_concurrent", 2)))

        # Estatísticas
        self.wins = 0
        self.losses = 0
        self.session_profit = 0.0
        self.consecutive_losses = 0

        # Risco
        self.entry = float(self.cfg.get("entry", 2))
        self.stop_win = float(self.cfg.get("stop_win", 20))
        self.stop_loss = float(self.cfg.get("stop_loss", -15))

        # Operação
        self.assets = list(self.cfg.get("pairs") or [])
        self.profile = self.cfg.get("profile", "Moderado")
        self.timeframe_label = self.cfg.get("timeframe", "1 Minuto")
        self.interval_sec = self._get_tf_sec(self.timeframe_label)

        # Filtros
        self.min_payout = float(self.cfg.get("min_payout", 70))
        self.cooldown_sec = int(self.cfg.get("cooldown_sec", 60))
        self.max_losses_row = int(self.cfg.get("max_losses_row", 3))
        self.min_confidence_ui = float(self.cfg.get("min_confidence", 0))

        self.candle_count = int(self.cfg.get("candle_count", 90))

        # ML
        self.use_ml = bool(self.cfg.get("use_ml", True))
        self.ml_threshold = float(self.cfg.get("ml_threshold", 0.58))
        self.ml = MLModel(seed=42, warmup=int(self.cfg.get("ml_warmup", 30)))

        # Mercado preferido (espelha melhor na IQ)
        self.market_prefer = tuple(self.cfg.get("market_prefer", ("turbo", "binary", "digital")))

        # Watchlist TOP N
        self.watchlist_size = int(self.cfg.get("watchlist_size", 15))
        self.watchlist_refresh_sec = int(self.cfg.get("watchlist_refresh_sec", 60))
        self._watchlist = []
        self._watchlist_ts = 0

        self._last_trade_ts = {}

    # ------------------------------------------------------------------
    def _get_tf_sec(self, label):
        label = (label or "").lower()
        if "1" in label and "min" in label:
            return 60
        if "5" in label and "min" in label:
            return 300
        if "15" in label and "min" in label:
            return 900
        return 60

    def _log(self, msg):
        if self.q:
            self.q.put({"type": "log", "message": msg})
        print(f"[BotEngine] {msg}")

    def _send_trade_event(self, order_id, asset, status, direction, profit, payout_txt, prob_txt, ind_used):
        if not self.q:
            return
        self.q.put({
            "type": "trade",
            "order_id": str(order_id),
            "hora": datetime.now().strftime("%H:%M:%S"),
            "par": asset,
            "tf": self.timeframe_label,
            "valor": f"R$ {self.entry:.2f}",
            "dir": direction.upper(),
            "prob": prob_txt,
            "ind": ind_used,
            "payout": payout_txt,
            "status": status,
            "resultado": "" if status == "OPEN" else status,
            "lucro": float(profit) if profit is not None else 0.0,
        })

    # ------------------------------------------------------------------
    @staticmethod
    def _ema(values, period: int):
        if values is None or len(values) < period:
            return None
        values = np.asarray(values, dtype=float)
        alpha = 2.0 / (period + 1.0)
        ema = [values[0]]
        for v in values[1:]:
            ema.append((v - ema[-1]) * alpha + ema[-1])
        return np.asarray(ema, dtype=float)

    @staticmethod
    def _atr(highs, lows, closes, period=14):
        if len(closes) < period + 2:
            return None
        highs = np.asarray(highs, dtype=float)
        lows = np.asarray(lows, dtype=float)
        closes = np.asarray(closes, dtype=float)
        prev_close = closes[:-1]
        tr = np.maximum(highs[1:] - lows[1:],
                        np.maximum(np.abs(highs[1:] - prev_close),
                                   np.abs(lows[1:] - prev_close)))
        return float(np.mean(tr[-period:]))

    def _get_candles(self, asset):
        try:
            return self.iq.get_candles(asset, self.interval_sec, self.candle_count) or []
        except Exception:
            return []

    @staticmethod
    def _extract_ohlc(candles):
        opens, highs, lows, closes = [], [], [], []
        for c in candles:
            opens.append(float(c.get("open", 0.0)))
            highs.append(float(c.get("max", c.get("high", c.get("close", 0.0)))))
            lows.append(float(c.get("min", c.get("low", c.get("close", 0.0)))))
            closes.append(float(c.get("close", 0.0)))
        return opens, highs, lows, closes

    # ------------------------------------------------------------------
    def _fast_confidence(self, asset, payout, closes, atr_val):
        """
        Score rápido (0..100) para ranquear ativos.
        """
        if payout is None:
            return 0.0

        score = float(payout)

        ema21 = self._ema(closes, 21)
        ema50 = self._ema(closes, 50)
        if ema21 is None or ema50 is None:
            return 0.0

        if ema21[-1] > ema50[-1] or ema21[-1] < ema50[-1]:
            score += 6.0

        if atr_val is not None and len(closes) > 0:
            p = max(1e-9, abs(closes[-1]))
            atr_pct = (atr_val / p) * 100.0
            if atr_pct >= 0.02:
                score += 6.0
            elif atr_pct >= 0.01:
                score += 3.0
            else:
                score -= 10.0

        return max(0.0, min(100.0, score))

    def _refresh_watchlist(self, assets):
        now = time.time()
        if self._watchlist and (now - self._watchlist_ts) < self.watchlist_refresh_sec:
            return self._watchlist

        ranked = []
        for asset in assets:
            try:
                payout = self.iq.get_payout_percent(asset)
                if payout is None or payout < self.min_payout:
                    continue

                candles = self._get_candles(asset)
                if len(candles) < 60:
                    continue

                _, highs, lows, closes = self._extract_ohlc(candles)
                atr_val = self._atr(highs, lows, closes, 14)

                score = self._fast_confidence(asset, payout, closes, atr_val)
                if score < (self._required_confidence() - 2):
                    continue

                ranked.append((score, asset))
            except Exception:
                continue

        ranked.sort(reverse=True, key=lambda x: x[0])
        self._watchlist = [a for _, a in ranked[:self.watchlist_size]]
        self._watchlist_ts = now

        if self._watchlist:
            self._log(f"👀 Watchlist TOP {len(self._watchlist)}: {', '.join(self._watchlist[:8])}" +
                      (" ..." if len(self._watchlist) > 8 else ""))
        else:
            self._log("👀 Watchlist vazia.")

        return self._watchlist

    # ------------------------------------------------------------------
    def _required_confidence(self):
        req = 0.0
        if self.analyzer:
            try:
                req = float(self.analyzer.get_required_confidence(self.profile))
            except Exception:
                req = 0.0
        return max(req, float(self.min_confidence_ui or 0.0))

    def _wait_next_candle(self):
        now = time.time()
        interval = max(1, int(self.interval_sec))
        next_ts = (int(now // interval) + 1) * interval
        time.sleep(max(0.0, next_ts - now))

    # ------------------------------------------------------------------
    def start(self):
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._run_loop, daemon=True).start()
        self._log(f"🚀 Bot iniciado | Watchlist TOP {self.watchlist_size}")

    def stop(self):
        self.running = False
        self._log("🛑 Bot parado")

    # ------------------------------------------------------------------
    def _run_loop(self):
        while self.running:
            try:
                assets = self.assets or self.iq.get_turbo_assets(include_otc=True, include_non_otc=True)[:150]

                watch = self._refresh_watchlist(assets)
                random.shuffle(watch)

                for asset in watch:
                    if not self.running:
                        break

                    payout = self.iq.get_payout_percent(asset)
                    candles = self._get_candles(asset)
                    if len(candles) < 60:
                        continue

                    _, highs, lows, closes = self._extract_ohlc(candles)
                    atr_val = self._atr(highs, lows, closes, 14)

                    direction, score, reason = self._signal(closes)
                    if not direction:
                        continue

                    final_conf = float(score)
                    if final_conf < self._required_confidence():
                        continue

                    threading.Thread(
                        target=self._trade_worker,
                        args=(asset, direction, payout, final_conf, reason),
                        daemon=True
                    ).start()

                    time.sleep(0.2)

                time.sleep(1.0)

            except Exception as e:
                self._log(f"❌ Loop erro: {e}")
                time.sleep(3)

    def _signal(self, closes):
        if len(closes) < 60:
            return None, 0, "poucas velas"

        ema21 = self._ema(closes, 21)
        ema50 = self._ema(closes, 50)
        if ema21 is None or ema50 is None:
            return None, 0, "ema indisponível"

        c0, c1, c2 = closes[-1], closes[-2], closes[-3]
        dist = abs(c0 - ema21[-1]) / max(1e-9, abs(ema21[-1]))

        if ema21[-1] > ema50[-1] and dist <= 0.005 and c0 > c1 < c2:
            return "call", 78, "pullback alta"
        if ema21[-1] < ema50[-1] and dist <= 0.005 and c0 < c1 > c2:
            return "put", 78, "pullback baixa"

        return None, 0, "sem sinal"

    def _trade_worker(self, asset, direction, payout, conf, reason):
        with self.sem:
            self._wait_next_candle()

            duration_min = max(1, self.interval_sec // 60)

            ok, order_id, market, err = self.iq.buy_best(
                asset, self.entry, direction, duration_min,
                prefer=self.market_prefer
            )
            if not ok:
                self._log(f"🚫 Compra falhou {asset}: {err}")
                return

            self._log(f"⚡ REAL {asset} {direction.upper()} | conf={conf:.0f}% | {market} | id={order_id}")
            self._send_trade_event(order_id, asset, "OPEN", direction, 0.0,
                                   f"{int(payout)}%", f"{conf:.0f}%", f"WATCHLIST|{market}")

            time.sleep(self.interval_sec)

            result = self.iq.check_result(order_id, market, timeout_sec=120)
            profit = float(result) if result is not None else -self.entry
            status = "WIN" if profit > 0 else "LOSS"

            self._send_trade_event(order_id, asset, status, direction, profit,
                                   f"{int(payout)}%", f"{conf:.0f}%", f"WATCHLIST|{market}")
            self._log(f"🏁 {asset} => {status} | lucro={profit}")
