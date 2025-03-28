from flask import Flask
from app.routes import main
import logging
from logging.config import dictConfig
import yaml
import os
from app.extensions import init_redis
from config import Config
import threading
import time
from app.video_generator import VideoGenerator  # 导入 VideoGenerator

# 创建Redis实例
redis_client = None

def update_task_status(app):
    """后台线程,定期更新任务状态"""
    with app.app_context():
        video_generator = VideoGenerator(start_updater=False)  # 不启动内部更新器
        while True:
            try:
                logging.info("开始调用 update_queue_status")
                video_generator.update_queue_status()
                logging.info("update_queue_status 调用成功")
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                logging.error(f"更新任务状态失败: {str(e)}")
                logging.error(f"错误堆栈: {error_trace}")
            
            # 每20秒更新一次
            time.sleep(20)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # 初始化Redis
    global redis_client
    redis_client = init_redis(app)
    
    # 启动任务状态更新线程
    status_thread = threading.Thread(target=update_task_status, args=(app,), daemon=True)
    status_thread.start()
    
    # 注册蓝图
    app.register_blueprint(main)
    
    return app 

def configure_logging():
    """配置全局日志设置"""
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
            
        # 应用配置
        dictConfig({
            'version': 1,
            'formatters': {
                'default': {
                    'format': config['logging']['format'],
                },
            },
            'handlers': {
                'console': {
                    'class': 'logging.StreamHandler',
                    'level': 'DEBUG',  # 控制台输出设为DEBUG
                    'formatter': 'default',
                    'stream': 'ext://sys.stdout',
                },
                'file': {
                    'class': 'logging.FileHandler',
                    'level': 'DEBUG',  # 文件输出设为DEBUG
                    'formatter': 'default',
                    'filename': config['logging']['file'],
                },
            },
            'root': {
                'level': 'DEBUG',  # 根日志级别设为DEBUG
                'handlers': config['logging']['handlers'],
            },
            'loggers': {
                'werkzeug': {  
                    'level': 'WARNING',  # 改为 WARNING，减少请求日志
                    'handlers': ['console'],
                    'propagate': False,
                },
                'app': {  
                    'level': 'DEBUG',
                    'handlers': config['logging']['handlers'],
                    'propagate': False,
                },
            }
        })
    except Exception as e:
        print(f"日志配置失败: {e}，使用默认配置")
        logging.basicConfig(level=logging.DEBUG)
    
    # 设置 werkzeug 日志级别为 WARNING
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

# 在应用初始化时调用
configure_logging() 