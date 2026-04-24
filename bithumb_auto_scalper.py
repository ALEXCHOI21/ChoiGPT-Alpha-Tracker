"""
ChoiGPT Bithumb Agentic Auto-Scalper v3.0
==========================================
Phase 1: 실전 매매 (TP/SL + 상태 영속화)
Phase 2: 방어력 강화 (바이낸스 동기화 + import 방어)
Phase 3: 초격차 (Trailing Stop + 거래일지 + 텔레그램)
"""
import os
import time
import uuid
import json
import hashlib
import urllib.parse
import logging
import requests
from datetime import datetime
from typing import Dict, List, Optional

# [Phase 2] SecretVault import 방어
try:
    import jwt
except ImportError:
    jwt = None
    print("PyJWT not installed. Run: pip install PyJWT")

try:
    import sys
    sys.path.append(r"D:\CDR_SynologyDrive\10_업무\Internal_Library")
    from backend.security.vault import SecretVault
    HAS_VAULT = True
except Exception:
    HAS_VAULT = False

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger("AgenticScalper")

# ─── 설정 상수 ───────────────────────────────────────────────
BUDGET_KRW = 1_000_000          # 총 예산
POS_SIZE_KRW = 200_000          # 슬롯당 투입금
MAX_SLOTS = 5                   # 최대 동시 보유 종목 수
TP_PCT = 1.5                    # 익절 기준 (%)
SL_PCT = -1.0                   # 손절 기준 (%)
TRAILING_ACTIVATION_PCT = 1.0   # Trailing Stop 활성화 기준 (%)
TRAILING_DISTANCE_PCT = 0.7     # Trailing Stop 거리 (%)
TIME_CUT_HOURS = 4              # 시간 제한 (시간)
KIMCHI_PREMIUM_LIMIT = 5.0      # 김프 진입 차단 기준 (%)
VOLUME_THRESHOLD = 30_000_000_000  # 거래대금 최소 기준 (300억)
CHANGE_LIMIT = 1.0              # 변동률 매집 기준 (%)

STATE_FILE = "scalper_state.json"
TRADE_LOG_FILE = "TRADE_LOG.md"
REPORT_FILE = "SCALPER_STRATEGY_REPORT.md"

# ─── 텔레그램 설정 ───────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


class BithumbScalper:
    """Phase 1~3 전면 구현 프로덕션급 스캘핑 엔진"""

    def __init__(self):
        # API 키 로드 (환경변수 우선 → SecretVault 폴백)
        self.api_key = os.environ.get("BITHUMB_API_KEY")
        self.api_secret = os.environ.get("BITHUMB_SECRET_KEY")

        if (not self.api_key or not self.api_secret) and HAS_VAULT:
            logger.info("환경변수에 키 없음 → SecretVault 폴백")
            vault = SecretVault()
            self.api_key = vault.get("BITHUMB_API_KEY")
            self.api_secret = vault.get("BITHUMB_SECRET_KEY")

        if not self.api_key or not self.api_secret:
            logger.error("API 키를 찾을 수 없습니다. 환경변수 또는 .env.vault를 확인하세요.")

        # [Phase 1] 상태 영속화: 파일에서 로드
        self.state = self._load_state()

    # ═══════════════════════════════════════════════════════════
    # [Phase 1] 상태 영속화
    # ═══════════════════════════════════════════════════════════
    def _load_state(self) -> dict:
        """JSON 파일에서 포지션 상태를 복원"""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    state = json.load(f)
                logger.info(f"상태 복원 완료: {len(state.get('positions', {}))}개 포지션")
                return state
            except Exception as e:
                logger.warning(f"상태 파일 파싱 실패, 초기화: {e}")
        return {"positions": {}, "total_trades": 0, "total_profit_krw": 0}

    def _save_state(self):
        """현재 포지션 상태를 JSON 파일로 저장"""
        try:
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
            logger.info("상태 저장 완료")
        except Exception as e:
            logger.error(f"상태 저장 실패: {e}")

    # ═══════════════════════════════════════════════════════════
    # API 인증 및 주문
    # ═══════════════════════════════════════════════════════════
    def _get_headers_simple(self) -> dict:
        """GET 요청용 JWT 헤더"""
        payload = {
            'access_key': self.api_key,
            'nonce': str(uuid.uuid4()),
            'timestamp': int(time.time() * 1000)
        }
        token = jwt.encode(payload, self.api_secret, algorithm='HS256')
        return {'Authorization': 'Bearer ' + token}

    def _get_headers_with_query(self, params: dict) -> dict:
        """POST 요청용 JWT 헤더 (query_hash 포함)"""
        query_string = urllib.parse.urlencode(params)
        m = hashlib.sha512()
        m.update(query_string.encode('utf-8'))

        payload = {
            'access_key': self.api_key,
            'nonce': str(uuid.uuid4()),
            'timestamp': int(time.time() * 1000),
            'query_hash': m.hexdigest(),
            'query_hash_alg': 'SHA512',
        }
        token = jwt.encode(payload, self.api_secret, algorithm='HS256')
        return {'Authorization': 'Bearer ' + token}

    def get_accounts(self) -> list:
        """계좌 잔고 조회"""
        try:
            resp = requests.get(
                'https://api.bithumb.com/v1/accounts',
                headers=self._get_headers_simple(),
                timeout=10
            )
            return resp.json()
        except Exception as e:
            logger.error(f"계좌 조회 실패: {e}")
            return []

    def place_order(self, symbol: str, side: str, ord_type: str,
                    price: str = None, volume: str = None) -> dict:
        """
        빗썸 API 2.0 주문 실행
        side: bid(매수) / ask(매도)
        ord_type: limit(지정가) / price(시장가매수-총액) / market(시장가매도)
        """
        params = {
            'market': f'KRW-{symbol}',
            'side': side,
            'ord_type': ord_type,
        }
        if price: params['price'] = price
        if volume: params['volume'] = volume

        try:
            resp = requests.post(
                'https://api.bithumb.com/v1/orders',
                headers=self._get_headers_with_query(params),
                json=params,
                timeout=10
            )
            result = resp.json()
            logger.info(f"주문 실행: {side.upper()} {symbol} → {result.get('state', 'unknown')}")
            return result
        except Exception as e:
            logger.error(f"주문 실패 ({symbol}): {e}")
            return {"error": str(e)}

    # ═══════════════════════════════════════════════════════════
    # 시장 데이터 수집
    # ═══════════════════════════════════════════════════════════
    def get_bithumb_ticker(self, symbol: str = "ALL") -> dict:
        """빗썸 공개 시세 조회"""
        try:
            resp = requests.get(
                f"https://api.bithumb.com/public/ticker/{symbol}_KRW",
                timeout=10
            )
            return resp.json()
        except Exception as e:
            logger.error(f"빗썸 시세 조회 실패: {e}")
            return {}

    def get_binance_price(self, symbol: str) -> Optional[float]:
        """[Phase 2] 바이낸스 글로벌 시세 조회"""
        try:
            resp = requests.get(
                f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={symbol}USDT",
                timeout=5
            )
            data = resp.json()
            if 'price' in data:
                return float(data['price'])
        except Exception as e:
            logger.warning(f"바이낸스 시세 조회 실패 ({symbol}): {e}")
        return None

    def get_exchange_rate(self) -> float:
        """[Phase 2] USD/KRW 환율 조회"""
        try:
            resp = requests.get(
                "https://api.exchangerate-api.com/v4/latest/USD",
                timeout=5
            )
            return resp.json().get("rates", {}).get("KRW", 1400.0)
        except Exception:
            return 1400.0  # 폴백 환율

    # ═══════════════════════════════════════════════════════════
    # [Phase 2] 안티-매니퓰레이션 필터
    # ═══════════════════════════════════════════════════════════
    def check_kimchi_premium(self, symbol: str, bithumb_price: float) -> float:
        """빗썸-바이낸스 가격 괴리율 계산"""
        binance_usd = self.get_binance_price(symbol)
        if binance_usd is None:
            return 0.0  # 조회 불가 시 통과

        rate = self.get_exchange_rate()
        binance_krw = binance_usd * rate
        if binance_krw <= 0:
            return 0.0

        premium = ((bithumb_price / binance_krw) - 1) * 100
        return round(premium, 2)

    # ═══════════════════════════════════════════════════════════
    # [Phase 1] 종목 스캔 + [Phase 2] 필터링
    # ═══════════════════════════════════════════════════════════
    def scan_market(self) -> List[dict]:
        """매집 후보 종목 스캔 (거래량 + 변동률 + 김프 필터)"""
        data = self.get_bithumb_ticker("ALL")
        if data.get("status") != "0000":
            return []

        candidates = []
        for sym, t in data["data"].items():
            if sym == "date":
                continue
            try:
                change = float(t.get("fluctate_rate_24H", 0))
                volume = float(t.get("acc_trade_value_24H", 0))
                price = float(t["closing_price"])

                # 기본 필터: 거래량 300억+ & 변동률 ±1% 이내
                if volume < VOLUME_THRESHOLD or abs(change) > CHANGE_LIMIT:
                    continue

                # [Phase 2] 김프 체크
                kimchi = self.check_kimchi_premium(sym, price)
                if abs(kimchi) > KIMCHI_PREMIUM_LIMIT:
                    logger.warning(f"{sym} 김프 {kimchi}% → 진입 차단")
                    continue

                candidates.append({
                    "symbol": sym,
                    "price": price,
                    "volume": volume,
                    "change": change,
                    "kimchi": kimchi
                })
            except Exception as e:
                logger.debug(f"종목 {sym} 파싱 스킵: {e}")
                continue

        return sorted(candidates, key=lambda x: x["volume"], reverse=True)[:3]

    # ═══════════════════════════════════════════════════════════
    # Brain (MD) 타겟 파싱
    # ═══════════════════════════════════════════════════════════
    def get_brain_targets(self) -> List[str]:
        """전략 보고서(Brain)에서 AI 선정 타겟 추출"""
        targets = []
        if not os.path.exists(REPORT_FILE):
            return targets
        try:
            with open(REPORT_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    if "### 🎯" in line:
                        symbol = line.replace("### 🎯", "").strip()
                        if symbol:
                            targets.append(symbol)
            logger.info(f"Brain 타겟: {targets}")
        except Exception as e:
            logger.error(f"Brain 파싱 실패: {e}")
        return targets

    # ═══════════════════════════════════════════════════════════
    # [Phase 1] TP/SL 엔진 + [Phase 3] Trailing Stop
    # ═══════════════════════════════════════════════════════════
    def manage_positions(self):
        """보유 포지션 관리: TP, SL, Trailing Stop, Time Cut"""
        positions = self.state.get("positions", {})
        if not positions:
            logger.info("보유 포지션 없음 → 스킵")
            return

        ticker_data = self.get_bithumb_ticker("ALL")
        if ticker_data.get("status") != "0000":
            logger.error("시세 조회 실패 → 포지션 관리 스킵")
            return

        to_sell = []

        for symbol, pos in positions.items():
            if symbol not in ticker_data["data"]:
                continue

            current_price = float(ticker_data["data"][symbol]["closing_price"])
            entry_price = pos["entry_price"]
            profit_pct = ((current_price / entry_price) - 1) * 100
            entry_time = datetime.fromisoformat(pos["entry_time"])
            hours_held = (datetime.now() - entry_time).total_seconds() / 3600

            # [Phase 3] Trailing Stop 업데이트
            if profit_pct >= TRAILING_ACTIVATION_PCT:
                trailing_sl = current_price * (1 - TRAILING_DISTANCE_PCT / 100)
                current_sl = pos.get("trailing_sl", 0)
                if trailing_sl > current_sl:
                    pos["trailing_sl"] = trailing_sl
                    logger.info(f"[TRAILING] {symbol} SL 상향: {trailing_sl:,.0f}원")

            # 판단 로직
            sell_reason = None

            # 1. 고정 익절
            if profit_pct >= TP_PCT:
                sell_reason = f"TP 도달 ({profit_pct:.1f}%)"

            # 2. 고정 손절
            elif profit_pct <= SL_PCT:
                sell_reason = f"SL 발동 ({profit_pct:.1f}%)"

            # 3. Trailing Stop 발동
            elif pos.get("trailing_sl") and current_price <= pos["trailing_sl"]:
                sell_reason = f"Trailing SL 발동 ({profit_pct:.1f}%)"

            # 4. 시간 제한
            elif hours_held >= TIME_CUT_HOURS:
                sell_reason = f"Time Cut ({hours_held:.1f}h, {profit_pct:.1f}%)"

            if sell_reason:
                to_sell.append((symbol, sell_reason, profit_pct, current_price))

        # 매도 실행
        for symbol, reason, profit_pct, sell_price in to_sell:
            pos = positions[symbol]
            volume = str(pos["volume"])

            logger.info(f"🔔 매도 실행: {symbol} | 사유: {reason}")
            result = self.place_order(symbol, "ask", "market", volume=volume)

            if "error" not in result:
                profit_krw = pos["volume"] * (sell_price - pos["entry_price"])
                self.state["total_trades"] += 1
                self.state["total_profit_krw"] += profit_krw

                # [Phase 3] 거래 일지 기록
                self._log_trade("SELL", symbol, sell_price, pos["volume"], reason, profit_pct, profit_krw)

                # [Phase 3] 텔레그램 알림
                emoji = "💰" if profit_krw >= 0 else "🛑"
                self._send_telegram(
                    f"{emoji} {symbol} 매도 완료\n"
                    f"사유: {reason}\n"
                    f"수익: {profit_krw:+,.0f}원 ({profit_pct:+.1f}%)\n"
                    f"누적 수익: {self.state['total_profit_krw']:+,.0f}원"
                )

                del positions[symbol]

        self._save_state()

    # ═══════════════════════════════════════════════════════════
    # [Phase 1] 매수 실행
    # ═══════════════════════════════════════════════════════════
    def execute_entries(self):
        """신규 매수 실행"""
        positions = self.state.get("positions", {})
        open_slots = MAX_SLOTS - len(positions)

        if open_slots <= 0:
            logger.info(f"슬롯 만석 ({len(positions)}/{MAX_SLOTS}) → 매수 스킵")
            return

        # Brain 타겟 + 시장 스캔 결합
        brain_targets = self.get_brain_targets()
        market_candidates = self.scan_market()
        market_symbols = [c["symbol"] for c in market_candidates]

        # Brain에서 추천하고 시장 스캔에서도 통과한 종목 우선
        final_targets = [t for t in brain_targets if t in market_symbols]
        # Brain에만 있는 종목 추가
        for t in brain_targets:
            if t not in final_targets:
                final_targets.append(t)
        # 시장 스캔에서만 나온 종목 추가
        for c in market_candidates:
            if c["symbol"] not in final_targets:
                final_targets.append(c["symbol"])

        for symbol in final_targets[:open_slots]:
            if symbol in positions:
                continue

            # 현재가 조회
            ticker = self.get_bithumb_ticker(symbol)
            if ticker.get("status") != "0000":
                continue
            current_price = float(ticker["data"]["closing_price"])

            # [Phase 1] 실전 매수 (시장가, 총액 기준)
            logger.info(f"📈 매수 시도: {symbol} @ {current_price:,.0f}원 (₩{POS_SIZE_KRW:,})")
            result = self.place_order(symbol, "bid", "price", price=str(POS_SIZE_KRW))

            if "error" not in result and result.get("uuid"):
                volume = POS_SIZE_KRW / current_price
                positions[symbol] = {
                    "entry_price": current_price,
                    "volume": volume,
                    "entry_time": datetime.now().isoformat(),
                    "trailing_sl": 0,
                    "order_uuid": result.get("uuid", "")
                }
                logger.info(f"✅ 매수 체결: {symbol} {volume:.4f}개 @ {current_price:,.0f}원")

                # [Phase 3] 거래 일지 기록
                self._log_trade("BUY", symbol, current_price, volume, "Brain+Market Signal", 0, 0)

                # [Phase 3] 텔레그램 알림
                self._send_telegram(
                    f"📈 {symbol} 매수 체결!\n"
                    f"가격: {current_price:,.0f}원\n"
                    f"수량: {volume:.4f}개\n"
                    f"투입금: ₩{POS_SIZE_KRW:,}"
                )

        self._save_state()

    # ═══════════════════════════════════════════════════════════
    # [Phase 3] 거래 일지 자동 기록
    # ═══════════════════════════════════════════════════════════
    def _log_trade(self, action: str, symbol: str, price: float,
                   volume: float, reason: str, profit_pct: float, profit_krw: float):
        """TRADE_LOG.md에 거래 내역 추가"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        emoji = "🟢" if action == "BUY" else ("💰" if profit_krw >= 0 else "🔴")

        entry = (
            f"\n### {emoji} {action} {symbol} ({now})\n"
            f"- **가격**: {price:,.0f} KRW\n"
            f"- **수량**: {volume:.4f}\n"
            f"- **사유**: {reason}\n"
        )
        if action == "SELL":
            entry += (
                f"- **수익률**: {profit_pct:+.1f}%\n"
                f"- **수익금**: {profit_krw:+,.0f} KRW\n"
            )

        try:
            # 파일이 없으면 헤더 생성
            if not os.path.exists(TRADE_LOG_FILE):
                with open(TRADE_LOG_FILE, "w", encoding="utf-8") as f:
                    f.write("# 📒 ChoiGPT Auto-Scalper 거래 일지\n\n")

            with open(TRADE_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(entry)
            logger.info(f"거래 일지 기록: {action} {symbol}")
        except Exception as e:
            logger.error(f"거래 일지 기록 실패: {e}")

    # ═══════════════════════════════════════════════════════════
    # [Phase 3] 텔레그램 알림
    # ═══════════════════════════════════════════════════════════
    def _send_telegram(self, message: str):
        """텔레그램 봇으로 알림 전송"""
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            return  # 미설정 시 무시

        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            requests.post(url, json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": f"[ChoiGPT Scalper]\n{message}",
                "parse_mode": "HTML"
            }, timeout=5)
        except Exception as e:
            logger.warning(f"텔레그램 전송 실패: {e}")

    # ═══════════════════════════════════════════════════════════
    # 메인 사이클
    # ═══════════════════════════════════════════════════════════
    def run_cycle(self):
        """1회 매매 사이클 실행"""
        logger.info("═══ Agentic Scalping Cycle Started ═══")
        logger.info(f"보유: {len(self.state['positions'])}개 | "
                     f"누적 거래: {self.state['total_trades']}건 | "
                     f"누적 수익: {self.state['total_profit_krw']:+,.0f}원")

        # Step 1: 기존 포지션 관리 (TP/SL/Trailing/TimeCut)
        self.manage_positions()

        # Step 2: 신규 매수 실행
        self.execute_entries()

        logger.info("═══ Cycle Complete ═══\n")


# ═══════════════════════════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    scalper = BithumbScalper()
    scalper.run_cycle()
