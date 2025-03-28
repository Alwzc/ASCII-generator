class VideoSettings {
    constructor() {
        this.settings = {
            subtitle: {
                font: 'SimHei',
                size: 24,
                color: '#ffffff',
                strokeColor: '#000000',
                strokeWidth: 2,
                position: 'bottom'
            },
            voice: {
                speaker: 'zh-CN-XiaoxiaoNeural',
                speed: 1.0,
                volume: 100
            },
            transition: {
                effect: 'none',
                duration: 1.0
            },
            filter: {
                brightness: 1.0,
                contrast: 1.0,
                saturation: 1.0,
                hue: 0,
                preset: 'none'
            },
            clip: {
                speed: 1.0,
                size: 'original',
                cropRatio: 'original'
            }
        };
        
        this.setupEventListeners();
        this.loadSettings();
    }
    
    setupEventListeners() {
        // 字幕设置
        document.getElementById('subtitleFont').addEventListener('change', e => 
            this.updateSetting('subtitle', 'font', e.target.value));
            
        document.getElementById('subtitleSize').addEventListener('input', e => {
            this.updateSetting('subtitle', 'size', parseInt(e.target.value));
            document.getElementById('subtitleSizeValue').textContent = `${e.target.value}px`;
        });
        
        document.getElementById('subtitleColor').addEventListener('change', e =>
            this.updateSetting('subtitle', 'color', e.target.value));
            
        document.getElementById('subtitleStrokeColor').addEventListener('change', e =>
            this.updateSetting('subtitle', 'strokeColor', e.target.value));
            
        document.getElementById('subtitleStrokeWidth').addEventListener('input', e => {
            this.updateSetting('subtitle', 'strokeWidth', parseInt(e.target.value));
            document.getElementById('strokeWidthValue').textContent = `${e.target.value}px`;
        });
        
        document.querySelectorAll('input[name="subtitlePosition"]').forEach(input => {
            input.addEventListener('change', e => 
                this.updateSetting('subtitle', 'position', e.target.value));
        });
        
        // 配音设置
        document.getElementById('voiceSelect').addEventListener('change', e =>
            this.updateSetting('voice', 'speaker', e.target.value));
            
        document.getElementById('voiceSpeed').addEventListener('input', e => {
            this.updateSetting('voice', 'speed', parseFloat(e.target.value));
            document.getElementById('speedValue').textContent = `${e.target.value}x`;
        });
        
        document.getElementById('voiceVolume').addEventListener('input', e => {
            this.updateSetting('voice', 'volume', parseInt(e.target.value));
            document.getElementById('volumeValue').textContent = `${e.target.value}%`;
        });
        
        // 转场设置
        document.getElementById('transitionEffect').addEventListener('change', e =>
            this.updateSetting('transition', 'effect', e.target.value));
            
        document.getElementById('transitionDuration').addEventListener('input', e => {
            this.updateSetting('transition', 'duration', parseFloat(e.target.value));
            document.getElementById('transitionDurationValue').textContent = `${e.target.value}s`;
        });
        
        // 测试配音
        document.getElementById('testVoice').addEventListener('click', () => this.testVoice());
        
        // 保存设置
        document.getElementById('saveSettings').addEventListener('click', () => this.saveSettings());
        
        // 滤镜设置
        ['brightness', 'contrast', 'saturation'].forEach(param => {
            document.getElementById(param).addEventListener('input', e => {
                this.updateSetting('filter', param, parseFloat(e.target.value));
                document.getElementById(`${param}Value`).textContent = e.target.value;
            });
        });
        
        document.getElementById('hue').addEventListener('input', e => {
            this.updateSetting('filter', 'hue', parseInt(e.target.value));
            document.getElementById('hueValue').textContent = `${e.target.value}°`;
        });
        
        document.getElementById('filterPreset').addEventListener('change', e => {
            this.updateSetting('filter', 'preset', e.target.value);
            if (e.target.value !== 'none') {
                this.applyFilterPreset(e.target.value);
            }
        });
        
        // 剪辑设置
        document.getElementById('playbackSpeed').addEventListener('input', e => {
            this.updateSetting('clip', 'speed', parseFloat(e.target.value));
            document.getElementById('speedValue').textContent = `${e.target.value}x`;
        });
        
        document.getElementById('videoSize').addEventListener('change', e =>
            this.updateSetting('clip', 'size', e.target.value));
            
        document.getElementById('cropRatio').addEventListener('change', e =>
            this.updateSetting('clip', 'cropRatio', e.target.value));
    }
    
    updateSetting(category, key, value) {
        this.settings[category][key] = value;
    }
    
    async testVoice() {
        try {
            const response = await fetch('/test_voice', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(this.settings.voice)
            });
            
            const result = await response.json();
            
            if (result.error) {
                throw new Error(result.error);
            }
            
            // 播放测试音频
            const audio = new Audio(result.audioUrl);
            audio.play();
            
        } catch (error) {
            handleError(error);
        }
    }
    
    saveSettings() {
        localStorage.setItem('videoSettings', JSON.stringify(this.settings));
        const modal = bootstrap.Modal.getInstance(document.getElementById('settingsModal'));
        modal.hide();
    }
    
    loadSettings() {
        const saved = localStorage.getItem('videoSettings');
        if (saved) {
            this.settings = JSON.parse(saved);
            this.updateUI();
        }
    }
    
    updateUI() {
        // 更新所有设置控件的值
        const s = this.settings;
        
        // 字幕设置
        document.getElementById('subtitleFont').value = s.subtitle.font;
        document.getElementById('subtitleSize').value = s.subtitle.size;
        document.getElementById('subtitleSizeValue').textContent = `${s.subtitle.size}px`;
        document.getElementById('subtitleColor').value = s.subtitle.color;
        document.getElementById('subtitleStrokeColor').value = s.subtitle.strokeColor;
        document.getElementById('subtitleStrokeWidth').value = s.subtitle.strokeWidth;
        document.getElementById('strokeWidthValue').textContent = `${s.subtitle.strokeWidth}px`;
        document.querySelector(`input[name="subtitlePosition"][value="${s.subtitle.position}"]`).checked = true;
        
        // 配音设置
        document.getElementById('voiceSelect').value = s.voice.speaker;
        document.getElementById('voiceSpeed').value = s.voice.speed;
        document.getElementById('speedValue').textContent = `${s.voice.speed}x`;
        document.getElementById('voiceVolume').value = s.voice.volume;
        document.getElementById('volumeValue').textContent = `${s.voice.volume}%`;
        
        // 转场设置
        document.getElementById('transitionEffect').value = s.transition.effect;
        document.getElementById('transitionDuration').value = s.transition.duration;
        document.getElementById('transitionDurationValue').textContent = `${s.transition.duration}s`;
    }
    
    getSettings() {
        return this.settings;
    }
    
    applyFilterPreset(preset) {
        const presets = {
            warm: {
                brightness: 1.1,
                contrast: 1.1,
                saturation: 1.2,
                hue: 5
            },
            cold: {
                brightness: 1.0,
                contrast: 1.1,
                saturation: 0.9,
                hue: -5
            },
            vintage: {
                brightness: 0.9,
                contrast: 1.2,
                saturation: 0.7,
                hue: 0
            },
            dramatic: {
                brightness: 1.1,
                contrast: 1.3,
                saturation: 1.1,
                hue: 0
            }
        };
        
        if (preset in presets) {
            const settings = presets[preset];
            Object.entries(settings).forEach(([key, value]) => {
                this.updateSetting('filter', key, value);
                const element = document.getElementById(key);
                if (element) {
                    element.value = value;
                    document.getElementById(`${key}Value`).textContent = 
                        key === 'hue' ? `${value}°` : value;
                }
            });
        }
    }
}

// 初始化设置
const videoSettings = new VideoSettings(); 