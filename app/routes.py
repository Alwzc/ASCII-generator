from flask import Blueprint, render_template, request, jsonify, current_app, Response, url_for, send_file
from app.video_generator import VideoGenerator
from app.video_processor import VideoProcessor
import os
import json
import queue
import threading
import asyncio
from app.utils.error_handler import ErrorHandler, VideoProcessError
import edge_tts
import logging
from pathlib import Path
import requests
from config import Config
import time
import uuid
from datetime import datetime
from app.extensions import init_redis

# 获取当前模块的日志记录器
logger = logging.getLogger(__name__)

main = Blueprint('main', __name__, url_prefix='')  # 确保没有 url_prefix

# 存储每个任务的进度信息
progress_queues = {}

error_handler = ErrorHandler()

@main.before_request
def before_request():
    """每个请求前执行"""
    if request.is_json:
        # print(f"JSON数据: {request.get_json(silent=True)}")
        pass

@main.after_request
def after_request(response):
    """每个请求后执行"""
    return response

@main.route('/')
def index():
    # 获取 model 目录下的所有 JSON 文件
    model_dir = Path("model")
    models = []
    
    if model_dir.exists():
        for file in model_dir.glob("*.json"):
            model_id = file.stem  # 文件名（不含扩展名）
            # 可以从 JSON 中读取模型名称等信息
            models.append({
                "id": model_id,
                "name": model_id.replace("_", " ").title()  # 简单处理显示名称
            })
    
    return render_template('index.html', models=models)

@main.route('/generate', methods=['POST', 'OPTIONS'])
def generate():
    """生成提示词接口"""
    print(f"请求数据: {request.get_json()}")
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': '没有接收到数据'
            })
        
        # 修复参数名称，支持content或theme作为输入
        content = data.get('content') or data.get('theme')
        if not content:
            return jsonify({
                'success': False,
                'message': '请输入视频文案'
            })
        
        num_segments = int(data.get('num_segments', 3))
        style = data.get('style', 'modern')  # 添加默认风格参数
        model = data.get('model', 'default')  # 添加默认模型参数
        
        print(f"处理请求 - 文案: {content}, 风格: {style}, 模型: {model}, 片段数: {num_segments}")
        
        # 初始化生成器
        generator = VideoGenerator()
        
        # 生成提示词 - 修复参数调用
        result = generator.generate_prompts(content, style, model, num_segments)
        
        if not result.get('success', False):
            return jsonify({
                'success': False,
                'message': result.get('error', '提示词生成失败，请重试')
            })
        
        return jsonify({
            'success': True,
            'prompts': result.get('prompts', []),
            'message': '提示词生成成功'
        })
        
    except Exception as e:
        print(f"生成路由错误: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'发生错误：{str(e)}'
        })

@main.route('/generate_video', methods=['POST'])
def generate_video():
    """视频生成接口"""
    data = request.get_json()
    prompt = data.get('prompt')
    model = data.get('model')
    client_id = data.get('client_id')  # 从请求中获取客户端ID
    
    if not prompt:
        return jsonify({'error': '没有提供提示词'}), 400
    
    try:
        # 初始化生成器
        generator = VideoGenerator()
        
        # 生成视频
        result = generator.generate_video(prompt, model, client_id)
        
        # 返回任务信息
        return jsonify({
            'success': True,
            'task_id': result.get('prompt_id'),
            'client_id': result.get('client_id'),
            'status': result.get('status')
        })
        
    except Exception as e:
        logger.error(f"视频生成请求失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@main.route('/check_video_status/<prompt_id>')
def check_video_status(prompt_id):
    """检查视频生成状态"""
    try:
        generator = VideoGenerator()
        status = generator.check_video_status(prompt_id)
        
        return jsonify({
            'success': True,
            **status
        })
        
    except Exception as e:
        logger.error(f"检查视频状态失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@main.route('/batch_generate_video', methods=['POST'])
def batch_generate_video():
    """批量视频生成接口"""
    data = request.get_json()
    prompts = data.get('prompts')
    model = data.get('model')
    client_id = data.get('client_id')
    
    if not prompts or not isinstance(prompts, list):
        return jsonify({'error': '没有提供有效的提示词列表'}), 400
    
    try:
        # 创建任务ID
        task_id = client_id or str(threading.get_ident())
        progress_queues[task_id] = queue.Queue()
        
        def progress_callback(msg):
            progress_queues[task_id].put(msg)
        
        # 获取当前应用实例
        app = current_app._get_current_object()
        
        def generate_task():
            with app.app_context():
                try:
                    generator = VideoGenerator()
                    results = []
                    
                    # 逐个处理提示词
                    for i, prompt in enumerate(prompts):
                        # 更新进度
                        progress_callback({
                            'type': 'progress',
                            'data': {
                                'current': i + 1,
                                'total': len(prompts),
                                'message': f'正在生成第 {i+1}/{len(prompts)} 个视频片段',
                                'prompt': prompt[:100] + '...' if len(prompt) > 100 else prompt
                            }
                        })
                        
                        # 生成视频
                        result = generator.generate_video(prompt, model, f"{client_id}_{i}" if client_id else None)
                        prompt_id = result.get('prompt_id')
                        
                        # 等待视频生成完成
                        while True:
                            status = generator.check_video_status(prompt_id)
                            if status.get('status') in ['completed', 'error']:
                                break
                            time.sleep(2)  # 每2秒检查一次
                        
                        # 添加结果
                        results.append({
                            'prompt': prompt,
                            'prompt_id': prompt_id,
                            'status': status.get('status'),
                            'output_path': status.get('output_path', ''),
                            'video_url': status.get('video_url', '')
                        })
                        
                        # 更新单个视频完成状态
                        progress_callback({
                            'type': 'segment_complete',
                            'data': {
                                'index': i,
                                'prompt': prompt,
                                'path': status.get('output_path', ''),
                                'video_url': status.get('video_url', '')
                            }
                        })
                    
                    # 任务完成
                    progress_callback({
                        'type': 'complete',
                        'data': {
                            'segments': results
                        }
                    })
                    
                except Exception as e:
                    logger.error(f"批量视频生成失败: {str(e)}")
                    progress_callback({
                        'type': 'error',
                        'data': {'message': str(e)}
                    })
                finally:
                    # 标记队列结束
                    progress_callback(None)
        
        # 启动生成任务
        thread = threading.Thread(target=generate_task)
        thread.start()
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'client_id': client_id
        })
        
    except Exception as e:
        logger.error(f"批量视频生成请求失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@main.route('/progress/<task_id>')
def progress(task_id):
    """SSE endpoint for progress updates"""
    def generate():
        if task_id not in progress_queues:
            yield "data: " + json.dumps({'error': '任务不存在'}) + "\n\n"
            return
            
        queue = progress_queues[task_id]
        while True:
            try:
                msg = queue.get(timeout=60)  # 60秒超时
                if msg is None:  # 队列结束标记
                    break
                yield "data: " + json.dumps(msg) + "\n\n"
            except queue.Empty:
                break
            
        # 清理
        if task_id in progress_queues:
            del progress_queues[task_id]
    
    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache'}
    )

@main.route('/process_video', methods=['POST'])
def process_video():
    """处理已生成的视频片段"""
    data = request.get_json()
    segments = data.get('segments')
    settings = data.get('settings')
    
    if not segments:
        return jsonify({'error': '没有提供视频片段'}), 400
        
    # 创建任务ID
    task_id = str(threading.get_ident())
    progress_queues[task_id] = queue.Queue()
    
    def progress_callback(msg):
        progress_queues[task_id].put(msg)
    
    # 获取当前应用实例
    app = current_app._get_current_object()
    
    async def process_task():
        with app.app_context():  # 使用应用实例创建上下文
            try:
                processor = VideoProcessor()
                video_segments = [
                    VideoSegment(
                        prompt=s['prompt'],
                        duration=s.get('duration', 5),
                        output_path=s['path']
                    ) for s in segments
                ]
                
                final_path = await processor.process_video(
                    video_segments,
                    settings,
                    progress_callback
                )
                
                # 任务完成
                progress_queues[task_id].put({
                    'type': 'complete',
                    'data': {
                        'final_path': final_path
                    }
                })
            except Exception as e:
                logger.error(f"视频处理失败: {str(e)}")
                progress_queues[task_id].put({
                    'type': 'error',
                    'data': {'message': str(e)}
                })
            finally:
                progress_queues[task_id].put(None)
    
    # 启动处理任务
    threading.Thread(target=lambda: asyncio.run(process_task())).start()
    
    return jsonify({
        'status': 'success',
        'task_id': task_id
    })

@main.route('/test_voice', methods=['POST'])
def test_voice():
    """测试语音合成"""
    try:
        data = request.get_json()
        speaker = data.get('speaker')
        speed = data.get('speed')
        volume = data.get('volume')
        
        # 测试文本
        test_text = "这是一段测试语音，用于预览配音效果。"
        
        # 生成测试音频
        output_path = os.path.join(
            current_app.config['OUTPUT_FOLDER'],
            'test_audio.mp3'
        )
        
        communicate = edge_tts.Communicate(
            text=test_text,
            voice=speaker,
            rate=f"+{int((speed-1)*100)}%",
            volume=f"+{int(volume-100)}%"
        )
        
        asyncio.run(communicate.save(output_path))
        
        return jsonify({
            'status': 'success',
            'audioUrl': '/static/output/test_audio.mp3'
        })
        
    except Exception as e:
        error_info = error_handler.handle_error(e, {
            'endpoint': 'test_voice',
            'input': data
        })
        return jsonify(error_info), 500

# 添加代理路由
@main.route('/api/proxy/<path:subpath>', methods=['GET', 'POST'])
def proxy(subpath):
    """代理转发请求到 ComfyUI 服务器"""
    try:
        # 创建配置实例
        config = Config()
        
        # 构建目标 URL，添加token参数
        target_url = f"{config.COMFYUI_URL}/{subpath}"
        if '?' in target_url:
            target_url += f"&token={config.COMFYUI_TOKEN}"
        else:
            target_url += f"?token={config.COMFYUI_TOKEN}"
        
        # 转发请求
        if request.method == 'GET':
            response = requests.get(
                target_url,
                params=request.args
            )
        else:
            response = requests.post(
                target_url,
                headers={
                    'Content-Type': request.headers.get('Content-Type', 'application/json')
                },
                json=request.json
            )
        
        return jsonify(response.json()), response.status_code
        
    except Exception as e:
        logger.error(f"代理请求失败: {str(e)}")
        return jsonify({'error': str(e)}), 500

@main.route('/api/generate-video', methods=['POST'])
def generate_video_api():
    """生成视频API"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': '无效的请求数据'})
        
        prompt = data.get('prompt')
        model = data.get('model')
        batch_id = data.get('batch_id')
        segment_index = data.get('segment_index')
        total_segments = data.get('total_segments')
        content = data.get('content')
        
        if not prompt or not model:
            return jsonify({'success': False, 'error': '缺少必要参数'})
        
        # 创建视频生成器实例
        generator = VideoGenerator()
        
        # 生成视频
        result = generator.generate_video(
            prompt=prompt,
            model=model,
            batch_id=batch_id,
            segment_index=segment_index,
            total_segments=total_segments,
            content=content
        )
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'prompt_id': result.get('prompt_id'),
                'status': result.get('status'),
                'message': '视频生成任务已提交'
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', '视频生成失败')
            })
    
    except Exception as e:
        current_app.logger.error(f"生成视频失败: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)})

@main.route('/api/history/<task_id>', methods=['GET'])
def get_history_api(task_id):
    """获取历史记录 API"""
    try:
        generator = VideoGenerator()
        history = generator._wait_for_completion(task_id)
        return jsonify(history)
    except FileNotFoundError:
        return jsonify({'error': 'History file not found'}), 404
    except KeyError:
        return jsonify({'error': 'Task not found'}), 404
    except Exception as e:
        logger.error(f"获取历史记录失败: {str(e)}")
        return jsonify({'error': str(e)}), 500

@main.route('/view')
def view_file():
    """查看文件(图片/视频)"""
    try:
        filename = request.args.get('filename')
        file_type = request.args.get('type', 'output')
        subfolder = request.args.get('subfolder', '')
        preview = request.args.get('preview', 'false').lower() == 'true'
        
        # 验证文件名
        if not filename:
            return '缺少文件名参数', 400
            
        # 构建文件路径
        base_dir = current_app.config.get('OUTPUT_DIR') if file_type == 'output' else current_app.config.get('INPUT_DIR')
        
        if not base_dir:
            if file_type == 'output':
                base_dir = os.path.join(os.getcwd(), 'static', 'output')
            else:
                base_dir = os.path.join(os.getcwd(), 'static', 'input')
        
        # 添加子文件夹
        if subfolder:
            base_dir = os.path.join(base_dir, subfolder)
            
        file_path = os.path.join(base_dir, filename)
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            current_app.logger.error(f"文件不存在: {file_path}")
            return f'文件不存在: {filename}', 404
            
        # 确定文件类型
        mime_type = None
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            mime_type = f'image/{os.path.splitext(filename)[1][1:].lower()}'
        elif filename.lower().endswith(('.mp4', '.webm')):
            mime_type = f'video/{os.path.splitext(filename)[1][1:].lower()}'
            
        # 发送文件
        return send_file(
            file_path,
            mimetype=mime_type,
            as_attachment=not preview,  # 如果是预览模式，不作为附件发送
            download_name=filename if not preview else None
        )
        
    except Exception as e:
        current_app.logger.error(f"文件访问失败: {str(e)}", exc_info=True)
        return str(e), 500

@main.route('/api/test-prompts', methods=['GET'])
def get_test_prompts():
    """获取测试提示词"""
    try:
        video_generator = VideoGenerator()
        return jsonify(video_generator.get_mock_prompts())
    except Exception as e:
        logger.error(f"获取测试提示词失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@main.route('/api/generate-videos', methods=['POST'])
def generate_videos():
    """批量生成视频"""
    try:
        data = request.json
        prompts = data.get('prompts', [])
        model = data.get('model')
        test_mode = data.get('test_mode', False)  # 获取测试模式标志
        
        if not prompts:
            return jsonify({
                "success": False,
                "error": "提示词列表为空"
            })
            
        if not model:
            return jsonify({
                "success": False,
                "error": "未指定模型"
            })
        
        # 生成唯一的客户端ID
        client_id = str(uuid.uuid4())
        
        # 创建视频生成器
        video_generator = VideoGenerator()
        
        # 批量提交视频生成任务
        tasks = []
        for i, prompt in enumerate(prompts):
            try:
                # 使用测试模式标志
                result = video_generator.generate_video(
                    prompt=prompt,
                    model=model,
                    client_id=client_id,
                    use_mock=test_mode  # 传递测试模式标志
                )
                
                # 添加任务信息
                task_info = {
                    "id": result["prompt_id"],
                    "prompt": prompt,
                    "model": model,
                    "status": result["status"],
                    "segment_index": i,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "client_id": client_id,
                    "is_test": test_mode  # 标记为测试任务
                }
                
                # 保存任务信息到数据库或缓存
                # ...
                
                tasks.append(task_info)
                
            except Exception as e:
                logger.error(f"生成视频失败 (提示词 {i+1}): {str(e)}")
                return jsonify({
                    "success": False,
                    "error": f"生成视频失败 (提示词 {i+1}): {str(e)}"
                })
        
        return jsonify({
            "success": True,
            "tasks": tasks,
            "client_id": client_id
        })
        
    except Exception as e:
        logger.error(f"批量视频生成失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        })

@main.route('/api/test-connection', methods=['GET'])
def test_connection():
    """测试与ComfyUI服务器的连接"""
    try:
        video_generator = VideoGenerator()
        result = video_generator.test_connection()
        return jsonify(result)
    except Exception as e:
        logger.error(f"测试连接失败: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"测试连接失败: {str(e)}",
            "error": str(e)
        })

@main.route('/api/task-status', methods=['GET'])
def get_task_status():
    """获取所有任务的状态"""
    try:
        # 初始化Redis连接 - 使用current_app而不是app
        redis_client = init_redis(current_app)
        
        # 获取活跃任务
        active_tasks = redis_client.hgetall("tasks_status")
        
        # 获取已完成任务
        completed_tasks = redis_client.hgetall("completed_tasks")
        
        # 合并任务数据
        all_tasks = {}
        
        # 处理活跃任务
        for task_id, task_data in active_tasks.items():
            task_id = task_id.decode('utf-8') if isinstance(task_id, bytes) else task_id
            task_data = task_data.decode('utf-8') if isinstance(task_data, bytes) else task_data
            all_tasks[task_id] = json.loads(task_data)
        
        # 处理已完成任务
        for task_id, task_data in completed_tasks.items():
            task_id = task_id.decode('utf-8') if isinstance(task_id, bytes) else task_id
            task_data = task_data.decode('utf-8') if isinstance(task_data, bytes) else task_data
            all_tasks[task_id] = json.loads(task_data)
        
        return jsonify(all_tasks)
    
    except Exception as e:
        # 使用current_app而不是app
        current_app.logger.error(f"获取任务状态失败: {str(e)}")
        return jsonify({"error": str(e)}), 500

@main.route('/api/health')
def health_check():
    """健康检查"""
    try:
        # 检查Redis连接
        redis_client = init_redis(current_app)
        redis_client.ping()
        
        return jsonify({
            'status': 'healthy',
            'redis': 'connected'
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

@main.route('/api/test-proxy')
def test_proxy():
    """测试代理连接"""
    try:
        response = requests.get(f"{current_app.config['COMFYUI_URL']}/queue")
        return jsonify({
            'status': 'success',
            'message': 'Successfully connected to ComfyUI server',
            'data': response.json()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to connect to ComfyUI server: {str(e)}'
        }), 500

@main.route('/api/task/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    """从Redis中删除任务"""
    try:
        redis_client = init_redis(current_app)
        
        # 从正在运行的任务中删除
        redis_client.hdel('tasks_status', task_id)
        
        # 从已完成任务中删除
        redis_client.hdel('completed_tasks', task_id)
        
        return jsonify({
            'success': True,
            'message': '任务已删除'
        })
        
    except Exception as e:
        logger.error(f"删除任务失败: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@main.route('/api/merge-videos', methods=['POST'])
def merge_videos():
    """合并批次中的视频片段"""
    try:
        data = request.json
        if not data:
            return jsonify({'success': False, 'error': '无效的请求数据'})
        
        batch_id = data.get('batch_id')
        video_paths = data.get('video_paths', [])
        content = data.get('content', '')
        
        if not batch_id or not video_paths:
            return jsonify({'success': False, 'error': '缺少必要参数'})
        
        # 创建视频处理器实例
        processor = VideoProcessor()
        
        # 合并视频
        result = processor.merge_videos(
            batch_id=batch_id,
            video_paths=video_paths,
            content=content
        )
        
        if result.get('success'):
            # 更新Redis中的批次状态
            redis_client = init_redis(current_app)
            batch_data = {
                'status': 'completed',
                'merged_video_url': result.get('merged_video_url'),
                'last_updated': time.time()
            }
            redis_client.hset('batch_status', batch_id, json.dumps(batch_data))
            
            return jsonify({
                'success': True,
                'merged_video_url': result.get('merged_video_url'),
                'message': '视频合并成功'
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', '视频合并失败')
            })
    
    except Exception as e:
        current_app.logger.error(f"合并视频失败: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'error': str(e)})