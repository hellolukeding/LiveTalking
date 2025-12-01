import os
import time

from basereal import BaseReal
from logger import logger


def llm_response(message, nerfreal: BaseReal):
    start = time.perf_counter()
    from openai import OpenAI
    client = OpenAI(
        # 如果您没有配置环境变量，请在此处用您的API Key进行替换
        api_key=os.getenv("OPEN_AI_API_KEY"),
        # 填写DashScope SDK的base_url
        base_url=os.getenv("OPEN_AI_URL"),
    )
    end = time.perf_counter()
    logger.info(f"llm Time init: {end-start}s")
    completion = client.chat.completions.create(
        model=os.getenv("LLM_MODEL", "qwen-plus"),
        messages=[{'role': 'system', 'content': 'You are a helpful assistant.'},
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
            lastpos = 0
            # msglist = re.split('[,.!;:，。！?]',msg)
            for i, char in enumerate(msg):
                if char in ",.!;:，。！？：；":
                    result = result+msg[lastpos:i+1]
                    lastpos = i+1
                    if len(result) > 10:
                        logger.info(result)
                        nerfreal.put_msg_txt(result)
                        result = ""
            result = result+msg[lastpos:]
    end = time.perf_counter()
    logger.info(f"llm Time to last chunk: {end-start}s")
    nerfreal.put_msg_txt(result)
