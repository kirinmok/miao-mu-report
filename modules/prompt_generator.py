"""
M5 PromptPackGenerator

Deterministic Compiler：
將 trigger 標的資料編譯成可交付給不同 AI 角色的 prompt packs。

規則：
- 不呼叫 AI、不做投資決策、不做情緒分析
- 不提供 fallback、缺變數直接丟錯
- 模板變數只有五個：{date}, {name}, {ticker}, {close}, {reasons}
- 不產生半套檔案：先 compile 全部成功，再 atomic write
"""
import os
import re
from pathlib import Path
from typing import List, Dict


# 專案根目錄
BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"

# AI 類型（唯一來源，模板檔名由此推導）
AI_TYPES = ("perplexity", "gemini", "claude", "chatgpt")

# ticker 允許的字元（字母、數字、dash、底線）
TICKER_PATTERN = re.compile(r'^[A-Za-z0-9_\-]+$')


class TemplateNotFoundError(Exception):
    """模板檔案不存在"""
    pass


class MissingTriggerFieldError(Exception):
    """Trigger 資料缺少必要欄位"""
    pass


class InvalidTriggerValueError(Exception):
    """Trigger 資料欄位值無效"""
    pass


def _get_template_filename(ai_type: str) -> str:
    """從 AI_TYPE 推導模板檔名，確保同步"""
    return f"prompt_{ai_type}.txt"


def _validate_templates() -> None:
    """
    驗證所有模板檔案是否存在
    模板檔名由 AI_TYPES 推導，確保不會不同步
    """
    for ai_type in AI_TYPES:
        template_file = _get_template_filename(ai_type)
        template_path = TEMPLATES_DIR / template_file
        if not template_path.exists():
            raise TemplateNotFoundError(
                f"模板檔案不存在: {template_path}\n"
                f"請確認 templates/ 目錄下有以下檔案:\n" +
                "\n".join(f"  - {_get_template_filename(t)}" for t in AI_TYPES)
            )


def _sanitize_ticker(ticker: str) -> str:
    """
    清理 ticker，確保可安全用於檔名
    只允許字母、數字、dash、底線
    """
    if not TICKER_PATTERN.match(ticker):
        # 移除不安全字元
        sanitized = re.sub(r'[^A-Za-z0-9_\-]', '', ticker)
        if not sanitized:
            raise InvalidTriggerValueError(
                f"ticker 清理後為空: 原始值='{ticker}'"
            )
        return sanitized
    return ticker


def _validate_trigger(trigger: dict) -> None:
    """
    驗證 trigger 資料是否包含所有必要欄位且值有效
    - ticker/name/reasons 必須為非空字串
    - close 不得為 None
    - ticker 需做基本 sanitize
    """
    required_fields = ("ticker", "name", "close", "reasons")
    
    # 檢查欄位存在
    missing = [f for f in required_fields if f not in trigger]
    if missing:
        raise MissingTriggerFieldError(
            f"Trigger 資料缺少必要欄位: {missing}\n"
            f"收到的資料: {trigger}"
        )
    
    # 驗證 ticker（非空字串）
    ticker = trigger["ticker"]
    if not isinstance(ticker, str) or not ticker.strip():
        raise InvalidTriggerValueError(
            f"ticker 必須為非空字串，收到: {repr(ticker)}"
        )
    
    # 驗證 name（非空字串）
    name = trigger["name"]
    if not isinstance(name, str) or not name.strip():
        raise InvalidTriggerValueError(
            f"name 必須為非空字串，收到: {repr(name)}"
        )
    
    # 驗證 close（不得為 None）
    close = trigger["close"]
    if close is None:
        raise InvalidTriggerValueError(
            f"close 不得為 None"
        )
    
    # 驗證 reasons（非空字串）
    reasons = trigger["reasons"]
    if not isinstance(reasons, str) or not reasons.strip():
        raise InvalidTriggerValueError(
            f"reasons 必須為非空字串，收到: {repr(reasons)}"
        )


def _load_template(ai_type: str) -> str:
    """
    載入指定 AI 類型的模板
    """
    template_file = _get_template_filename(ai_type)
    template_path = TEMPLATES_DIR / template_file
    
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()


def _compile_prompt(template: str, date: str, name: str, ticker: str, close: str, reasons: str) -> str:
    """
    使用 str.format() 填入變數
    若模板中有未提供的變數會自動 raise KeyError
    """
    return template.format(
        date=date,
        name=name,
        ticker=ticker,
        close=close,
        reasons=reasons
    )


def _atomic_write(file_path: Path, content: str) -> None:
    """
    原子寫入：先寫 .tmp 再 replace，避免半套檔案
    """
    tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    # atomic replace
    tmp_path.replace(file_path)


def generate_packs(triggers: List[dict], date_str: str) -> List[str]:
    """
    為所有觸發標的產生四份 Prompt Pack
    
    保證不產生半套檔案：
    1) 先把四份 prompt 全部 compile 成功（memory dict）
    2) 再寫入檔案（使用 atomic write）
    
    Args:
        triggers: 觸發標的列表，每項必須有 ticker, name, close, reasons
        date_str: 日期字串 (YYYY-MM-DD)
    
    Returns:
        List[str]: 產生的檔案完整路徑清單
    
    Raises:
        TemplateNotFoundError: 模板檔案不存在
        MissingTriggerFieldError: Trigger 缺少必要欄位
        InvalidTriggerValueError: Trigger 欄位值無效
        KeyError: 模板變數填入失敗
    """
    # Step 1: 驗證所有模板存在
    _validate_templates()
    
    # Step 2: 建立輸出目錄（deterministic path）
    output_dir = BASE_DIR / "research" / date_str / "outputs" / "prompt_packs"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Step 3: 預載所有模板
    templates = {ai_type: _load_template(ai_type) for ai_type in AI_TYPES}
    
    generated_files: List[str] = []
    
    # Step 4: 逐一處理 trigger
    for trigger in triggers:
        # 驗證必要欄位與值
        _validate_trigger(trigger)
        
        ticker = _sanitize_ticker(trigger["ticker"])
        name = trigger["name"]
        close = str(trigger["close"])  # 轉字串確保格式一致
        reasons = trigger["reasons"]
        
        # Step 4a: 先 compile 全部（若任一失敗，不會寫入任何檔案）
        compiled: Dict[str, str] = {}
        for ai_type in AI_TYPES:
            template = templates[ai_type]
            try:
                compiled[ai_type] = _compile_prompt(
                    template=template,
                    date=date_str,
                    name=name,
                    ticker=ticker,
                    close=close,
                    reasons=reasons
                )
            except KeyError as e:
                raise KeyError(
                    f"模板變數填入失敗: ticker={ticker}, template={ai_type}, "
                    f"缺少變數={e}"
                ) from e
        
        # Step 4b: 全部成功後，atomic write
        for ai_type in AI_TYPES:
            file_name = f"{ticker}_{ai_type}.txt"
            file_path = output_dir / file_name
            
            _atomic_write(file_path, compiled[ai_type])
            generated_files.append(str(file_path))
    
    return generated_files
