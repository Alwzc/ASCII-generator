import os
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from moviepy import editor as mpy
import edge_tts
from app.utils.error_handler import VideoProcessingError
import time
from moviepy.editor import VideoFileClip, concatenate_videoclips
from config import Config
from flask import jsonify, send_file, request
import json
import uuid
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class VideoSegment:
    prompt: str
    duration: int
    output_path: str
    audio_path: str = ""
    subtitle_settings: Dict = None

class VideoProcessor:
    """视频处理器 - 处理视频合并、添加字幕和音频"""
    
    def __init__(self):
        """初始化视频处理器"""
        # 确保从正确的模块导入 Config
        try:
            from app.config import Config
            self.config = Config()
        except ImportError:
            from config import Config
            self.config = Config()
        
        # 确保输出目录存在
        self._ensure_output_dir()
        
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
    
    def merge_videos(self, batch_id: str, video_paths: List[str], content: str = '') -> Dict:
        """
        合并多个视频片段，并添加字幕和音频
        
        Args:
            batch_id: 批次ID
            video_paths: 视频路径列表
            content: 视频内容描述，用于生成字幕
            
        Returns:
            Dict: 包含合并结果的字典
        """
        try:
            logger.info(f"开始合并视频 - 批次ID: {batch_id}, 视频数量: {len(video_paths)}")
            
            if not video_paths:
                return {'success': False, 'error': '没有可用的视频文件'}
            
            # 处理视频路径，确保是完整的文件路径
            processed_paths = []
            for path in video_paths:
                # 如果是相对URL路径，转换为本地文件路径
                if path.startswith('/static/output/'):
                    filename = os.path.basename(path)
                    full_path = os.path.join(self.config.OUTPUT_DIR, filename)
                    processed_paths.append(full_path)
                elif not path.startswith(('http://', 'https://')):
                    # 如果是相对路径，转换为绝对路径
                    if not os.path.isabs(path):
                        full_path = os.path.join(self.config.OUTPUT_DIR, path)
                        processed_paths.append(full_path)
                    else:
                        processed_paths.append(path)
                else:
                    # 如果是URL，需要先下载
                    logger.warning(f"不支持直接合并URL视频: {path}")
                    return {'success': False, 'error': '不支持直接合并URL视频'}
            
            # 检查所有视频文件是否存在
            for path in processed_paths:
                if not os.path.exists(path):
                    logger.error(f"视频文件不存在: {path}")
                    return {'success': False, 'error': f'视频文件不存在: {os.path.basename(path)}'}
            
            # 生成输出文件名
            timestamp = int(time.time())
            output_filename = f"merged_{batch_id}_{timestamp}.mp4"
            output_path = os.path.join(self.config.OUTPUT_DIR, output_filename)
            
            # 创建临时文件列表
            list_file_path = os.path.join(self.config.OUTPUT_DIR, f"filelist_{batch_id}_{timestamp}.txt")
            with open(list_file_path, 'w', encoding='utf-8') as f:
                for path in processed_paths:
                    f.write(f"file '{path}'\n")
            
            # 使用FFmpeg合并视频
            ffmpeg_cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', list_file_path,
                '-c', 'copy',
                output_path
            ]
            
            logger.info(f"执行FFmpeg命令: {' '.join(ffmpeg_cmd)}")
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            
            # 删除临时文件列表
            if os.path.exists(list_file_path):
                os.remove(list_file_path)
            
            if result.returncode != 0:
                logger.error(f"FFmpeg合并视频失败: {result.stderr}")
                return {'success': False, 'error': f'合并视频失败: {result.stderr[:200]}...'}
            
            # 如果有内容描述，生成字幕
            if content:
                # 这里可以添加生成字幕的代码
                # 例如，可以调用GPT API生成字幕，然后使用FFmpeg添加字幕
                pass
            
            # 返回合并后的视频URL
            merged_video_url = f"/static/output/{output_filename}"
            logger.info(f"视频合并成功: {merged_video_url}")
            
            return {
                'success': True,
                'merged_video_url': merged_video_url,
                'output_path': output_path
            }
            
        except Exception as e:
            logger.error(f"合并视频失败: {str(e)}", exc_info=True)
            return {'success': False, 'error': str(e)}
        
    def process_videos(self, video_segments, theme):
        """处理视频：合并、添加配音和字幕"""
        try:
            # 合并视频
            video_paths = [segment['path'] for segment in video_segments]
            merged_video = self.merge_videos(video_paths)
            
            # 生成配音
            audio_path = os.path.join(self.config.OUTPUT_DIR, 'voiceover.mp3')
            asyncio.run(self.generate_voiceover(theme, audio_path))
            
            # TODO: 添加配音和字幕到视频
            
            return merged_video
            
        except Exception as e:
            raise Exception(f"视频处理失败：{str(e)}")

    def _ensure_dirs(self):
        """确保所需目录存在"""
        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)
        os.makedirs(os.path.join(self.config.OUTPUT_DIR, 'audio'), exist_ok=True)
        os.makedirs(os.path.join(self.config.OUTPUT_DIR, 'final'), exist_ok=True)
        
    async def process_video(self, segments: List[VideoSegment], settings: Dict, callback=None) -> str:
        """处理视频片段，添加字幕、配音和特效"""
        try:
            total_steps = len(segments) * 2 + 1  # 配音、字幕和最终合并
            current_step = 0
            
            # 1. 为每个片段生成配音
            for i, segment in enumerate(segments):
                if callback:
                    current_step += 1
                    callback({
                        'type': 'progress',
                        'data': {
                            'current': current_step,
                            'total': total_steps,
                            'status': f'正在生成第 {i + 1} 个片段的配音'
                        }
                    })
                    
                audio_path = os.path.join(
                    self.config.OUTPUT_DIR,
                    'audio',
                    f'audio_{i + 1}_{int(time.time())}.mp3'
                )
                
                await self.generate_audio(
                    segment.prompt,
                    audio_path,
                    settings['voice']
                )
                segment.audio_path = audio_path
                
            # 2. 为每个片段添加字幕和配音
            processed_clips = []
            for i, segment in enumerate(segments):
                if callback:
                    current_step += 1
                    callback({
                        'type': 'progress',
                        'data': {
                            'current': current_step,
                            'total': total_steps,
                            'status': f'正在处理第 {i + 1} 个片段的字幕'
                        }
                    })
                
                # 加载视频片段
                video = mpy.VideoFileClip(segment.output_path)
                
                # 添加配音
                audio = mpy.AudioFileClip(segment.audio_path)
                video = video.set_audio(audio)
                
                # 添加字幕
                subtitle = self.create_subtitle(
                    segment.prompt,
                    video.size,
                    settings['subtitle']
                )
                video = mpy.CompositeVideoClip([video, subtitle])
                
                # 应用转场效果
                if i > 0 and settings['transition']['effect'] != 'none':
                    video = self.apply_transition(
                        video,
                        settings['transition']
                    )
                    
                # 应用滤镜
                video = self.apply_filters(video, settings['filter'])
                
                # 调整尺寸
                video = self.resize_video(video, settings['clip']['size'])
                
                # 裁剪比例
                video = self.crop_video(video, settings['clip']['cropRatio'])
                
                # 调整速度
                if settings['clip']['speed'] != 1.0:
                    video = video.fx(mpy.vfx.speedx, settings['clip']['speed'])
                
                processed_clips.append(video)
                
            # 3. 合并所有片段
            if callback:
                current_step += 1
                callback({
                    'type': 'progress',
                    'data': {
                        'current': current_step,
                        'total': total_steps,
                        'status': '正在合并视频片段'
                    }
                })
                
            final_video = mpy.concatenate_videoclips(processed_clips)
            
            # 保存最终视频
            final_output = os.path.join(
                self.config.OUTPUT_DIR,
                'final',
                f'final_{int(time.time())}.mp4'
            )
            
            final_video.write_videofile(
                final_output,
                codec='libx264',
                audio_codec='aac',
                fps=24
            )
            
            # 清理临时文件
            for clip in processed_clips:
                clip.close()
            final_video.close()
            
            return final_output
            
        except Exception as e:
            raise VideoProcessingError(
                message=f"视频处理失败: {str(e)}",
                error_code="VIDEO_PROCESSING_ERROR"
            )
            
    async def generate_audio(self, text: str, output_path: str, voice_settings: Dict) -> str:
        """使用 Edge TTS 生成语音"""
        try:
            communicate = edge_tts.Communicate(
                text=text,
                voice=voice_settings['speaker'],
                rate=f"+{int((voice_settings['speed']-1)*100)}%",
                volume=f"+{int(voice_settings['volume']-100)}%"
            )
            
            await communicate.save(output_path)
            return output_path
            
        except Exception as e:
            raise VideoProcessingError(
                message=f"语音生成失败: {str(e)}",
                error_code="VOICE_GENERATION_ERROR"
            )
            
    def create_subtitle(self, text: str, video_size: tuple, subtitle_settings: Dict) -> mpy.TextClip:
        """创建字幕"""
        try:
            # 计算字幕位置
            w, h = video_size
            positions = {
                'top': ('center', 50),
                'middle': ('center', 'center'),
                'bottom': ('center', h - 50)
            }
            
            text_clip = mpy.TextClip(
                text,
                fontsize=subtitle_settings['size'],
                font=subtitle_settings['font'],
                color=subtitle_settings['color'],
                stroke_color=subtitle_settings['strokeColor'],
                stroke_width=subtitle_settings['strokeWidth']
            )
            
            text_clip = text_clip.set_position(positions[subtitle_settings['position']])
            return text_clip
            
        except Exception as e:
            raise VideoProcessingError(
                message=f"字幕创建失败: {str(e)}",
                error_code="SUBTITLE_CREATION_ERROR"
            )
            
    def apply_transition(self, clip: mpy.VideoFileClip, transition_settings: Dict) -> mpy.VideoFileClip:
        """应用转场效果"""
        duration = transition_settings['duration']
        effect = transition_settings['effect']
        
        try:
            if effect == 'fade':
                return clip.fadein(duration)
            elif effect == 'slide':
                return clip.set_start(duration).crossfadein(duration)
            elif effect == 'zoom':
                return clip.fx(mpy.vfx.zoom, 1.5, duration)
            return clip
            
        except Exception as e:
            raise VideoProcessingError(
                message=f"转场效果应用失败: {str(e)}",
                error_code="TRANSITION_ERROR"
            )
            
    def apply_filters(self, clip: mpy.VideoFileClip, filter_settings: Dict) -> mpy.VideoFileClip:
        """应用视频滤镜效果"""
        try:
            # 应用基本调整
            if filter_settings['brightness'] != 1.0:
                clip = clip.fx(mpy.vfx.colorx, filter_settings['brightness'])
            
            if filter_settings['contrast'] != 1.0:
                clip = clip.fx(mpy.vfx.gamma_corr, filter_settings['contrast'])
            
            if filter_settings['saturation'] != 1.0:
                clip = clip.fx(mpy.vfx.colorx, filter_settings['saturation'])
            
            if filter_settings['hue'] != 0:
                clip = clip.fx(mpy.vfx.hue, filter_settings['hue'])
            
            return clip
            
        except Exception as e:
            raise VideoProcessingError(
                message=f"滤镜应用失败: {str(e)}",
                error_code="FILTER_ERROR"
            )
            
    def resize_video(self, clip: mpy.VideoFileClip, size_setting: str) -> mpy.VideoFileClip:
        """调整视频尺寸"""
        try:
            if size_setting == 'original':
                return clip
                
            sizes = {
                '1080p': (1920, 1080),
                '720p': (1280, 720),
                '480p': (854, 480)
            }
            
            if size_setting in sizes:
                width, height = sizes[size_setting]
                return clip.resize(width=width, height=height)
            
            return clip
            
        except Exception as e:
            raise VideoProcessingError(
                message=f"视频尺寸调整失败: {str(e)}",
                error_code="RESIZE_ERROR"
            )
            
    def crop_video(self, clip: mpy.VideoFileClip, ratio: str) -> mpy.VideoFileClip:
        """裁剪视频"""
        try:
            if ratio == 'original':
                return clip
                
            ratios = {
                '16:9': 16/9,
                '9:16': 9/16,
                '1:1': 1,
                '4:3': 4/3
            }
            
            if ratio in ratios:
                target_ratio = ratios[ratio]
                current_ratio = clip.w / clip.h
                
                if current_ratio > target_ratio:
                    # 裁剪宽度
                    new_w = int(clip.h * target_ratio)
                    x_center = clip.w / 2
                    x1 = int(x_center - new_w / 2)
                    return clip.crop(x1=x1, width=new_w)
                else:
                    # 裁剪高度
                    new_h = int(clip.w / target_ratio)
                    y_center = clip.h / 2
                    y1 = int(y_center - new_h / 2)
                    return clip.crop(y1=y1, height=new_h)
                    
            return clip
            
        except Exception as e:
            raise VideoProcessingError(
                message=f"视频裁剪失败: {str(e)}",
                error_code="CROP_ERROR"
            )

    def get_file(self, filename: str, file_type: str = 'output', subfolder: str = '') -> str:
        """获取文件路径"""
        try:
            if not filename:
                raise ValueError('Filename is required')
                
            base_path = os.path.join(self.config.OUTPUT_DIR, file_type)
            if subfolder:
                base_path = os.path.join(base_path, subfolder)
                
            file_path = os.path.join(base_path, filename)
            
            # 检查文件是否存在且在允许的目录内
            if not os.path.exists(file_path) or not os.path.abspath(file_path).startswith(os.path.abspath(self.config.OUTPUT_DIR)):
                raise FileNotFoundError('File not found')
                
            return file_path
            
        except Exception as e:
            raise Exception(f"Error getting file: {str(e)}") 