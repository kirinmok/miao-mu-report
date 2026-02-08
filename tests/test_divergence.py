"""
Test Case v13: 外資買、股價跌的背離情境
驗證 v13 Spec 合規性：衝突強度、雙層語言、0-100 信心度
"""

import json
from modules.role_analyzers import MultiRoleAnalyzer

def test_divergence_v13():
    """
    測試情境：
    - 外資連續5日買超 8,500 張
    - 但股價近5日下跌 6%
    - 技術面：跌破季線、MACD 死叉
    - 基本面：無明顯利多
    """
    print("=" * 70)
    print("🧪 v13 測試：外資買超 + 股價下跌 (背離情境)")
    print("=" * 70)
    
    analyzer = MultiRoleAnalyzer()
    
    result = analyzer.analyze(
        # 籌碼 (外資強買)
        foreign_net_volume=8500,
        positive_days=5,
        trust_net_volume=-2000,
        dealer_net_volume=-1000,
        # 技術 (股價跌)
        close=95.0,
        ma60=100.0,
        ma20=98.0,
        rsi=38.0,
        macd_diff=-0.5,
        price_change_5d=-6.0,
        # 情境 (無催化劑)
        has_positive_news=False,
        has_negative_news=False,
        sector_trend="flat",
        market_sentiment="neutral",
        has_catalyst=False
    )
    
    # 1. 各角色輸出
    print("\n📊 各角色獨立分析:")
    print("-" * 70)
    for role in result['role_outputs']:
        dir_map = {"bullish": "偏多", "bearish": "偏空", "neutral": "中性"}
        print(f"\n【{role['role_name']}】")
        print(f"  方向: {dir_map.get(role['role_conclusion'], role['role_conclusion'])}")
        print(f"  信心: {role['confidence']}%")
        print(f"  證據: {', '.join(role['key_evidence'][:2])}...")
    
    # 2. 衝突報告
    print("\n" + "=" * 70)
    print("⚔️ 衝突分析 (v13):")
    print("-" * 70)
    cr = result['conflict_resolution']
    print(f"  衝突偵測: {'是 ⚠️' if cr['has_conflict'] else '否'}")
    print(f"  衝突強度: {cr['conflict_intensity']:.2f} (0=無, 1=極高)")
    print(f"  衝突角色: {', '.join(cr['conflict_roles'])}")
    
    # 3. 雙層語言摘要 (v13 核心)
    print("\n" + "=" * 70)
    print("🧠 雙層語言輸出 (v13 核心):")
    print("-" * 70)
    print(f"\n🟢 人話版本 (給阿公阿嬤):")
    print(f"   「{result['summary_human']}」")
    print(f"\n🔵 專業版本 (給進階用戶):")
    print(f"   「{result['summary_professional']}」")
    
    # 4. 最終結論
    print("\n" + "=" * 70)
    print("🎯 最終整合結論:")
    print("-" * 70)
    dir_map = {"bullish": "偏多", "bearish": "偏空", "neutral": "中性"}
    print(f"  方向: {dir_map.get(result['final_direction'], result['final_direction'])}")
    print(f"  信心: {result['confidence']}%")
    print(f"  整合理由: {result['integration_reason']}")
    
    # 5. 完整 JSON
    print("\n" + "=" * 70)
    print("📄 完整 JSON (v13 Spec):")
    print("-" * 70)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 6. 驗證
    print("\n" + "=" * 70)
    print("✅ v13 Spec 合規驗證:")
    print("-" * 70)
    
    # 必須欄位檢查
    assert "final_direction" in result
    assert "confidence" in result
    assert "summary_human" in result
    assert "summary_professional" in result
    assert "conflict_intensity" in result
    assert "role_outputs" in result
    assert "conflict_resolution" in result
    print("   ✓ 所有必須欄位存在")
    
    # 信心度 0-100
    assert 0 <= result['confidence'] <= 100
    for r in result['role_outputs']:
        assert 0 <= r['confidence'] <= 100
    print("   ✓ 信心度為 0-100 格式")
    
    # 衝突強度 0-1
    assert 0 <= cr['conflict_intensity'] <= 1
    print("   ✓ 衝突強度為 0.0-1.0 格式")
    
    # 雙層語言存在
    assert len(result['summary_human']) > 10
    assert len(result['summary_professional']) > 10
    print("   ✓ 雙層語言摘要已生成")
    
    # 衝突偵測
    assert cr['has_conflict'] == True
    print("   ✓ 正確偵測到籌碼/技術背離衝突")
    
    chip = next(r for r in result['role_outputs'] if r['role_name'] == '籌碼分析官')
    tech = next(r for r in result['role_outputs'] if r['role_name'] == '技術分析官')
    assert chip['role_conclusion'] == 'bullish'
    assert tech['role_conclusion'] == 'bearish'
    print("   ✓ 籌碼官偏多 / 技術官偏空 (背離確認)")
    
    print("\n🎉 v13 Spec 驗證全部通過！")
    return result


if __name__ == "__main__":
    test_divergence_v13()
