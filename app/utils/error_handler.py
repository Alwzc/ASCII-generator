from typing import Dict, Any

class VideoProcessError(Exception):
    """视频处理错误基类"""
    def __init__(self, message: str, error_code: str):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)

class GPTError(VideoProcessError):
    """GPT API 相关错误"""
    pass

class ComfyUIError(VideoProcessError):
    """ComfyUI 相关错误"""
    pass

class VideoProcessingError(VideoProcessError):
    """视频处理相关错误"""
    pass

class RedisError(Exception):
    """Redis操作异常"""
    def __init__(self, message, error_code=None):
        super().__init__(message)
        self.error_code = error_code or "REDIS_ERROR"

class ErrorHandler:
    def __init__(self):
        self.error_map = {
            GPTError: {
                'status_code': 500,
                'error_type': 'GPT_ERROR'
            },
            ComfyUIError: {
                'status_code': 500,
                'error_type': 'COMFYUI_ERROR'
            },
            VideoProcessError: {
                'status_code': 500,
                'error_type': 'VIDEO_PROCESS_ERROR'
            }
        }
    
    def handle_error(self, error: Exception, context: Dict[str, Any] = None) -> Dict:
        """处理错误并返回标准化的错误响应"""
        error_info = self.error_map.get(
            type(error),
            {
                'status_code': 500,
                'error_type': 'UNKNOWN_ERROR'
            }
        )
        
        return {
            'success': False,
            'error': {
                'type': error_info['error_type'],
                'message': str(error),
                'context': context
            }
        } 