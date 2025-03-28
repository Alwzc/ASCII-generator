import yaml
import logging
from pathlib import Path
import os

logger = logging.getLogger(__name__)

class Config:
    # Flask 配置
    SECRET_KEY = 'your-secret-key-here'  # 用于Flask会话安全
    debug = False  # 添加 debug 属性
    
    # API配置
    GPT_API_KEY = "sk-xasOhQxOqJvUOVdlPJIRbTChpAc1dhbFH5N7UlUKuyR3rcNL"
    GPT_API_URL = "https://www.mnapi.com/v1/chat/completions"
    
    # ComfyUI 配置
    COMFYUI_URL = os.getenv('COMFYUI_URL', 'http://213.181.123.58:42224').rstrip('/')
    COMFYUI_WS_URL = os.getenv('COMFYUI_WS_URL', 'ws://213.181.123.58:42224').rstrip('/')
    COMFYUI_CLIENT_ID='991'
    COMFYUI_TOKEN = os.getenv('COMFYUI_TOKEN', '376209a9f8e8a5a7664a1c1d0b2818f899a8565b92fb5057a033768f703108eb')
    
    # 文件路径配置
    UPLOAD_FOLDER = 'app/static/uploads'
    OUTPUT_FOLDER = 'app/static/output'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max-limit
    
    COMFYUI_OUTPUT_DIR = "path/to/comfyui/output"  # 需要设置正确的输出目录路径
    
    # Redis配置
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
    REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)  # 如果有密码的话
    REDIS_DB = int(os.getenv('REDIS_DB', 3))
    
    def __init__(self, config_path=None):
        """
        初始化配置
        Args:
            config_path: 配置文件路径（可选）
        """
        if config_path:
            self.config_path = Path(config_path)
            self.config = self._load_config()
            # 更新配置
            self._update_from_yaml()
        
    def _load_config(self):
        """
        加载YAML配置文件
        """
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.debug(f"成功加载配置文件: {self.config_path}")
            return config
        except Exception as e:
            logger.error(f"加载配置文件失败: {str(e)}")
            return {}

    def _update_from_yaml(self):
        """从YAML配置更新属性"""
        if self.config:
            # 更新 debug 模式
            if 'debug' in self.config:
                self.debug = self.config['debug']
            
            # 更新其他配置...
            if 'flask' in self.config:
                flask_config = self.config['flask']
                if 'secret_key' in flask_config:
                    self.SECRET_KEY = flask_config['secret_key']
                if 'upload_folder' in flask_config:
                    self.UPLOAD_FOLDER = flask_config['upload_folder']
                if 'output_folder' in flask_config:
                    self.OUTPUT_FOLDER = flask_config['output_folder']
                if 'max_content_length' in flask_config:
                    self.MAX_CONTENT_LENGTH = flask_config['max_content_length']

    def get(self, key, default=None):
        """
        获取配置项
        """
        return self.config.get(key, default) if hasattr(self, 'config') else default

    @property
    def ai_model(self):
        """AI模型配置"""
        return self.get('ai_model', {})

    @property
    def api_key(self):
        """API密钥"""
        return self.get('api_key') 