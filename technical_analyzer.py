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
    # 이동평균선 (MA) + 골든크로스/데드크로스
    # ═══════════════════════════════════════════════════════════
    def calc_ma(self, closes: List[float], period: int) -> float:
        """단순 이동평균(SMA) 계산"""
        if len(closes) < period:
            return 0.0
        return round(sum(closes[-period:]) / period, 2)

    def detect_cross(self, closes: List[float],
                     short_period: int = 5, long_period: int = 20) -> str:
        """
        골든크로스 / 데드크로스 감지
        - GOLDEN: 단기 MA가 장기 MA를 위로 돌파 → 상승 전환
        - DEAD: 단기 MA가 장기 MA를 아래로 돌파 → 하락 전환
        - NONE: 교차 없음
        """
        if len(closes) < long_period + 2:
            return "NONE"

        # 현재와 이전의 MA 비교
        current_short = self.calc_ma(closes, short_period)
        current_long = self.calc_ma(closes, long_period)

        prev_closes = closes[:-1]
        prev_short = self.calc_ma(prev_closes, short_period)
        prev_long = self.calc_ma(prev_closes, long_period)

        # 이전: short < long → 현재: short > long → 골든크로스
        if prev_short <= prev_long and current_short > current_long:
            return "GOLDEN"
        # 이전: short > long → 현재: short < long → 데드크로스
        elif prev_short >= prev_long and current_short < current_long:
            return "DEAD"
        return "NONE"

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

        # 3. 이동평균선 크로스
        cross = self.detect_cross(closes, short_period=5, long_period=20)
        ma5 = self.calc_ma(closes, 5)
        ma20 = self.calc_ma(closes, 20)

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
            reasons.append("골든크로스 발생! (강력 상승 전환)")
        elif cross == "DEAD":
            score -= 25
            reasons.append("데드크로스 발생 (하락 전환)")
        elif ma5 > ma20:
            score += 5
            reasons.append("단기 MA > 장기 MA (상승 추세)")
        else:
            score -= 5
            reasons.append("단기 MA < 장기 MA (하락 추세)")

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
                "ma5": ma5,
                "ma20": ma20,
                "cross": cross,
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
    print(f"  MA(5): {ind['ma5']:,.0f} / MA(20): {ind['ma20']:,.0f}")
    print(f"  크로스: {ind['cross']}")
    print(f"  볼린저: 상단 {ind['bollinger']['upper']:,.0f} | 중간 {ind['bollinger']['middle']:,.0f} | 하단 {ind['bollinger']['lower']:,.0f}")
    print(f"  MACD: {ind['macd']['macd']} / Signal: {ind['macd']['signal']} ({ind['macd']['trend']})")
    print(f"\n  [판단 근거]")
    for r in result['reasons']:
        print(f"  → {r}")
