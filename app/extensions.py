from redis import Redis
from config import Config

# 创建Redis实例
def init_redis(app):
    redis_client = Redis(
        host=app.config['REDIS_HOST'],
        port=app.config['REDIS_PORT'],
        password=None,
        db=app.config['REDIS_DB'],
        decode_responses=True  # 自动解码响应
    )
    return redis_client 