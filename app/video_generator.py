import requests
import json
import time
import os
from typing import List, Dict, Optional
from dataclasses import dataclass
import uuid
from app.utils.error_handler import GPTError, ComfyUIError, VideoProcessingError
from config import Config
import logging
from pathlib import Path
import base64
import random
from app.extensions import init_redis
from flask import current_app
import threading

logger = logging.getLogger(__name__)

@dataclass
class VideoSegment:
    prompt: str
    duration: int
    output_path: str = ""

class VideoGenerator:
    def __init__(self, start_updater=False):
        """初始化视频生成器"""
        # 确保从正确的模块导入 Config
        try:
            from app.config import Config
            self.config = Config()
        except ImportError:
            from config import Config
            self.config = Config()
        
        # 确保输出目录存在
        self._ensure_output_dir()
        self._ensure_workflow_dir()
        
        # 生成一个默认的客户端ID
        self.default_client_id = str(uuid.uuid4())
        
        # 使用当前应用的Redis实例
        self.redis = init_redis(current_app)
        
        # 只有在指定时才启动后台任务更新器
        if start_updater:
            self._start_queue_updater()

    def _ensure_output_dir(self):
        """确保输出目录存在"""
        try:
            output_dir = self.config.OUTPUT_DIR
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
        except AttributeError:
            # 如果 OUTPUT_DIR 不存在，使用默认值
            default_output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "output")
            if not os.path.exists(default_output_dir):
                os.makedirs(default_output_dir)
            # 动态添加 OUTPUT_DIR 属性
            self.config.OUTPUT_DIR = default_output_dir

    def _ensure_workflow_dir(self):
        """确保工作流目录存在并设置正确"""
        # 直接使用项目根目录下的Model文件夹
        root_dir = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        model_dir = root_dir / "model"
        
        if not model_dir.exists():
            logger.warning(f"model文件夹不存在，创建目录: {model_dir}")
            os.makedirs(model_dir)
        
        # 设置工作流目录为Model文件夹
        self.config.WORKFLOW_DIR = model_dir
        # logger.info(f"工作流目录设置为: {self.config.WORKFLOW_DIR}")

    def _load_workflow(self, model_name: str) -> Dict:
        """
        从JSON文件加载工作流配置
        
        Args:
            model_name: 模型配置文件名称
            
        Returns:
            Dict: 工作流配置字典
            
        Raises:
            FileNotFoundError: 配置文件不存在时抛出
        """
        try:
            # 直接从Model文件夹加载
            workflow_path = self.config.WORKFLOW_DIR / f"{model_name}.json"
            
            if not workflow_path.exists():
                raise FileNotFoundError(f"找不到工作流配置文件: {workflow_path}")
            
            logger.info(f"加载工作流配置: {workflow_path}")
            with open(workflow_path, 'r', encoding='utf-8') as f:
                workflow = json.load(f)
            return workflow
        
        except Exception as e:
            logger.error(f"加载工作流配置失败: {str(e)}")
            raise

    def _validate_workflow(self, workflow: Dict) -> None:
        """验证工作流配置的有效性"""
        if not isinstance(workflow, dict):
            raise ComfyUIError("Invalid workflow format: must be a dictionary", error_code="INVALID_WORKFLOW")
        
        # 检查工作流是否为空
        if not workflow:
            raise ComfyUIError("Empty workflow configuration", error_code="INVALID_WORKFLOW")
        
        # 检查必要的节点是否存在
        required_nodes = {
           
        }
        
        for node_id, node_name in required_nodes.items():
            if node_id not in workflow:
                raise ComfyUIError(f"Missing required node {node_name} (ID: {node_id})", error_code="INVALID_WORKFLOW")
            if "inputs" not in workflow[node_id]:
                raise ComfyUIError(f"Node {node_name} (ID: {node_id}) missing inputs configuration", error_code="INVALID_WORKFLOW")

    def _queue_prompt(self, workflow: Dict) -> str:
        """提交工作流到 ComfyUI"""
        try:
            data = {
                "prompt": workflow,
                "client_id": self.config.COMFYUI_CLIENT_ID
            }
            
            # 使用Authorization头进行认证
            headers = {
                "Authorization": f"Bearer {self.config.COMFYUI_TOKEN}",
                "Content-Type": "application/json"
            }
            
            logger.debug(f"Sending request to {self.config.COMFYUI_URL}/prompt")
            logger.debug(f"Request data: {json.dumps(data, indent=2)}")
            
            # 添加更详细的错误处理和调试信息
            response = requests.post(
                f"{self.config.COMFYUI_URL}/prompt",
                json=data,
                headers=headers,
                timeout=30  # 添加超时设置
            )
            
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                logger.error(f"ComfyUI API 错误: {error_msg}")
                raise ComfyUIError(error_msg, error_code="COMFYUI_HTTP_ERROR")
            
            # 打印完整的响应内容以便调试
            logger.debug(f"ComfyUI 响应: {response.text}")
            
            result = response.json()
            if "prompt_id" not in result:
                # 记录完整的响应内容
                logger.error(f"ComfyUI 响应中没有 prompt_id: {json.dumps(result, indent=2)}")
                
                # 尝试从响应中提取可能的错误信息
                error_msg = "No prompt_id in response"
                if "error" in result:
                    error_msg = f"{error_msg}: {result['error']}"
                elif "detail" in result:
                    error_msg = f"{error_msg}: {result['detail']}"
                    
                raise ComfyUIError(error_msg, error_code="COMFYUI_INVALID_RESPONSE")
                
            return result["prompt_id"]
            
        except requests.RequestException as e:
            logger.error(f"ComfyUI 请求异常: {str(e)}")
            raise ComfyUIError(f"Failed to connect to ComfyUI server: {str(e)}", error_code="COMFYUI_CONNECTION_ERROR")
        except json.JSONDecodeError as e:
            logger.error(f"ComfyUI 响应解析失败: {str(e)}")
            raise ComfyUIError(f"Invalid JSON response from ComfyUI: {str(e)}", error_code="COMFYUI_INVALID_RESPONSE")
        except Exception as e:
            logger.error(f"提交工作流失败: {str(e)}")
            if isinstance(e, ComfyUIError):
                raise
            raise ComfyUIError(f"Failed to queue prompt: {str(e)}", error_code="COMFYUI_REQUEST_FAILED")

    def _update_queue_status(self):
        """更新队列状态到Redis"""
        try:
            headers = {"Authorization": f"Bearer {self.config.COMFYUI_TOKEN}"}
            
            # 获取当前队列状态
            queue_response = requests.get(
                f"{self.config.COMFYUI_URL}/queue",
                headers=headers
            )
            
            if queue_response.status_code == 200:
                queue_data = queue_response.json()
                current_time = time.time()
                
                # 获取运行中和等待中的任务
                running_tasks = queue_data.get("queue_running", [])
                pending_tasks = queue_data.get("queue_pending", [])
                
                # 记录当前所有活跃任务的ID
                active_task_ids = set()
                
                # 更新运行中的任务
                self.redis.delete("running_tasks")
                for task in running_tasks:
                    # 确保任务数据格式正确
                    if len(task) >= 2:
                        task_id = task[1]  # 使用索引1获取任务ID
                        active_task_ids.add(task_id)
                        self.redis.sadd("running_tasks", task_id)
                        
                        # 更新任务状态
                        task_data = self.redis.hget("tasks_status", task_id)
                        if task_data:
                            task_info = json.loads(task_data)
                            task_info["status"] = "processing"
                            task_info["message"] = "任务正在处理中"
                            
                            # 计算处理时间
                            if "processing_started" not in task_info:
                                task_info["processing_started"] = current_time
                            
                            task_info["processing_time"] = current_time - task_info.get("processing_started", current_time)
                            task_info["last_updated"] = current_time
                            
                            # 尝试从工作流中提取提示词
                            if "prompt" not in task_info and len(task) >= 3 and isinstance(task[2], dict):
                                workflow = task[2]
                                for node_id, node in workflow.items():
                                    if node.get("class_type") == "CLIPTextEncode" and "inputs" in node and "text" in node["inputs"]:
                                        task_info["prompt"] = node["inputs"]["text"]
                                        break
                                    elif node.get("class_type") == "WanVideoTextEncode" and "inputs" in node and "positive_prompt" in node["inputs"]:
                                        task_info["prompt"] = node["inputs"]["positive_prompt"]
                                        break
                                    elif node.get("class_type") == "BizyAir_CLIPTextEncode" and "inputs" in node and "text" in node["inputs"]:
                                        task_info["prompt"] = node["inputs"]["text"]
                                        break
                                    elif node.get("class_type") == "KSampler" and "inputs" in node and "positive" in node["inputs"]:
                                        # 对于KSampler节点，可能需要进一步查找正向提示词
                                        positive_node_id = node["inputs"]["positive"]
                                        if isinstance(positive_node_id, list) and len(positive_node_id) >= 2:
                                            positive_node_id = positive_node_id[0]
                                            if str(positive_node_id) in workflow:
                                                positive_node = workflow[str(positive_node_id)]
                                                if "inputs" in positive_node and "text" in positive_node["inputs"]:
                                                    task_info["prompt"] = positive_node["inputs"]["text"]
                                                    break
                            
                            # 尝试提取模型信息
                            if "model" not in task_info and len(task) >= 3 and isinstance(task[2], dict):
                                workflow = task[2]
                                for node_id, node in workflow.items():
                                    if node.get("class_type") == "WanVideoModelLoader" and "inputs" in node and "model" in node["inputs"]:
                                        model_name = node["inputs"]["model"]
                                        if isinstance(model_name, str) and "/" in model_name:
                                            model_name = model_name.split("/")[0]  # 提取模型名称的第一部分
                                        task_info["model"] = model_name
                                        break
                            
                            self.redis.hset("tasks_status", task_id, json.dumps(task_info))
                        else:
                            # 如果任务不在状态表中，创建一个新的状态记录
                            logger.info(f"为运行中的任务 {task_id} 创建新的状态记录")
                            
                            # 尝试从工作流中提取提示词
                            prompt = None
                            model = None
                            if len(task) >= 3 and isinstance(task[2], dict):
                                workflow = task[2]
                                for node_id, node in workflow.items():
                                    if node.get("class_type") == "CLIPTextEncode" and "inputs" in node and "text" in node["inputs"]:
                                        prompt = node["inputs"]["text"]
                                    elif node.get("class_type") == "WanVideoTextEncode" and "inputs" in node and "positive_prompt" in node["inputs"]:
                                        prompt = node["inputs"]["positive_prompt"]
                                    
                                    if node.get("class_type") == "WanVideoModelLoader" and "inputs" in node and "model" in node["inputs"]:
                                        model_name = node["inputs"]["model"]
                                        if isinstance(model_name, str) and "/" in model_name:
                                            model_name = model_name.split("/")[0]
                                        model = model_name
                            
                            new_task_info = {
                                "status": "processing",
                                "message": "任务正在处理中",
                                "processing_started": current_time,
                                "processing_time": 0,
                                "last_updated": current_time,
                                "created_at": current_time,
                                "prompt": prompt,
                                "model": model
                            }
                            self.redis.hset("tasks_status", task_id, json.dumps(new_task_info))
                
                # 更新等待中的任务
                self.redis.delete("pending_tasks")
                for i, task in enumerate(pending_tasks):
                    # 确保任务数据格式正确
                    if len(task) >= 2:
                        task_id = task[1]  # 使用索引1获取任务ID
                        active_task_ids.add(task_id)
                        self.redis.sadd("pending_tasks", task_id)
                        
                        # 更新任务状态
                        task_data = self.redis.hget("tasks_status", task_id)
                        if task_data:
                            task_info = json.loads(task_data)
                            task_info["status"] = "pending"
                            task_info["message"] = f"正在等待队列中，位置: {i+1}"
                            task_info["queue_position"] = i + 1
                            
                            # 计算等待时间
                            if "waiting_started" not in task_info:
                                task_info["waiting_started"] = current_time
                            
                            task_info["waiting_time"] = current_time - task_info.get("waiting_started", current_time)
                            task_info["last_updated"] = current_time
                            
                            # 尝试从工作流中提取提示词
                            if "prompt" not in task_info and len(task) >= 3 and isinstance(task[2], dict):
                                workflow = task[2]
                                for node_id, node in workflow.items():
                                    if node.get("class_type") == "CLIPTextEncode" and "inputs" in node and "text" in node["inputs"]:
                                        task_info["prompt"] = node["inputs"]["text"]
                                        break
                                    elif node.get("class_type") == "WanVideoTextEncode" and "inputs" in node and "positive_prompt" in node["inputs"]:
                                        task_info["prompt"] = node["inputs"]["positive_prompt"]
                                        break
                            
                            # 尝试提取模型信息
                            if "model" not in task_info and len(task) >= 3 and isinstance(task[2], dict):
                                workflow = task[2]
                                for node_id, node in workflow.items():
                                    if node.get("class_type") == "WanVideoModelLoader" and "inputs" in node and "model" in node["inputs"]:
                                        model_name = node["inputs"]["model"]
                                        if isinstance(model_name, str) and "/" in model_name:
                                            model_name = model_name.split("/")[0]  # 提取模型名称的第一部分
                                        task_info["model"] = model_name
                                        break
                            
                            self.redis.hset("tasks_status", task_id, json.dumps(task_info))
                        else:
                            # 如果任务不在状态表中，创建一个新的状态记录
                            logger.info(f"为等待中的任务 {task_id} 创建新的状态记录")
                            
                            # 尝试从工作流中提取提示词
                            prompt = None
                            model = None
                            if len(task) >= 3 and isinstance(task[2], dict):
                                workflow = task[2]
                                for node_id, node in workflow.items():
                                    if node.get("class_type") == "CLIPTextEncode" and "inputs" in node and "text" in node["inputs"]:
                                        prompt = node["inputs"]["text"]
                                    elif node.get("class_type") == "WanVideoTextEncode" and "inputs" in node and "positive_prompt" in node["inputs"]:
                                        prompt = node["inputs"]["positive_prompt"]
                                    
                                    if node.get("class_type") == "WanVideoModelLoader" and "inputs" in node and "model" in node["inputs"]:
                                        model_name = node["inputs"]["model"]
                                        if isinstance(model_name, str) and "/" in model_name:
                                            model_name = model_name.split("/")[0]
                                        model = model_name
                            
                            new_task_info = {
                                "status": "pending",
                                "message": f"正在等待队列中，位置: {i+1}",
                                "queue_position": i + 1,
                                "waiting_started": current_time,
                                "waiting_time": 0,
                                "last_updated": current_time,
                                "created_at": current_time,
                                "prompt": prompt,
                                "model": model
                            }
                            self.redis.hset("tasks_status", task_id, json.dumps(new_task_info))
                
                # 检查历史记录中的任务
                all_tasks = self.redis.hgetall("tasks_status")
                for task_id_bytes, task_data_bytes in all_tasks.items():
                    task_id = task_id_bytes.decode('utf-8') if isinstance(task_id_bytes, bytes) else task_id_bytes
                    
                    # 跳过活跃任务
                    if task_id in active_task_ids:
                        continue
                    
                    # 解析任务数据
                    task_data = json.loads(task_data_bytes) if isinstance(task_data_bytes, bytes) else json.loads(task_data_bytes)
                    
                    # 如果任务不在队列中，检查历史记录
                    if task_data.get("status") not in ["completed", "error"]:
                        history_result = self._check_task_history(task_id)
                        
                        if history_result:
                            # 更新任务状态
                            task_data.update(history_result)
                            task_data["last_updated"] = current_time
                            
                            # 如果任务已完成或出错，移到已完成列表
                            if task_data.get("status") in ["completed", "error"]:
                                task_data["completed_at"] = current_time
                                self.redis.hset("completed_tasks", task_id, json.dumps(task_data))
                                self.redis.hdel("tasks_status", task_id)
                                logger.info(f"任务 {task_id} 已完成，状态: {task_data.get('status')}")
                            else:
                                self.redis.hset("tasks_status", task_id, json.dumps(task_data))
            else:
                logger.error(f"获取队列状态失败: HTTP {queue_response.status_code}")
        
        except Exception as e:
            logger.error(f"更新队列状态失败: {str(e)}", exc_info=True)

    def _check_task_history(self, task_id: str) -> Dict:
        """检查任务历史记录"""
        try:
            headers = {"Authorization": f"Bearer {self.config.COMFYUI_TOKEN}"}
            response = requests.get(
                f"{self.config.COMFYUI_URL}/history/{task_id}",
                headers=headers
            )
            
            if response.status_code == 200:
                history_data = response.json()
                
                # 检查是否有任务数据
                if task_id in history_data:
                    task_history = history_data[task_id]
                    
                    # 尝试从历史记录中提取提示词
                    prompt = None
                    try:
                        prompt_data = task_history.get("prompt", [])
                        if len(prompt_data) >= 3 and isinstance(prompt_data[2], dict):
                            workflow = prompt_data[2]
                            for node_id, node in workflow.items():
                                if node.get("class_type") == "CLIPTextEncode" and "inputs" in node and "text" in node["inputs"]:
                                    prompt = node["inputs"]["text"]
                                    break
                                elif node.get("class_type") == "WanVideoTextEncode" and "inputs" in node and "positive_prompt" in node["inputs"]:
                                    prompt = node["inputs"]["positive_prompt"]
                                    break
                    except (IndexError, KeyError, TypeError):
                        pass
                    
                    # 提取模型信息
                    model = None
                    try:
                        # 尝试从客户端数据中提取
                        if len(prompt_data) >= 4 and isinstance(prompt_data[3], dict):
                            client_data = prompt_data[3]
                            if "model" in client_data:
                                model = client_data["model"]
                        
                        # 如果没有找到，尝试从工作流中提取
                        if not model and len(prompt_data) >= 3 and isinstance(prompt_data[2], dict):
                            workflow = prompt_data[2]
                            for node_id, node in workflow.items():
                                if node.get("class_type") == "UNETLoader" and "inputs" in node and "unet_name" in node["inputs"]:
                                    model = node["inputs"]["unet_name"].replace(".safetensors", "")
                                    break
                                elif node.get("class_type") == "WanVideoModelLoader" and "inputs" in node and "model" in node["inputs"]:
                                    model_name = node["inputs"]["model"]
                                    if isinstance(model_name, str) and "/" in model_name:
                                        model_name = model_name.split("/")[0]  # 提取模型名称的第一部分
                                    model = model_name
                                    break
                    except (IndexError, KeyError, TypeError) as e:
                        logger.warning(f"Failed to extract model from history: {str(e)}")
                    
                    # 提取执行时间信息
                    start_time = None
                    end_time = None
                    try:
                        status_data = task_history.get("status", {})
                        messages = status_data.get("messages", [])
                        
                        for msg in messages:
                            if msg[0] == "execution_start":
                                start_time = msg[1].get("timestamp", 0) / 1000  # 转换为秒
                            elif msg[0] == "execution_success":
                                end_time = msg[1].get("timestamp", 0) / 1000  # 转换为秒
                    except (IndexError, KeyError, TypeError) as e:
                        logger.warning(f"Failed to extract timing from history: {str(e)}")
                    
                    # 检查是否有输出
                    if "outputs" in task_history:
                        outputs = task_history["outputs"]
                        
                        # 检查是否有视频输出 - 处理VHS_VideoCombine节点的输出
                        for node_id, output in outputs.items():
                            # 检查是否有gifs字段（VHS_VideoCombine节点的输出格式）
                            if "gifs" in output and output["gifs"]:
                                video_info = output["gifs"][0]
                                filename = video_info.get("filename")
                                
                                if filename:
                                    # 构建完整的URL路径
                                    video_url = f"{self.config.COMFYUI_URL}/view?filename={filename}"
                                    local_path = os.path.join(self.config.OUTPUT_DIR, filename)
                                    
                                    # 下载视频到本地
                                    self._download_video(video_url, local_path)
                                    
                                    # 计算处理时间
                                    processing_time = None
                                    if start_time and end_time:
                                        processing_time = end_time - start_time
                                    
                                    result = {
                                        "status": "completed",
                                        "message": "视频生成完成",
                                        "output_path": local_path,
                                        "type": "video",
                                        "preview_url": f"/static/output/{filename}",
                                        "prompt": prompt,
                                        "model": model
                                    }
                                    
                                    if processing_time:
                                        result["processing_time"] = processing_time
                                    
                                    return result
                            
                            # 检查是否有animated标记
                            is_animated = False
                            if "animated" in output and output["animated"] and output["animated"][0]:
                                is_animated = True
                            
                            # 处理常规图像/视频输出
                            if "images" in output and output["images"]:
                                filename = output["images"][0]["filename"]
                                output_path = os.path.join(self.config.OUTPUT_DIR, filename)
                                
                                # 下载文件
                                file_url = f"{self.config.COMFYUI_URL}/view?filename={filename}"
                                self._download_video(file_url, output_path)
                                
                                # 计算处理时间
                                processing_time = None
                                if start_time and end_time:
                                    processing_time = end_time - start_time
                                
                                result = {
                                    "status": "completed",
                                    "message": "视频生成完成" if is_animated else "图片生成完成",
                                    "output_path": output_path,
                                    "type": "video" if is_animated else "image",
                                    "preview_url": f"/static/output/{filename}",
                                    "prompt": prompt,
                                    "model": model
                                }
                                
                                if processing_time:
                                    result["processing_time"] = processing_time
                                
                                return result
                    
                    # 如果没有找到具体输出但状态是成功
                    status = task_history.get("status", {})
                    if status.get("completed") and status.get("status_str") == "success":
                        return {
                            "status": "completed",
                            "message": "任务已完成但未找到输出",
                            "prompt": prompt,
                            "model": model
                        }
                
                # 检查任务状态
                status = task_history.get("status", {})
                if status:
                    if status.get("completed"):
                        if status.get("status_str") == "error":
                            return {
                                "status": "error",
                                "message": "任务在ComfyUI中失败",
                                "prompt": prompt,
                                "model": model
                            }
                        else:
                            return {
                                "status": "completed",
                                "message": "任务已完成",
                                "prompt": prompt,
                                "model": model
                            }
                    else:
                        return {
                            "status": "processing",
                            "message": "任务仍在处理中",
                            "prompt": prompt,
                            "model": model
                        }
                
                return {
                    "status": "unknown",
                    "message": "无法确定任务状态",
                    "prompt": prompt,
                    "model": model
                }
                
            elif response.status_code == 404:
                # 任务不存在
                return {
                    "status": "error",
                    "message": "在历史记录中未找到任务"
                }
            else:
                # 其他错误
                return {
                    "status": "error",
                    "message": f"检查历史记录失败: HTTP {response.status_code}"
                }
            
        except Exception as e:
            logger.error(f"检查任务历史记录失败: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "message": f"Failed to check history: {str(e)}"
            }

    def _start_queue_updater(self):
        """启动后台任务更新器"""
        def update_loop():
            while True:
                try:
                    # 使用公共方法名
                    self.update_queue_status()
                    self._cleanup_old_tasks()
                except Exception as e:
                    logger.error(f"更新任务状态失败: {str(e)}")
                time.sleep(20)  # 每20秒更新一次
        
        # 启动后台线程
        updater_thread = threading.Thread(target=update_loop, daemon=True)
        updater_thread.start()
        logger.info("后台任务更新器已启动")

    def _wait_for_completion(self, prompt_id: str) -> Dict:
        """从Redis获取任务状态"""
        try:
            # 检查是否在已完成列表中
            completed_task = self.redis.hget("completed_tasks", prompt_id)
            if completed_task:
                return json.loads(completed_task)
            
            # 检查任务状态
            task_status = self.redis.hget("tasks_status", prompt_id)
            if task_status:
                return json.loads(task_status)
            
            # 如果找不到任务状态，返回未知状态
            return {
                "status": "unknown",
                "message": "任务状态未知"
            }
            
        except Exception as e:
            logger.error(f"获取任务状态失败: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }

    def generate_prompts(self, content: str, style: str, model: str, num_segments: int = 3) -> Dict:
        """调用 GPT 生成视频片段的提示词并返回JSON格式结果"""
        try:
            style_prompts = {
                "ancient": "使用中国传统古风元素,如水墨画风格、古代建筑、古装人物、青砖古墙、翠竹幽径、红色灯笼、古代家具、书法字画等",
                "anime": "使用日本动漫风格,明亮的色彩、夸张的表情、简洁的线条、动漫人物特征、大眼睛、华丽的发型、校园场景等", 
                "cute": "使用可爱萌系风格,圆润的造型、柔和的色彩、温馨的氛围、萌宠元素、粉色系、毛绒玩具、甜点、花朵等",
                "modern": "使用现代都市风格,时尚的场景、现代建筑、写实风格、城市元素、高楼大厦、咖啡厅、商场、地铁等",
                "nature": "使用自然风光风格,壮丽的景色、自然元素、光影效果、山水画卷、森林、湖泊、瀑布、日出日落等"
            }
            
            style_desc = style_prompts.get(style, "")
            
            # 根据不同模型调整提示词
            model_prefix = f"使用{model}模型生成。" if model and model != "default" else ""
            
            # 添加随机性提示和更强调用户内容
            prompt = f"""
            {model_prefix}请根据以下文案内容，创造性地拆分为{num_segments}个连续且各不相同的场景，并为每个场景生成详细的文生视频提示词。

            文案内容:
            {content}

            风格要求:
            {style_desc}

            要求:
            1. 直接生成{num_segments}个详细且各不相同的视频生成提示词，每个提示词不少于100字
            2. 每个提示词必须紧密围绕文案内容展开，确保场景与文案主题高度相关
            3. 每个提示词要包含具体的视觉元素描述，如场景、人物、动作、表情、光线、色彩等细节
            4. 场景之间要保持连贯性和故事性，但每个场景必须有明显的区别
            5. 提示词要充分体现选定的风格特点，融入该风格的独特视觉元素
            6. 避免生成重复或相似的场景描述，确保每个场景都有独特的视觉表现
            7. 使用丰富的形容词和具体的名词，确保AI能生成高质量、细节丰富的视频画面

            请直接返回一个JSON格式，格式如下：
            {{
              "prompts": [
                "第一个场景的详细描述...",
                "第二个场景的详细描述...",
                "第三个场景的详细描述..."
              ],
              "success": true
            }}
            """
            
            # 调用 GPT API
            headers = {
                "Authorization": f"Bearer {self.config.GPT_API_KEY}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.8,  # 增加随机性
                "presence_penalty": 0.6,  # 减少重复
                "frequency_penalty": 0.6  # 减少重复
            }
            
            try:
                response = requests.post(self.config.GPT_API_URL, headers=headers, json=data)
                response.raise_for_status()
                result = response.json()
                content = result['choices'][0]['message']['content']
                
                # 清理 Markdown 代码块标记和其他可能干扰 JSON 解析的内容
                content = content.replace('```json', '').replace('```', '').strip()
                logger.debug(f"GPT API 返回内容: {content}")
                
                # 尝试直接解析返回的JSON
                try:
                    # 尝试直接解析返回的JSON
                    json_response = json.loads(content)
                    
                    if isinstance(json_response, dict) and "prompts" in json_response:
                        # 确保 prompts 是一个列表，并且每个元素都是字符串
                        if isinstance(json_response["prompts"], list):
                            # 清理每个提示词中可能存在的多余空白字符
                            json_response["prompts"] = [p.strip() for p in json_response["prompts"] if p.strip()]
                            return json_response
                except json.JSONDecodeError as e:
                    logger.warning(f"JSON 解析失败: {str(e)}, 尝试其他方法")
                
                # 如果解析失败，则尝试提取JSON部分
                try:
                    # 查找JSON开始和结束的位置
                    start_idx = content.find('{')
                    end_idx = content.rfind('}') + 1
                    if start_idx >= 0 and end_idx > start_idx:
                        json_str = content[start_idx:end_idx]
                        json_response = json.loads(json_str)
                        if isinstance(json_response, dict) and "prompts" in json_response:
                            # 清理每个提示词
                            if isinstance(json_response["prompts"], list):
                                json_response["prompts"] = [p.strip() for p in json_response["prompts"] if p.strip()]
                            return json_response
                except Exception as e:
                    logger.warning(f"JSON 提取失败: {str(e)}, 尝试按行分割")
                
                # 如果仍然解析失败，则尝试从内容中提取提示词
                try:
                    # 查找提示词数组的开始和结束位置
                    prompts_start = content.find('"prompts": [')
                    if prompts_start >= 0:
                        array_start = content.find('[', prompts_start)
                        array_end = content.rfind(']')
                        if array_start >= 0 and array_end > array_start:
                            # 提取数组内容
                            array_content = content[array_start+1:array_end]
                            # 按逗号分割，但要考虑引号内的逗号
                            prompts = []
                            current = ""
                            in_quotes = False
                            for char in array_content:
                                if char == '"' and (len(current) == 0 or current[-1] != '\\'):
                                    in_quotes = not in_quotes
                                if char == ',' and not in_quotes and current.strip():
                                    prompts.append(current.strip().strip('"'))
                                    current = ""
                                else:
                                    current += char
                            if current.strip():
                                prompts.append(current.strip().strip('"'))
                            
                            # 清理提示词
                            prompts = [p.strip() for p in prompts if p.strip()]
                            return {
                                "prompts": prompts[:num_segments],
                                "success": True
                            }
                except Exception as e:
                    logger.warning(f"提示词提取失败: {str(e)}, 使用最后的备选方案")
                
                # 最后的备选方案：按行分割处理
                prompts = [p.strip() for p in content.strip().split('\n') 
                           if p.strip() and not p.strip().startswith('{') and not p.strip().startswith('}') 
                           and not p.strip().startswith('"prompts":') and not p.strip().startswith('"success":')]
                
                # 过滤掉可能的 JSON 语法元素
                prompts = [p.strip('"').strip(',').strip() for p in prompts]
                prompts = [p for p in prompts if p and len(p) > 20]  # 只保留有意义的长文本
                
                return {
                    "prompts": prompts[:num_segments],
                    "success": True
                }
                
            except Exception as e:
                logger.error(f"调用 GPT API 失败: {str(e)}")
                return {
                    "prompts": [],
                    "success": False,
                    "error": str(e)
                }
        except Exception as e:
            logger.error(f"生成提示词失败: {str(e)}")
            return {
                "prompts": [],
                "success": False,
                "error": str(e)
            }

    def generate_video(self, prompt: str, model: str, client_id: str = None, batch_id: str = None, segment_index: int = None, total_segments: int = None, content: str = None, use_mock: bool = False) -> Dict:
        """
        调用 ComfyUI 生成视频
        
        Args:
            prompt: 视频生成提示词
            model: 使用的模型名称
            client_id: 客户端ID，用于跟踪任务
            batch_id: 批次ID，用于分组任务
            segment_index: 片段索引
            total_segments: 总片段数
            content: 内容描述
            use_mock: 是否使用模拟数据
            
        Returns:
            Dict: 包含任务ID和状态的字典
        """
        # 如果启用了模拟模式，使用模拟数据
        if use_mock:
            logger.info("使用模拟数据生成视频")
            return self.mock_generate_video(prompt, model, client_id)
        
        try:
            # 添加更多调试日志
            logger.debug(f"开始生成视频 - 模型: {model}, 客户端ID: {client_id}")
            logger.debug(f"提示词: {prompt[:100]}...")  # 只打印前100个字符
            
            # 1. 加载工作流配置
            logger.debug(f"正在加载工作流配置: {model}")
            workflow = self._load_workflow(model)
            
            # 2. 验证工作流配置
            logger.debug("正在验证工作流配置")
            self._validate_workflow(workflow)
            
            # 3. 更新提示词和种子
            logger.debug("正在更新工作流中的提示词和种子")
            
            # 生成随机种子
            random_seed = random.randint(1, 2**32 - 1)
            
            # 根据不同模型类型更新提示词和种子
            prompt_updated = False
            seed_updated = False
            
            for node_id, node in workflow.items():
                # 检查节点类型和输入
                if "inputs" in node:
                    # 处理提示词 - 支持多种节点类型
                    if node.get("class_type") == "CLIPTextEncode" and "text" in node["inputs"]:
                        node["inputs"]["text"] = prompt
                        prompt_updated = True
                        logger.debug(f"已更新CLIPTextEncode节点 {node_id} 的提示词")
                    
                    elif node.get("class_type") == "WanVideoTextEncode" and "positive_prompt" in node["inputs"]:
                        node["inputs"]["positive_prompt"] = prompt
                        prompt_updated = True
                        logger.debug(f"已更新WanVideoTextEncode节点 {node_id} 的提示词")
                    
                    # 处理种子 - 支持多种节点类型
                    if "seed" in node["inputs"]:
                        node["inputs"]["seed"] = random_seed
                        seed_updated = True
                        logger.debug(f"已更新节点 {node_id} 的种子为 {random_seed}")
            
            # 如果没有找到合适的节点来更新提示词，记录警告
            if not prompt_updated:
                logger.warning(f"未找到合适的节点来更新提示词，原始工作流将保持不变")
            
            # 如果没有更新种子，记录信息
            if not seed_updated:
                logger.info(f"未找到种子节点，将使用工作流中的默认种子")
            
            # 4. 准备客户端ID
            # 生成一个随机的客户端ID，如果没有提供
            request_client_id = client_id or str(uuid.uuid4())
            logger.debug(f"使用客户端ID: {request_client_id}")
            
            # 5. 提交工作流到 ComfyUI
            logger.debug(f"正在提交工作流到ComfyUI: {self.config.COMFYUI_URL}/prompt")
            
            # 创建请求数据，直接包含client_id
            data = {
                "prompt": workflow,
                "client_id": request_client_id
            }
            
            # 使用Authorization头进行认证
            headers = {
                "Authorization": f"Bearer {self.config.COMFYUI_TOKEN}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(
                f"{self.config.COMFYUI_URL}/prompt",
                json=data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                logger.error(f"ComfyUI API 错误: {error_msg}")
                raise ComfyUIError(error_msg, error_code="COMFYUI_HTTP_ERROR")
            
            result = response.json()
            if "prompt_id" not in result:
                logger.error(f"ComfyUI 响应中没有 prompt_id: {json.dumps(result, indent=2)}")
                error_msg = "No prompt_id in response"
                if "error" in result:
                    error_msg = f"{error_msg}: {result['error']}"
                elif "detail" in result:
                    error_msg = f"{error_msg}: {result['detail']}"
                raise ComfyUIError(error_msg, error_code="COMFYUI_INVALID_RESPONSE")
            
            prompt_id = result["prompt_id"]
            logger.info(f"成功提交工作流，获取到prompt_id: {prompt_id}")
            
            # 添加任务到Redis
            task_data = {
                "status": "pending",
                "message": "Task initialized",
                "prompt": prompt,
                "model": model,
                "created_at": time.time(),
                "seed": random_seed
            }
            
            # 如果有批次信息，添加到任务数据中
            if batch_id:
                task_data["batch_id"] = batch_id
                task_data["segment_index"] = segment_index
                task_data["total_segments"] = total_segments
                task_data["content"] = content
            
            self.redis.hset("tasks_status", prompt_id, json.dumps(task_data))
            
            # 添加到等待队列
            self.redis.sadd("pending_tasks", prompt_id)
            
            return {
                "success": True,
                "status": "pending",
                "prompt_id": prompt_id,
                "client_id": request_client_id,
                "seed": random_seed
            }
            
        except Exception as e:
            logger.error(f"生成视频失败: {str(e)}", exc_info=True)
            # 添加更详细的错误信息
            error_message = "生成视频失败"
            error_code = "VIDEO_GENERATION_FAILED"
            
            if isinstance(e, ComfyUIError):
                error_code = e.error_code
            
            return {
                "success": False,
                "error": error_message,
                "error_code": error_code,
                "details": str(e)
            }

    def check_video_status(self, prompt_id: str, use_mock: bool = False) -> Dict:
        """
        检查视频生成任务的状态
        
        Args:
            prompt_id: ComfyUI的提示ID
            use_mock: 是否使用模拟数据
            
        Returns:
            Dict: 包含任务状态和输出路径(如果完成)的字典
        """
        # 如果启用了模拟模式，使用模拟数据
        if use_mock:
            return self.mock_check_video_status(prompt_id)
        
        try:
            # 使用Authorization头进行认证
            headers = {
                "Authorization": f"Bearer {self.config.COMFYUI_TOKEN}"
            }
            
            # 检查任务历史
            response = requests.get(
                f"{self.config.COMFYUI_URL}/history/{prompt_id}",
                headers=headers
            )
            
            if response.status_code != 200:
                raise ComfyUIError(f"Failed to get history: {response.text}")
            
            history = response.json()
            
            # 检查是否完成
            if history.get("outputs"):
                outputs = history["outputs"]
                
                # 检查是否有视频输出
                if "video" in outputs:
                    video_info = outputs["video"][0]
                    filename = video_info["filename"]
                    
                    # 构建完整的URL路径，使用Authorization头
                    video_url = f"{self.config.COMFYUI_URL}/view?filename={filename}"
                    local_path = os.path.join(self.config.OUTPUT_DIR, filename)
                    
                    # 下载视频到本地，传递headers
                    self._download_video(video_url, local_path)
                    
                    return {
                        "status": "completed",
                        "output_path": local_path,
                        "video_url": f"/static/output/{filename}"  # 相对于Web服务的URL
                    }
                
                # 检查是否有图像输出
                elif "images" in outputs:
                    image_info = outputs["images"][0]
                    filename = image_info["filename"]
                    
                    # 构建完整的URL路径，使用Authorization头
                    image_url = f"{self.config.COMFYUI_URL}/view?filename={filename}"
                    local_path = os.path.join(self.config.OUTPUT_DIR, filename)
                    
                    # 下载图像到本地，传递headers
                    self._download_video(image_url, local_path)
                    
                    return {
                        "status": "completed",
                        "output_path": local_path,
                        "image_url": f"/static/output/{filename}"  # 相对于Web服务的URL
                    }
            
            # 检查队列状态
            queue_response = requests.get(
                f"{self.config.COMFYUI_URL}/prompt",
                headers=headers
            )
            
            if queue_response.status_code == 200:
                queue_info = queue_response.json()
                
                # 检查是否在执行中
                executing = queue_info.get("exec_info", {}).get("queue_running", [])
                for item in executing:
                    if item[0] == prompt_id:
                        return {
                            "status": "processing",
                            "message": "视频正在生成中",
                            "progress": 50  # 假设进度为50%
                        }
                
                # 检查是否在队列中
                pending = queue_info.get("exec_info", {}).get("queue_pending", [])
                for i, item in enumerate(pending):
                    if item[0] == prompt_id:
                        return {
                            "status": "pending",
                            "message": f"等待中，队列位置: {i+1}",
                            "queue_position": i+1
                        }
            
            # 如果没有找到任务，可能已经完成但没有输出，或者出错了
            return {
                "status": "unknown",
                "message": "无法确定任务状态，可能已完成但没有输出，或者出错了"
            }
            
        except Exception as e:
            logger.error(f"检查视频状态失败: {str(e)}")
            return {
                "status": "error",
                "message": f"检查状态失败: {str(e)}"
            }

    def _download_video(self, url: str, local_path: str) -> None:
        """
        从ComfyUI服务器下载视频到本地
        
        Args:
            url: 视频URL
            local_path: 本地保存路径
        """
        try:
            # 确保输出目录存在
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # 如果文件已存在，不再下载
            if os.path.exists(local_path):
                return
            
            # 使用Authorization头进行认证
            headers = {
                "Authorization": f"Bearer {self.config.COMFYUI_TOKEN}"
            }
            
            # 下载文件，使用Authorization头
            response = requests.get(url, headers=headers, stream=True)
            response.raise_for_status()
            
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                
            logger.info(f"文件已下载到: {local_path}")
            
        except Exception as e:
            logger.error(f"下载文件失败: {str(e)}")
            raise

    def get_history(self, prompt_id: str) -> Dict:
        """获取历史记录"""
        try:
            response = requests.get(f"{self.config.COMFYUI_URL}/history/{prompt_id}")
            
            if response.status_code != 200:
                return {'success': False, 'error': f'获取历史记录失败: {response.text}'}
            
            return response.json()
            
        except Exception as e:
            logger.error(f"获取历史记录失败: {str(e)}")
            return {'success': False, 'error': str(e)}

    def _cleanup_old_tasks(self):
        """清理过期任务和错误任务"""
        try:
            current_time = time.time()
            max_age = 7 * 24 * 60 * 60  # 改为7天，而不是24小时
            
            # 检查错误状态的任务
            all_tasks = self.redis.hgetall("tasks_status")
            for task_id_bytes, task_data_bytes in all_tasks.items():
                task_id = task_id_bytes.decode('utf-8') if isinstance(task_id_bytes, bytes) else task_id_bytes
                task_data = json.loads(task_data_bytes) if isinstance(task_data_bytes, bytes) else json.loads(task_data_bytes)
                
                # 检查是否是错误状态且已经超过一定时间
                if task_data.get("status") == "error":
                    # 如果错误任务已经存在超过1小时，移到已完成列表
                    if "last_updated" in task_data and current_time - task_data["last_updated"] > 3600:
                        self.redis.hset("completed_tasks", task_id, json.dumps(task_data))
                        self.redis.hdel("tasks_status", task_id)
                        logger.info(f"错误任务 {task_id} 已移至已完成列表")
                
                # 检查是否是未知状态的任务
                elif task_data.get("status") == "unknown":
                    # 重新检查历史记录
                    history_result = self._check_task_history(task_id)
                    if history_result and history_result.get("status") in ["completed", "error"]:
                        # 更新任务状态
                        self.redis.hset("completed_tasks", task_id, json.dumps(history_result))
                        self.redis.hdel("tasks_status", task_id)
                        logger.info(f"未知状态任务 {task_id} 已更新为 {history_result.get('status')}")
            
            # 清理过期的已完成任务 - 改为7天而不是24小时
            completed_tasks = self.redis.hgetall("completed_tasks")
            for task_id_bytes, task_data_bytes in completed_tasks.items():
                task_id = task_id_bytes.decode('utf-8') if isinstance(task_id_bytes, bytes) else task_id_bytes
                task_data = json.loads(task_data_bytes) if isinstance(task_data_bytes, bytes) else json.loads(task_data_bytes)
                
                # 检查任务是否过期 - 使用更长的保留期
                if "completed_at" in task_data and current_time - task_data["completed_at"] > max_age:
                    self.redis.hdel("completed_tasks", task_id)
                    logger.info(f"已删除过期任务 {task_id}")
                elif "last_updated" in task_data and current_time - task_data["last_updated"] > max_age:
                    self.redis.hdel("completed_tasks", task_id)
                    logger.info(f"已删除过期任务 {task_id}")
        
        except Exception as e:
            logger.error(f"清理任务失败: {str(e)}", exc_info=True)

    def update_queue_status(self):
        """
        公共方法，用于更新队列状态
        这是为了兼容现有代码而添加的
        """
        try:
            logger.info("开始执行 update_queue_status 方法")
            result = self._update_queue_status()
            logger.info("update_queue_status 方法执行完成")
            return result
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"update_queue_status 方法执行失败: {str(e)}")
            logger.error(f"错误堆栈: {error_trace}")
            # 重新抛出异常，让调用者知道发生了错误
            raise 