import os
import time

from openai import OpenAI

from basereal import BaseReal
from logger import logger
from system_prompt import get_system_prompt


# Load environment variables at runtime to ensure they're available
def get_api_config():
    api_key = os.getenv("OPEN_AI_API_KEY")
    base_url = os.getenv("OPEN_AI_URL")
    model = os.getenv("LLM_MODEL", "qwen-plus")
    return api_key, base_url, model


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

    completion = client.chat.completions.create(
        model=model,
        messages=[{'role': 'system', 'content': system_prompt},
                  {'role': 'user', 'content': message}],
        stream=True,
        # 通过以下设置，在流式输出的最后一行展示token使用信息
        stream_options={"include_usage": True}
    )
    result = ""
    first = True
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
            # msglist = re.split('[,.!;:，。！?]',msg)
            for i, char in enumerate(msg):
                if char in ",.!;:，。！？：；\n":
                    result = result+msg[lastpos:i+1]
                    lastpos = i+1
                    if len(result.strip()) > 0:
                        logger.info(result)
                        nerfreal.put_msg_txt(result)
                        result = ""
            result = result+msg[lastpos:]
            
            # Force flush if sentence is getting too long without punctuation
            if len(result) > 15:
                logger.info(result)
                nerfreal.put_msg_txt(result)
                result = ""
    end = time.perf_counter()
    logger.info(f"llm Time to last chunk: {end-start}s")
    if result.strip():
        nerfreal.put_msg_txt(result)
