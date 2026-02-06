import time
import random
import numpy as np

MHI_RSI = "MHI_RSI"
RSI_REVERSAL = "RSI_REVERSAL"
BOLLINGER_REVERSAL = "BOLLINGER_REVERSAL"
PRICE_ACTION = "PRICE_ACTION"
MULTI_CONFIRMATION = "MULTI_CONFIRMATION"
TREND_FOLLOW = "TREND_FOLLOW"

UP = "up"
DOWN = "down"
NEUTRAL = "neutral"


class StrategyAnalyzer:
    """
    Analisador leve (sem promessas):
    - Analisa candles + payout e sugere direção/confiança.
    - Mantém histórico por ativo/estratégia/timeframe (record_test_result).
    - Retorna confiança mínima por perfil.
    """

    def __init__(self, iq_service):
        self.iq = iq_service
        self.strategy_results = {}
        self.last_analysis = {}
        self.analysis_count = 0

    # -----------------------------
    # Helpers numéricos
    # -----------------------------
    @staticmethod
    def _ema(values, period: int):
        if not values or len(values) < period:
            return None
        values = np.asarray(values, dtype=float)
        alpha = 2.0 / (period + 1.0)
        ema = [values[0]]
        for v in values[1:]:
            ema.append((v - ema[-1]) * alpha + ema[-1])
        return np.asarray(ema, dtype=float)

    @staticmethod
    def _safe_closes(candles):
        closes = []
        for c in candles or []:
            closes.append(float(c.get("close", 0.0)))
        return closes

    def _calc_rsi(self, closes, period=14):
        if len(closes) < period + 2:
            return 0.5, NEUTRAL

        diffs = np.diff(np.asarray(closes[-(period + 1):], dtype=float))
        gains = np.where(diffs > 0, diffs, 0.0)
        losses = np.where(diffs < 0, -diffs, 0.0)

        avg_gain = float(np.mean(gains)) if gains.size else 1e-6
        avg_loss = float(np.mean(losses)) if losses.size else 1e-6
        rs = avg_gain / (avg_loss + 1e-9)
        rsi = 100.0 - (100.0 / (1.0 + rs))

        if 40 <= rsi <= 70:
            score = 0.8
        elif 30 <= rsi < 40 or 70 < rsi <= 80:
            score = 0.6
        else:
            score = 0.4

        if rsi <= 35:
            sig = "oversold"
        elif rsi >= 75:
            sig = "overbought"
        else:
            sig = NEUTRAL
        return score, sig

    def _calc_trend(self, closes):
        if len(closes) < 30:
            return 0.5, NEUTRAL

        ema_fast = self._ema(closes, 10)
        ema_slow = self._ema(closes, 20)
        if ema_fast is None or ema_slow is None:
            return 0.5, NEUTRAL

        tail = closes[-6:]
        if len(tail) >= 2 and tail[-1] > tail[0]:
            trend = UP
        elif len(tail) >= 2 and tail[-1] < tail[0]:
            trend = DOWN
        else:
            trend = NEUTRAL

        score = 0.7 if trend in (UP, DOWN) else 0.55
        return score, trend

    def analyze_with_indicators(self, asset, indicators_config, timeframe_sec=60, candle_count=80):
        self.analysis_count += 1

        try:
            payout = self.iq.get_payout_percent(asset)
        except Exception:
            payout = 80

        try:
            candles = self.iq.get_candles(asset, timeframe_sec, candle_count) or []
        except Exception:
            candles = []

        closes = self._safe_closes(candles)

        tech = 50.0
        momentum = 50.0
        indicators_used = []

        # RSI
        if indicators_config.get("rsi", False):
            rsi_score, rsi_sig = self._calc_rsi(closes)
            tech += rsi_score * 20
            momentum += rsi_score * 15
            indicators_used.append("RSI")
        else:
            rsi_sig = NEUTRAL

        # Tendência (MACD simplificado)
        if indicators_config.get("macd", False):
            tr_score, trend = self._calc_trend(closes)
            tech += tr_score * 20
            indicators_used.append("MACD")
        else:
            tr_score, trend = self._calc_trend(closes)

        # Price action básico
        if indicators_config.get("close_price", True) and len(closes) >= 6:
            tail = closes[-6:]
            if tail[-1] > tail[0]:
                trend = trend if trend != NEUTRAL else UP
                tech += 12
            elif tail[-1] < tail[0]:
                trend = trend if trend != NEUTRAL else DOWN
                tech += 12
            indicators_used.append("PRICE")

        tech = float(np.clip(tech, 30.0, 100.0))
        momentum = float(np.clip(momentum, 30.0, 100.0))

        base_conf = tech * 0.6 + momentum * 0.2

        payout_bonus = 0.0
        if payout is not None:
            if payout >= 80:
                payout_bonus = 15
            elif payout >= 75:
                payout_bonus = 10
            elif payout >= 70:
                payout_bonus = 5

        ind_bonus = min(20.0, len(indicators_used) * 5.0)
        confidence = float(np.clip(base_conf + payout_bonus + ind_bonus, 40.0, 95.0))

        if trend == UP:
            recommendation = "call"
        elif trend == DOWN:
            recommendation = "put"
        else:
            if rsi_sig == "oversold":
                recommendation = "call"
            elif rsi_sig == "overbought":
                recommendation = "put"
            else:
                recommendation = random.choice(["call", "put"])

        strategies = self._generate_strategies(trend, indicators_used)

        return {
            "asset": asset,
            "payout": float(payout) if payout is not None else None,
            "timestamp": time.time(),
            "indicators_used": indicators_used,
            "technical_score": tech,
            "momentum_score": momentum,
            "trend_direction": trend,
            "confidence": confidence,
            "recommendation": recommendation,
            "strategies": strategies,
            "analysis_id": self.analysis_count,
        }

    @staticmethod
    def _generate_strategies(trend, indicators_used):
        strategies = [PRICE_ACTION]
        if "RSI" in indicators_used:
            strategies += [MHI_RSI, RSI_REVERSAL]
        if "MACD" in indicators_used or trend in (UP, DOWN):
            strategies.append(TREND_FOLLOW)
        if len(set(indicators_used)) >= 2:
            strategies.append(MULTI_CONFIRMATION)

        out = []
        for s in strategies:
            if s not in out:
                out.append(s)
        return out[:4]

    # -----------------------------
    # Histórico
    # -----------------------------
    def record_test_result(self, asset, strategy, timeframe_label, result, payout):
        key = f"{asset}_{strategy}_{timeframe_label}"
        if key not in self.strategy_results:
            self.strategy_results[key] = {"wins": 0, "losses": 0, "total": 0, "last_payout": None, "last_update": 0}

        if str(result).upper() == "WIN":
            self.strategy_results[key]["wins"] += 1
        else:
            self.strategy_results[key]["losses"] += 1

        self.strategy_results[key]["total"] += 1
        self.strategy_results[key]["last_payout"] = payout
        self.strategy_results[key]["last_update"] = time.time()

    def get_best_strategy_for_asset(self, asset):
        best = None
        best_score = -1

        for key, stats in self.strategy_results.items():
            if not key.startswith(asset + "_"):
                continue

            total = int(stats.get("total", 0))
            if total < 3:
                continue

            wins = int(stats.get("wins", 0))
            win_rate = wins / max(1, total)
            score = win_rate * 100.0 + min(total, 15)

            if score > best_score:
                best_score = score
                parts = key.split("_")
                best = parts[1] if len(parts) >= 3 else PRICE_ACTION

        return best or PRICE_ACTION

    def get_required_confidence(self, profile: str):
        profile = (profile or "").strip().lower()
        if profile == "agressivo":
            return 55.0
        if profile == "moderado":
            return 60.0
        return 65.0
