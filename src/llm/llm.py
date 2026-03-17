import os
import threading
import time

from openai import OpenAI

from basereal import BaseReal
from logger import logger
from system_prompt import get_system_prompt

LLM_TTS_SOFT_BREAK_MIN_CHARS = int(os.getenv("LLM_TTS_SOFT_BREAK_MIN_CHARS", "28"))
LLM_TTS_FORCE_FLUSH_CHARS = int(os.getenv("LLM_TTS_FORCE_FLUSH_CHARS", "72"))
LLM_MAX_HISTORY_TURNS = int(os.getenv("LLM_MAX_HISTORY_TURNS", "6"))


# Load environment variables at runtime to ensure they're available
def get_api_config():
    api_key = os.getenv("OPEN_AI_API_KEY")
    base_url = os.getenv("OPEN_AI_URL")
    model = os.getenv("LLM_MODEL", "qwen-plus")
    return api_key, base_url, model


def _get_memory_holder(nerfreal: BaseReal):
    if hasattr(nerfreal, "get_conversation_memory_holder"):
        try:
            holder = nerfreal.get_conversation_memory_holder()
            if holder is not None:
                return holder
        except Exception:
            pass
    return nerfreal


def _get_memory_lock(holder) -> threading.RLock:
    lock = getattr(holder, "_conversation_history_lock", None)
    if lock is None:
        lock = threading.RLock()
        setattr(holder, "_conversation_history_lock", lock)
    return lock


def _get_conversation_history(holder) -> list[dict]:
    with _get_memory_lock(holder):
        history = getattr(holder, "_conversation_history", None)
        if not isinstance(history, list):
            history = []
            setattr(holder, "_conversation_history", history)
        return list(history)


def _append_conversation_turn(holder, user_text: str, assistant_text: str):
    user_text = (user_text or "").strip()
    assistant_text = (assistant_text or "").strip()
    if not user_text or not assistant_text:
        return

    with _get_memory_lock(holder):
        history = getattr(holder, "_conversation_history", None)
        if not isinstance(history, list):
            history = []
        history.extend([
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_text},
        ])
        max_messages = max(1, LLM_MAX_HISTORY_TURNS) * 2
        if len(history) > max_messages:
            history = history[-max_messages:]
        setattr(holder, "_conversation_history", history)


def _should_persist_turn(nerfreal: BaseReal) -> bool:
    if hasattr(nerfreal, "should_persist_conversation_turn"):
        try:
            return bool(nerfreal.should_persist_conversation_turn())
        except Exception:
            return False
    return True


def llm_response(message, nerfreal: BaseReal, avatar_name: str = "小li"):
    start = time.perf_counter()

    # Get API configuration at runtime
    api_key, base_url, model = get_api_config()

    # Check if API key is configured
    if not api_key:
        logger.error("OPEN_AI_API_KEY environment variable is not set")
        nerfreal.put_msg_txt("Error: API key not configured")
        return

    if not base_url:
        logger.error("OPEN_AI_URL environment variable is not set")
        nerfreal.put_msg_txt("Error: Base URL not configured")
        return

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    end = time.perf_counter()
    logger.info(f"llm Time init: {end-start}s")
    logger.info(f"llm url: {base_url}")
    logger.info(f"llm model: {model}")
    logger.info(f"llm key: {api_key}")

    # 动态生成系统提示词
    system_prompt = get_system_prompt(avatar_name)
    memory_holder = _get_memory_holder(nerfreal)
    conversation_history = _get_conversation_history(memory_holder)

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {'role': 'system', 'content': system_prompt},
            *conversation_history,
            {'role': 'user', 'content': message},
        ],
        stream=True,
        # 通过以下设置，在流式输出的最后一行展示token使用信息
        stream_options={"include_usage": True}
    )
    result = ""
    first = True
    full_response_parts: list[str] = []

    def flush_result():
        nonlocal result
        text = result.strip()
        if not text:
            result = ""
            return
        logger.info(text)
        full_response_parts.append(text)
        nerfreal.put_msg_txt(text)
        result = ""

    for chunk in completion:
        if len(chunk.choices) > 0:
            # print(chunk.choices[0].delta.content)
            if first:
                end = time.perf_counter()
                logger.info(f"llm Time to first chunk: {end-start}s")
                first = False
            msg = chunk.choices[0].delta.content
            
            # 🆕 修复：检查msg是否为None
            if msg is None:
                continue
                
            lastpos = 0
            hard_breaks = ".!?。！？\n"
            soft_breaks = ",;:，、；："
            for i, char in enumerate(msg):
                if char in hard_breaks:
                    result = result+msg[lastpos:i+1]
                    lastpos = i+1
                    flush_result()
                elif char in soft_breaks:
                    result = result + msg[lastpos:i+1]
                    lastpos = i+1
                    if len(result.strip()) >= LLM_TTS_SOFT_BREAK_MIN_CHARS:
                        flush_result()
            result = result+msg[lastpos:]
            
            if len(result.strip()) >= LLM_TTS_FORCE_FLUSH_CHARS:
                flush_result()
    end = time.perf_counter()
    logger.info(f"llm Time to last chunk: {end-start}s")
    if result.strip():
        flush_result()

    if _should_persist_turn(nerfreal):
        full_response = "".join(full_response_parts).strip()
        _append_conversation_turn(memory_holder, message, full_response)
