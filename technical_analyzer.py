"""
ChoiGPT Technical Analysis Engine
=================================
스캘핑 고수들이 사용하는 핵심 기술적 지표 모듈
- RSI (과매수/과매도)
- Bollinger Bands (변동성 + 평균회귀)
- 이동평균선 (골든크로스/데드크로스)
- MACD (추세 전환)
"""
import requests
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger("TechnicalAnalysis")


class TechnicalAnalyzer:
    """빗썸 캔들 데이터 기반 기술적 분석 엔진"""

    def __init__(self):
        self.cache = {}

    # ═══════════════════════════════════════════════════════════
    # 캔들 데이터 수집
    # ═══════════════════════════════════════════════════════════
    def get_candles(self, symbol: str, interval: str = "5m", count: int = 100) -> List[dict]:
        """
        빗썸 캔들스틱 데이터 조회
        interval: 1m, 3m, 5m, 10m, 30m, 1h, 6h, 12h, 24h
        """
        try:
            url = f"https://api.bithumb.com/public/candlestick/{symbol}_KRW/{interval}"
            resp = requests.get(url, timeout=10)
            data = resp.json()
            if data.get("status") != "0000":
                return []

            candles = []
            for c in data["data"][-count:]:
                candles.append({
                    "timestamp": c[0],
                    "open": float(c[1]),
                    "close": float(c[2]),
                    "high": float(c[3]),
                    "low": float(c[4]),
                    "volume": float(c[5])
                })
            return candles
        except Exception as e:
            logger.error(f"캔들 데이터 조회 실패 ({symbol}): {e}")
            return []

    # ═══════════════════════════════════════════════════════════
    # RSI (Relative Strength Index) - 과매수/과매도 판별
    # ═══════════════════════════════════════════════════════════
    def calc_rsi(self, closes: List[float], period: int = 14) -> float:
        """
        RSI 계산
        - 30 이하: 과매도 → 매수 시그널
        - 70 이상: 과매수 → 매도 시그널
        - 30~70: 중립
        """
        if len(closes) < period + 1:
            return 50.0  # 데이터 부족 시 중립

        gains = []
        losses = []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i - 1]
            gains.append(max(diff, 0))
            losses.append(max(-diff, 0))

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # Wilder's Smoothing
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    # ═══════════════════════════════════════════════════════════
    # Bollinger Bands - 변동성 밴드
    # ═══════════════════════════════════════════════════════════
    def calc_bollinger(self, closes: List[float], period: int = 20, std_dev: float = 2.0) -> Dict:
        """
        볼린저 밴드 계산
        - 하단 밴드 터치: 매수 시그널 (평균 회귀 기대)
        - 상단 밴드 터치: 매도 시그널
        - 밴드 폭 축소: 큰 변동 임박 (스퀴즈)
        """
        if len(closes) < period:
            return {"upper": 0, "middle": 0, "lower": 0, "width": 0}

        recent = closes[-period:]
        middle = sum(recent) / period
        variance = sum((x - middle) ** 2 for x in recent) / period
        std = variance ** 0.5

        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        width = ((upper - lower) / middle) * 100  # 밴드 폭 (%)

        return {
            "upper": round(upper, 2),
            "middle": round(middle, 2),
            "lower": round(lower, 2),
            "width": round(width, 2)
        }

    # ═══════════════════════════════════════════════════════════
    # EMA 9/21 (고수 기법) & VWAP & MTF
    # ═══════════════════════════════════════════════════════════
    def detect_ema_cross(self, closes: List[float],
                         short_period: int = 9, long_period: int = 21) -> str:
        """EMA 골든크로스 / 데드크로스 감지"""
        if len(closes) < long_period + 2:
            return "NONE"
            
        short_emas = self.calc_ema(closes, short_period)
        long_emas = self.calc_ema(closes, long_period)
        
        if len(short_emas) < 2 or len(long_emas) < 2:
            return "NONE"

        current_short, prev_short = short_emas[-1], short_emas[-2]
        current_long, prev_long = long_emas[-1], long_emas[-2]

        if prev_short <= prev_long and current_short > current_long:
            return "GOLDEN"
        elif prev_short >= prev_long and current_short < current_long:
            return "DEAD"
        return "NONE"

    def calc_vwap(self, candles: List[dict]) -> float:
        """VWAP (Volume Weighted Average Price) 계산"""
        total_value = 0.0
        total_volume = 0.0
        for c in candles:
            typical_price = (c["high"] + c["low"] + c["close"]) / 3
            total_value += typical_price * c["volume"]
            total_volume += c["volume"]
        return round(total_value / total_volume, 2) if total_volume else 0.0

    def check_mtf_trend(self, symbol: str) -> str:
        """1시간봉 기반 Multi-Timeframe Filter"""
        candles = self.get_candles(symbol, "1h", 30)
        if len(candles) < 22:
            return "NEUTRAL"
        closes = [c["close"] for c in candles]
        ema9 = self.calc_ema(closes, 9)[-1]
        ema21 = self.calc_ema(closes, 21)[-1]
        return "UPTREND" if ema9 > ema21 else "DOWNTREND"

    # ═══════════════════════════════════════════════════════════
    # MACD (Moving Average Convergence Divergence)
    # ═══════════════════════════════════════════════════════════
    def calc_ema(self, closes: List[float], period: int) -> List[float]:
        """지수이동평균(EMA) 계산"""
        if len(closes) < period:
            return []
        k = 2 / (period + 1)
        ema = [sum(closes[:period]) / period]
        for price in closes[period:]:
            ema.append(price * k + ema[-1] * (1 - k))
        return ema

    def calc_macd(self, closes: List[float],
                  fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
        """
        MACD 계산
        - MACD > Signal: 매수 시그널
        - MACD < Signal: 매도 시그널
        - 히스토그램 양전환: 상승 모멘텀
        """
        if len(closes) < slow + signal:
            return {"macd": 0, "signal": 0, "histogram": 0, "trend": "NEUTRAL"}

        ema_fast = self.calc_ema(closes, fast)
        ema_slow = self.calc_ema(closes, slow)

        # MACD 라인 = EMA(12) - EMA(26)
        min_len = min(len(ema_fast), len(ema_slow))
        offset = len(ema_fast) - min_len
        macd_line = [ema_fast[offset + i] - ema_slow[i] for i in range(min_len)]

        # Signal 라인 = MACD의 EMA(9)
        if len(macd_line) < signal:
            return {"macd": 0, "signal": 0, "histogram": 0, "trend": "NEUTRAL"}

        signal_line = self.calc_ema(macd_line, signal)
        if not signal_line:
            return {"macd": 0, "signal": 0, "histogram": 0, "trend": "NEUTRAL"}

        current_macd = macd_line[-1]
        current_signal = signal_line[-1]
        histogram = current_macd - current_signal

        trend = "BULLISH" if histogram > 0 else "BEARISH"

        return {
            "macd": round(current_macd, 2),
            "signal": round(current_signal, 2),
            "histogram": round(histogram, 2),
            "trend": trend
        }

    # ═══════════════════════════════════════════════════════════
    # 종합 분석 (모든 지표 통합 판단)
    # ═══════════════════════════════════════════════════════════
    def analyze(self, symbol: str) -> Dict:
        """
        종목에 대한 종합 기술적 분석 실행

        Returns:
            verdict: BUY / SELL / HOLD
            score: -100 ~ +100 (양수일수록 매수 강도)
            indicators: 개별 지표 상세
        """
        # 5분봉 캔들 100개 조회
        candles = self.get_candles(symbol, "5m", 100)
        if len(candles) < 30:
            return {"verdict": "HOLD", "score": 0, "reason": "데이터 부족"}

        closes = [c["close"] for c in candles]
        current_price = closes[-1]

        # 1. RSI
        rsi = self.calc_rsi(closes)

        # 2. Bollinger Bands
        bb = self.calc_bollinger(closes)

        # 3. EMA 9/21 크로스 & VWAP & MTF
        cross = self.detect_ema_cross(closes, 9, 21)
        emas = self.calc_ema(closes, 9)
        ema9 = emas[-1] if emas else 0
        ema21_list = self.calc_ema(closes, 21)
        ema21 = ema21_list[-1] if ema21_list else 0
        vwap = self.calc_vwap(candles)
        mtf_trend = self.check_mtf_trend(symbol)

        # 4. MACD
        macd = self.calc_macd(closes)

        # ─── 종합 점수 계산 ────────────────────────────────
        score = 0
        reasons = []

        # RSI 점수 (-30 ~ +30)
        if rsi <= 30:
            score += 30
            reasons.append(f"RSI {rsi} 과매도 (강력 매수)")
        elif rsi <= 40:
            score += 15
            reasons.append(f"RSI {rsi} 매수 구간")
        elif rsi >= 70:
            score -= 30
            reasons.append(f"RSI {rsi} 과매수 (매도)")
        elif rsi >= 60:
            score -= 10
            reasons.append(f"RSI {rsi} 주의")

        # 볼린저 밴드 점수 (-25 ~ +25)
        if bb["lower"] > 0 and current_price <= bb["lower"]:
            score += 25
            reasons.append("볼린저 하단 터치 (반등 기대)")
        elif bb["upper"] > 0 and current_price >= bb["upper"]:
            score -= 25
            reasons.append("볼린저 상단 터치 (조정 주의)")
        elif bb["width"] < 2.0:
            score += 5
            reasons.append(f"볼린저 스퀴즈 (폭 {bb['width']}% → 큰 변동 임박)")

        # 골든크로스/데드크로스 점수 (-25 ~ +25)
        if cross == "GOLDEN":
            score += 25
            reasons.append("EMA 9/21 골든크로스! (강력 매수)")
        elif cross == "DEAD":
            score -= 25
            reasons.append("EMA 9/21 데드크로스 (매도)")
        elif ema9 > ema21:
            score += 5
            reasons.append("EMA 9 > EMA 21 (상승 추세)")
        else:
            score -= 5
            reasons.append("EMA 9 < EMA 21 (하락 추세)")

        # VWAP 점수 (-15 ~ +15)
        if current_price < vwap:
            score += 15
            reasons.append(f"VWAP 하회 (반등 기대, VWAP: {vwap:,.0f})")
        else:
            score -= 15
            reasons.append(f"VWAP 상회 (조정 주의, VWAP: {vwap:,.0f})")

        # MTF 점수 (필터)
        if mtf_trend == "DOWNTREND":
            score -= 50  # 1시간봉 하락장 시 강력 차단
            reasons.append("1시간봉 DOWNTREND (매수 차단)")
        elif mtf_trend == "UPTREND":
            score += 10
            reasons.append("1시간봉 UPTREND (상승 동력)")

        # MACD 점수 (-20 ~ +20)
        if macd["trend"] == "BULLISH":
            score += 15 if macd["histogram"] > 0 else 5
            reasons.append(f"MACD 상승 (히스토그램 {macd['histogram']})")
        else:
            score -= 15 if macd["histogram"] < 0 else -5
            reasons.append(f"MACD 하락 (히스토그램 {macd['histogram']})")

        # ─── 최종 판단 ────────────────────────────────────
        if score >= 30:
            verdict = "BUY"
        elif score <= -30:
            verdict = "SELL"
        else:
            verdict = "HOLD"

        return {
            "symbol": symbol,
            "verdict": verdict,
            "score": score,
            "reasons": reasons,
            "indicators": {
                "rsi": rsi,
                "bollinger": bb,
                "ema9": ema9,
                "ema21": ema21,
                "cross": cross,
                "vwap": vwap,
                "mtf_trend": mtf_trend,
                "macd": macd,
                "current_price": current_price
            }
        }


# ═══════════════════════════════════════════════════════════════
# 테스트 실행
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    ta = TechnicalAnalyzer()

    # 솔라나 분석
    result = ta.analyze("SOL")
    print(f"\n{'='*50}")
    print(f"  {result['symbol']} 종합 기술적 분석")
    print(f"{'='*50}")
    print(f"  판정: {result['verdict']} (점수: {result['score']})")
    print(f"\n  [지표 상세]")
    ind = result['indicators']
    print(f"  RSI(14): {ind['rsi']}")
    print(f"  EMA(9): {ind['ema9']:,.0f} / EMA(21): {ind['ema21']:,.0f}")
    print(f"  VWAP: {ind['vwap']:,.0f} / MTF: {ind['mtf_trend']}")
    print(f"  크로스: {ind['cross']}")
    print(f"  볼린저: 상단 {ind['bollinger']['upper']:,.0f} | 중간 {ind['bollinger']['middle']:,.0f} | 하단 {ind['bollinger']['lower']:,.0f}")
    print(f"  MACD: {ind['macd']['macd']} / Signal: {ind['macd']['signal']} ({ind['macd']['trend']})")
    print(f"\n  [판단 근거]")
    for r in result['reasons']:
        print(f"  → {r}")
