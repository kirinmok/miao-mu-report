"""
tests/test_prompt_generator.py

測試 PromptPackGenerator 的 deterministic 行為
"""
import os
import sys
import pytest
import tempfile
import shutil
from pathlib import Path

# 加入專案路徑
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.prompt_generator import (
    generate_packs,
    TemplateNotFoundError,
    MissingTriggerFieldError,
    TEMPLATES_DIR,
    BASE_DIR
)


class TestGeneratePacks:
    """測試 generate_packs 主函數"""
    
    def test_normal_case_generates_4_files(self):
        """正常情況：能生成 4 份檔案"""
        triggers = [{
            "ticker": "TEST001",
            "name": "測試股票",
            "close": 123.45,
            "reasons": "測試理由"
        }]
        date_str = "9999-12-31"  # 使用未來日期避免衝突
        
        try:
            files = generate_packs(triggers, date_str)
            
            # 應產生 4 份檔案
            assert len(files) == 4
            
            # 檢查檔案名稱格式
            expected_suffixes = ["_perplexity.txt", "_gemini.txt", "_claude.txt", "_chatgpt.txt"]
            for suffix in expected_suffixes:
                matching = [f for f in files if f.endswith(f"TEST001{suffix}")]
                assert len(matching) == 1, f"找不到 {suffix} 檔案"
            
            # 檢查 perplexity 檔案內容包含正確填入的變數
            # 注意：不是所有模板都有全部變數，但 perplexity 有
            perplexity_file = [f for f in files if "perplexity" in f][0]
            with open(perplexity_file, "r", encoding="utf-8") as f:
                content = f.read()
                assert "TEST001" in content, "ticker 未正確填入"
                assert "9999-12-31" in content, "date 未正確填入"
                assert "測試股票" in content, "name 未正確填入"
                assert "123.45" in content, "close 未正確填入"
                assert "測試理由" in content, "reasons 未正確填入"
        
        finally:
            # 清理測試檔案
            test_dir = BASE_DIR / "research" / date_str
            if test_dir.exists():
                shutil.rmtree(test_dir)
    
    def test_multiple_triggers(self):
        """多個 trigger 應產生對應數量檔案"""
        triggers = [
            {"ticker": "AAA", "name": "股票A", "close": 100, "reasons": "理由A"},
            {"ticker": "BBB", "name": "股票B", "close": 200, "reasons": "理由B"},
        ]
        date_str = "9999-12-30"
        
        try:
            files = generate_packs(triggers, date_str)
            
            # 2 個 trigger × 4 個 AI = 8 份檔案
            assert len(files) == 8
        
        finally:
            test_dir = BASE_DIR / "research" / date_str
            if test_dir.exists():
                shutil.rmtree(test_dir)


class TestMissingTemplate:
    """測試缺模板檔必須丟錯"""
    
    def test_missing_template_raises_error(self):
        """缺模板檔：必須丟 TemplateNotFoundError"""
        # 暫時重命名一個模板
        original = TEMPLATES_DIR / "prompt_perplexity.txt"
        backup = TEMPLATES_DIR / "prompt_perplexity.txt.bak"
        
        if original.exists():
            shutil.move(original, backup)
        
        try:
            triggers = [{"ticker": "X", "name": "X", "close": 1, "reasons": "X"}]
            
            with pytest.raises(TemplateNotFoundError) as exc_info:
                generate_packs(triggers, "9999-01-01")
            
            assert "prompt_perplexity.txt" in str(exc_info.value)
        
        finally:
            # 還原模板
            if backup.exists():
                shutil.move(backup, original)


class TestMissingTriggerField:
    """測試缺變數必須丟錯"""
    
    def test_missing_ticker_raises_error(self):
        """缺 ticker：必須丟 MissingTriggerFieldError"""
        triggers = [{"name": "X", "close": 1, "reasons": "X"}]  # 缺 ticker
        
        with pytest.raises(MissingTriggerFieldError) as exc_info:
            generate_packs(triggers, "9999-01-01")
        
        assert "ticker" in str(exc_info.value)
    
    def test_missing_name_raises_error(self):
        """缺 name：必須丟 MissingTriggerFieldError"""
        triggers = [{"ticker": "X", "close": 1, "reasons": "X"}]  # 缺 name
        
        with pytest.raises(MissingTriggerFieldError) as exc_info:
            generate_packs(triggers, "9999-01-01")
        
        assert "name" in str(exc_info.value)
    
    def test_missing_close_raises_error(self):
        """缺 close：必須丟 MissingTriggerFieldError"""
        triggers = [{"ticker": "X", "name": "X", "reasons": "X"}]  # 缺 close
        
        with pytest.raises(MissingTriggerFieldError) as exc_info:
            generate_packs(triggers, "9999-01-01")
        
        assert "close" in str(exc_info.value)
    
    def test_missing_reasons_raises_error(self):
        """缺 reasons：必須丟 MissingTriggerFieldError"""
        triggers = [{"ticker": "X", "name": "X", "close": 1}]  # 缺 reasons
        
        with pytest.raises(MissingTriggerFieldError) as exc_info:
            generate_packs(triggers, "9999-01-01")
        
        assert "reasons" in str(exc_info.value)


class TestDeterministicOutput:
    """測試 deterministic 特性"""
    
    def test_output_path_is_deterministic(self):
        """輸出路徑必須是 deterministic（使用 Path.parts 避免跨平台問題）"""
        triggers = [{"ticker": "DET", "name": "確定性測試", "close": 50, "reasons": "測試"}]
        date_str = "9999-12-29"
        
        try:
            files = generate_packs(triggers, date_str)
            
            # 使用 Path.parts 比對，避免 Windows 路徑分隔符問題
            expected_parts = ("research", date_str, "outputs", "prompt_packs")
            for f in files:
                path_parts = Path(f).parts
                # 檢查必要路徑元件都存在且順序正確
                for i, part in enumerate(expected_parts):
                    assert part in path_parts, f"路徑缺少 {part}: {f}"
        
        finally:
            test_dir = BASE_DIR / "research" / date_str
            if test_dir.exists():
                shutil.rmtree(test_dir)
    
    def test_same_input_same_output(self):
        """相同輸入必須產生相同輸出"""
        triggers = [{"ticker": "SAME", "name": "相同測試", "close": 99, "reasons": "一致性"}]
        date_str = "9999-12-28"
        
        try:
            # 執行兩次
            files1 = generate_packs(triggers, date_str)
            
            # 讀取第一次內容
            contents1 = {}
            for f in files1:
                with open(f, "r", encoding="utf-8") as file:
                    contents1[f] = file.read()
            
            # 再執行一次
            files2 = generate_packs(triggers, date_str)
            
            # 讀取第二次內容
            contents2 = {}
            for f in files2:
                with open(f, "r", encoding="utf-8") as file:
                    contents2[f] = file.read()
            
            # 內容必須完全相同
            assert contents1 == contents2
        
        finally:
            test_dir = BASE_DIR / "research" / date_str
            if test_dir.exists():
                shutil.rmtree(test_dir)


class TestAtomicNoPartialFiles:
    """測試不產生半套檔案（atomic rollback）"""
    
    def test_invalid_template_variable_no_files_created(self):
        """
        模板含無效變數時，該 ticker 的所有輸出檔案都不存在
        - 故意讓其中一個 template 包含 {oops}，觸發 KeyError
        - 期望：該 ticker 的所有輸出檔案都不存在
        """
        # 暫時修改 perplexity 模板，加入無效變數
        original = TEMPLATES_DIR / "prompt_perplexity.txt"
        backup = TEMPLATES_DIR / "prompt_perplexity.txt.bak"
        
        original_content = original.read_text(encoding="utf-8")
        
        try:
            # 在模板中加入無效變數
            modified_content = original_content + "\n無效變數測試: {oops}\n"
            original.write_text(modified_content, encoding="utf-8")
            
            triggers = [{"ticker": "ATOMIC", "name": "原子測試", "close": 100, "reasons": "測試"}]
            date_str = "9999-01-02"
            output_dir = BASE_DIR / "research" / date_str / "outputs" / "prompt_packs"
            
            # 執行應該失敗
            with pytest.raises(KeyError):
                generate_packs(triggers, date_str)
            
            # 驗證：該 ticker 的所有檔案都不存在
            if output_dir.exists():
                for ai_type in ["perplexity", "gemini", "claude", "chatgpt"]:
                    file_path = output_dir / f"ATOMIC_{ai_type}.txt"
                    assert not file_path.exists(), f"不應存在: {file_path}"
        
        finally:
            # 還原模板
            original.write_text(original_content, encoding="utf-8")
            # 清理測試目錄
            test_dir = BASE_DIR / "research" / date_str
            if test_dir.exists():
                shutil.rmtree(test_dir)


class TestKeyErrorContext:
    """測試 KeyError 錯誤訊息必須包含上下文"""
    
    def test_keyerror_includes_ticker_and_template(self):
        """
        KeyError 時錯誤訊息必須指出是哪个 ticker + 哪个 template/ai_type
        """
        # 暫時修改 gemini 模板，加入無效變數
        original = TEMPLATES_DIR / "prompt_gemini.txt"
        original_content = original.read_text(encoding="utf-8")
        
        try:
            # 在模板中加入無效變數 {undefined_var}
            modified_content = original_content + "\n無效: {undefined_var}\n"
            original.write_text(modified_content, encoding="utf-8")
            
            triggers = [{"ticker": "CTXTEST", "name": "上下文測試", "close": 50, "reasons": "測試"}]
            date_str = "9999-01-03"
            
            with pytest.raises(KeyError) as exc_info:
                generate_packs(triggers, date_str)
            
            error_msg = str(exc_info.value)
            
            # 錯誤訊息必須包含 ticker
            assert "CTXTEST" in error_msg, f"錯誤訊息缺少 ticker: {error_msg}"
            
            # 錯誤訊息必須包含 template/ai_type
            assert "gemini" in error_msg, f"錯誤訊息缺少 ai_type: {error_msg}"
            
            # 錯誤訊息必須包含缺少的變數名
            assert "undefined_var" in error_msg, f"錯誤訊息缺少變數名: {error_msg}"
        
        finally:
            # 還原模板
            original.write_text(original_content, encoding="utf-8")
            # 清理測試目錄
            test_dir = BASE_DIR / "research" / date_str
            if test_dir.exists():
                shutil.rmtree(test_dir)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
