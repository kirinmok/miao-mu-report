"""
喵姆 AI 多角色分析架構 (v13.0)
Multi-Role Stock Analyzer - Official Specification Compliant

設計原則：
1. 真分工：角色獨立，不共享結論
2. 衝突是常態：主動偵測，不強制平均
3. 雙層語言：人話版本 + 專業版本
"""

from dataclasses import dataclass, field, asdict
from typing import List, Literal, Optional
from enum import Enum


# ============================================================
# 1. 標準輸出資料結構 (v13 Spec Compliant)
# ============================================================

class Direction(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


@dataclass
class RoleOutput:
    """每個分析角色的標準輸出格式 (v13)"""
    role_name: str                          # 角色名稱
    role_conclusion: Direction              # 方向判斷
    confidence: int                         # 信心度 0-100 (per spec)
    key_evidence: List[str] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d['role_conclusion'] = self.role_conclusion.value
        return d


@dataclass
class ConflictReport:
    """衝突分析報告 (v13)"""
    has_conflict: bool
    conflict_intensity: float               # 0.0-1.0 衝突強度 (v13 新增)
    conflict_roles: List[str]
    conflict_summary: str
    integration_reason: str
    final_direction: Direction
    final_confidence: int                   # 0-100
    
    def to_dict(self) -> dict:
        d = asdict(self)
        d['final_direction'] = self.final_direction.value
        return d


# ============================================================
# 2. 動態權重接口 (v13 擴充)
# ============================================================

def get_role_weights(market_state: str = "normal") -> dict:
    """
    動態角色權重 - 依市場狀態調整
    
    Args:
        market_state: "normal" | "consolidation" | "event_driven"
    """
    if market_state == "consolidation":
        # 盤整期：技術官權重↓，情境官權重↑
        return {"籌碼分析官": 0.30, "技術分析官": 0.30, "情境分析官": 0.40}
    elif market_state == "event_driven":
        # 事件期：籌碼官權重↑
        return {"籌碼分析官": 0.45, "技術分析官": 0.25, "情境分析官": 0.30}
    else:
        return {"籌碼分析官": 0.35, "技術分析官": 0.40, "情境分析官": 0.25}


# ============================================================
# 3. 分析角色實作
# ============================================================

class ChipAnalyzer:
    """
    📊 籌碼分析官
    
    關注：外資/投信/自營商行為、連續性、力道
    禁止：不看價格線型、不推測技術型態
    """
    
    ROLE_NAME = "籌碼分析官"
    
    def analyze(self, foreign_net_volume: int, positive_days: int, 
                trust_net_volume: int = 0, dealer_net_volume: int = 0) -> RoleOutput:
        evidence = []
        confidence = 50  # 基準 50
        
        # 外資判斷 (不看價格!)
        if foreign_net_volume > 5000 and positive_days >= 4:
            direction = Direction.BULLISH
            confidence = 80
            evidence.append(f"外資連{positive_days}日買超，合計 {foreign_net_volume:,} 張")
        elif foreign_net_volume < -5000 and positive_days <= 1:
            direction = Direction.BEARISH
            confidence = 80
            evidence.append(f"外資連續倒貨，合計賣超 {abs(foreign_net_volume):,} 張")
        else:
            direction = Direction.NEUTRAL
            confidence = 40
            evidence.append(f"外資動向不明確 (淨量 {foreign_net_volume:,} 張)")
        
        # 三大法人一致性
        total_inst = foreign_net_volume + trust_net_volume + dealer_net_volume
        if total_inst > 0 and foreign_net_volume > 0:
            evidence.append("三大法人同步買超")
            confidence = min(100, confidence + 10)
        elif total_inst < 0 and foreign_net_volume > 0:
            evidence.append("⚠️ 法人內部分歧：外資買、投信/自營賣")
            confidence = max(0, confidence - 10)
        
        return RoleOutput(
            role_name=self.ROLE_NAME,
            role_conclusion=direction,
            confidence=confidence,
            key_evidence=evidence,
            raw_data={
                "foreign_net": foreign_net_volume,
                "positive_days": positive_days,
                "trust_net": trust_net_volume,
                "dealer_net": dealer_net_volume
            }
        )


class TechAnalyzer:
    """
    📉 技術分析官
    
    關注：價格趨勢、均線位置、RSI/MACD/成交量
    禁止：不解讀外資動機、不假設基本面利多
    """
    
    ROLE_NAME = "技術分析官"
    
    def analyze(self, close: float, ma60: float, ma20: float,
                rsi: float, macd_diff: float, 
                price_change_5d: float, volume_ratio: float = 1.0) -> RoleOutput:
        evidence = []
        score = 0  # -4 to +4
        
        # 均線位置 (純技術，不猜原因)
        if close > ma60:
            score += 1
            evidence.append("股價站上季線 ✓")
        else:
            score -= 1
            evidence.append("股價跌破季線 ✗")
        
        if close > ma20:
            score += 0.5
        else:
            score -= 0.5
            evidence.append("股價跌破月線")
        
        # MACD
        if macd_diff > 0:
            score += 1
            evidence.append("MACD 多頭排列")
        else:
            score -= 1
            evidence.append("MACD 死叉")
        
        # RSI
        if rsi > 70:
            evidence.append(f"RSI({rsi:.0f}) 過熱區")
            score -= 0.5
        elif rsi < 30:
            evidence.append(f"RSI({rsi:.0f}) 超賣區")
            score += 0.5
        
        # 近期走勢
        if price_change_5d < -5:
            evidence.append(f"近5日跌幅 {price_change_5d:.1f}%")
            score -= 1
        elif price_change_5d > 5:
            evidence.append(f"近5日漲幅 +{price_change_5d:.1f}%")
            score += 0.5
        
        # 決定方向與信心
        if score >= 1.5:
            direction = Direction.BULLISH
            confidence = min(90, 50 + int(score * 10))
        elif score <= -1.5:
            direction = Direction.BEARISH
            confidence = min(90, 50 + int(abs(score) * 10))
        else:
            direction = Direction.NEUTRAL
            confidence = 35
        
        return RoleOutput(
            role_name=self.ROLE_NAME,
            role_conclusion=direction,
            confidence=confidence,
            key_evidence=evidence,
            raw_data={
                "close": close,
                "ma60": ma60,
                "ma20": ma20,
                "rsi": rsi,
                "macd_diff": macd_diff,
                "price_change_5d": price_change_5d,
                "tech_score": score
            }
        )


class ContextAnalyzer:
    """
    🌐 情境分析官
    
    關注：基本面事件、產業循環、政策/財報/新聞
    禁止：不解讀短線價量、不推測籌碼行為
    """
    
    ROLE_NAME = "情境分析官"
    
    def analyze(self, has_positive_news: bool = False, 
                has_negative_news: bool = False,
                sector_trend: Literal["up", "down", "flat"] = "flat",
                market_sentiment: Literal["bullish", "bearish", "neutral"] = "neutral",
                has_catalyst: bool = False) -> RoleOutput:
        evidence = []
        score = 0
        
        # 基本面 (不看價量)
        if has_positive_news:
            score += 1
            evidence.append("基本面有利多消息")
        elif has_negative_news:
            score -= 1
            evidence.append("基本面有利空消息")
        else:
            evidence.append("基本面無明顯催化劑")
        
        # 產業循環
        if sector_trend == "up":
            score += 0.5
            evidence.append("產業處於上升趨勢")
        elif sector_trend == "down":
            score -= 0.5
            evidence.append("產業處於下行循環")
        
        # 大盤情緒
        if market_sentiment == "bullish":
            score += 0.5
            evidence.append("大盤情緒偏多")
        elif market_sentiment == "bearish":
            score -= 0.5
            evidence.append("大盤情緒偏空")
        
        # 催化劑
        if has_catalyst:
            evidence.append("存在近期催化劑事件")
            score += 0.3
        
        if score >= 1:
            direction = Direction.BULLISH
            confidence = 60
        elif score <= -1:
            direction = Direction.BEARISH
            confidence = 60
        else:
            direction = Direction.NEUTRAL
            confidence = 40
        
        return RoleOutput(
            role_name=self.ROLE_NAME,
            role_conclusion=direction,
            confidence=confidence,
            key_evidence=evidence,
            raw_data={
                "has_positive_news": has_positive_news,
                "has_negative_news": has_negative_news,
                "sector_trend": sector_trend,
                "market_sentiment": market_sentiment,
                "has_catalyst": has_catalyst,
                "context_score": score
            }
        )


# ============================================================
# 4. 衝突解決器 (v13 with intensity)
# ============================================================

class ConflictResolver:
    """
    ⚔️ 衝突解決器
    
    - 偵測角色間方向衝突
    - 計算 conflict_intensity (0.0-1.0)
    - 產生雙層語言摘要
    """
    
    def resolve(self, role_outputs: List[RoleOutput], 
                market_state: str = "normal") -> ConflictReport:
        
        # 動態權重
        weights = get_role_weights(market_state)
        
        # 1. 蒐集方向 (排除 Neutral)
        directions = {r.role_name: r.role_conclusion for r in role_outputs}
        confidences = {r.role_name: r.confidence for r in role_outputs}
        
        non_neutral_dirs = {n: d for n, d in directions.items() if d != Direction.NEUTRAL}
        unique_dirs = set(non_neutral_dirs.values())
        
        # 2. 衝突偵測
        has_conflict = len(unique_dirs) > 1
        conflict_roles = list(non_neutral_dirs.keys()) if has_conflict else []
        
        # 3. 計算衝突強度 (v13)
        if has_conflict:
            # 衝突強度 = 衝突角色的平均信心度 / 100
            conflict_confidences = [confidences[r] for r in conflict_roles]
            conflict_intensity = round(sum(conflict_confidences) / len(conflict_confidences) / 100, 2)
        else:
            conflict_intensity = 0.0
        
        # 4. 加權計算最終方向
        weighted_score = 0.0
        for r in role_outputs:
            weight = weights.get(r.role_name, 0.33)
            if r.role_conclusion == Direction.BULLISH:
                weighted_score += weight * (r.confidence / 100)
            elif r.role_conclusion == Direction.BEARISH:
                weighted_score -= weight * (r.confidence / 100)
        
        # 5. 決定最終方向
        if weighted_score >= 0.15:
            final_direction = Direction.BULLISH
        elif weighted_score <= -0.15:
            final_direction = Direction.BEARISH
        else:
            final_direction = Direction.NEUTRAL
        
        final_confidence = int(min(100, abs(weighted_score) * 100))
        
        # 6. 產生衝突摘要
        if has_conflict:
            dir_map = {"bullish": "偏多", "bearish": "偏空", "neutral": "中性"}
            dir_strs = [f"{n}({dir_map[d.value]})" for n, d in directions.items()]
            conflict_summary = f"角色分歧: {' vs '.join(dir_strs)}"
            
            # 特殊情境整合理由
            chip_dir = directions.get("籌碼分析官")
            tech_dir = directions.get("技術分析官")
            
            if chip_dir == Direction.BULLISH and tech_dir == Direction.BEARISH:
                integration_reason = (
                    "外資買進但股價下跌，賣壓大於承接力。"
                    "可能：1)投信/自營同賣 2)散戶恐慌 3)外資慢接非掃貨。"
                    "建議等待止跌訊號。"
                )
            elif chip_dir == Direction.BEARISH and tech_dir == Direction.BULLISH:
                integration_reason = (
                    "法人賣出但股價上漲，散戶接盤撐價。"
                    "須警惕後續賣壓消化問題。"
                )
            else:
                integration_reason = "多維度分歧，採信心度加權整合。"
        else:
            conflict_summary = "各角色判斷一致"
            integration_reason = "無衝突，採共識方向。"
        
        return ConflictReport(
            has_conflict=has_conflict,
            conflict_intensity=conflict_intensity,
            conflict_roles=conflict_roles,
            conflict_summary=conflict_summary,
            integration_reason=integration_reason,
            final_direction=final_direction,
            final_confidence=final_confidence
        )


# ============================================================
# 5. 雙層語言產生器 (v13)
# ============================================================

class SummaryGenerator:
    """產生雙層語言摘要"""
    
    @staticmethod
    def generate(conflict_report: ConflictReport, 
                 role_outputs: List[RoleOutput]) -> tuple:
        """
        Returns:
            (summary_human, summary_professional)
        """
        direction = conflict_report.final_direction
        has_conflict = conflict_report.has_conflict
        chip_out = next((r for r in role_outputs if r.role_name == "籌碼分析官"), None)
        tech_out = next((r for r in role_outputs if r.role_name == "技術分析官"), None)
        
        # 🟢 人話版本 (80歲可懂)
        if has_conflict:
            if chip_out and tech_out:
                if chip_out.role_conclusion == Direction.BULLISH and tech_out.role_conclusion == Direction.BEARISH:
                    summary_human = "雖然外資有在買，但股價一直跌，代表市場賣壓還很重，現在追進風險高。"
                elif chip_out.role_conclusion == Direction.BEARISH and tech_out.role_conclusion == Direction.BULLISH:
                    summary_human = "外資有在賣，但股價還撐著，可能是散戶在接，要小心後面沒人買。"
                else:
                    summary_human = "專家意見不一致，現在局勢不明，建議先觀望。"
            else:
                summary_human = "分析結果有分歧，建議等局勢明朗再行動。"
        else:
            if direction == Direction.BULLISH:
                summary_human = "各項指標都偏正面，屬於相對安全的機會。"
            elif direction == Direction.BEARISH:
                summary_human = "各項指標都偏負面，現在進場風險較高。"
            else:
                summary_human = "目前多空不明，建議持續觀察。"
        
        # 🔵 專業版本 (因果+指標)
        if has_conflict:
            if chip_out and tech_out:
                if chip_out.role_conclusion == Direction.BULLISH and tech_out.role_conclusion == Direction.BEARISH:
                    summary_professional = (
                        f"外資連續買超未能推升股價，顯示賣壓大於承接力，"
                        f"屬典型籌碼與技術背離情境。"
                        f"建議等待技術面止穩訊號後再評估進場時機。"
                    )
                elif chip_out.role_conclusion == Direction.BEARISH and tech_out.role_conclusion == Direction.BULLISH:
                    summary_professional = (
                        f"技術面維持多頭結構，但法人持續調節，"
                        f"需警惕籌碼面轉弱後的補跌風險。"
                    )
                else:
                    summary_professional = f"多維度分析結果分歧，綜合評估後方向：{direction.value}。"
            else:
                summary_professional = "分析維度不完整，建議補充資料後重新評估。"
        else:
            if direction == Direction.BULLISH:
                summary_professional = "籌碼、技術、情境三維度均偏多，風險報酬比相對有利。"
            elif direction == Direction.BEARISH:
                summary_professional = "籌碼、技術、情境三維度均偏空，短期內宜保守操作。"
            else:
                summary_professional = "多空力道均衡，建議觀望等待方向訊號。"
        
        return summary_human, summary_professional


# ============================================================
# 6. 整合分析器 (Orchestrator v13)
# ============================================================

class MultiRoleAnalyzer:
    """
    多角色分析協調器 (v13)
    
    完整流程：
    1. 各角色獨立分析
    2. 衝突偵測與整合
    3. 雙層語言摘要
    4. 輸出符合 v13 Spec 的完整結構
    """
    
    def __init__(self):
        self.chip_analyzer = ChipAnalyzer()
        self.tech_analyzer = TechAnalyzer()
        self.context_analyzer = ContextAnalyzer()
        self.conflict_resolver = ConflictResolver()
        self.summary_generator = SummaryGenerator()
    
    def analyze(self, 
                # 籌碼數據
                foreign_net_volume: int,
                positive_days: int,
                trust_net_volume: int = 0,
                dealer_net_volume: int = 0,
                # 技術數據
                close: float = 100.0,
                ma60: float = 100.0,
                ma20: float = 100.0,
                rsi: float = 50.0,
                macd_diff: float = 0.0,
                price_change_5d: float = 0.0,
                # 情境數據
                has_positive_news: bool = False,
                has_negative_news: bool = False,
                sector_trend: str = "flat",
                market_sentiment: str = "neutral",
                has_catalyst: bool = False,
                # 系統參數
                market_state: str = "normal") -> dict:
        """
        執行完整多角色分析
        
        Returns:
            符合 v13 Spec 的完整輸出結構
        """
        
        # 1. 各角色獨立分析 (真分工, 不共享)
        chip_result = self.chip_analyzer.analyze(
            foreign_net_volume, positive_days, trust_net_volume, dealer_net_volume
        )
        
        tech_result = self.tech_analyzer.analyze(
            close, ma60, ma20, rsi, macd_diff, price_change_5d
        )
        
        context_result = self.context_analyzer.analyze(
            has_positive_news, has_negative_news, sector_trend, market_sentiment, has_catalyst
        )
        
        all_roles = [chip_result, tech_result, context_result]
        
        # 2. 衝突偵測與整合
        conflict_report = self.conflict_resolver.resolve(all_roles, market_state)
        
        # 3. 雙層語言摘要
        summary_human, summary_professional = self.summary_generator.generate(
            conflict_report, all_roles
        )
        
        # 4. 組裝 v13 Spec 輸出
        return {
            "final_direction": conflict_report.final_direction.value,
            "confidence": conflict_report.final_confidence,
            "summary_human": summary_human,
            "summary_professional": summary_professional,
            "integration_reason": conflict_report.integration_reason,
            "conflict_intensity": conflict_report.conflict_intensity,
            "role_outputs": [r.to_dict() for r in all_roles],
            "conflict_resolution": conflict_report.to_dict()
        }
