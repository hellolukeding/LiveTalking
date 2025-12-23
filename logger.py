import logging

# 配置日志器
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 文件处理器
fhandler = logging.FileHandler('livetalking.log')
fhandler.setFormatter(formatter)
fhandler.setLevel(logging.INFO)
logger.addHandler(fhandler)

# 控制台处理器
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
sformatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(sformatter)
logger.addHandler(handler)
