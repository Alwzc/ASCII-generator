// 全局变量，用于跟踪测试模式状态
let testModeEnabled = false;

// 添加任务缓存管理
const TaskManager = {
    tasks: new Map(),
    
    // 添加任务
    addTask(promptId, taskInfo) {
        console.log('Adding task to cache:', promptId, taskInfo);
        this.tasks.set(promptId, {
            ...taskInfo,
            lastChecked: Date.now()
        });
        this.saveTasks();
        console.log('Current tasks after add:', Array.from(this.tasks.entries()));
    },
    
    // 更新任务状态
    updateTask(promptId, status) {
        console.log('Updating task in cache:', promptId, status);
        const currentTask = this.tasks.get(promptId);
        console.log('Current task before update:', currentTask);
        
        this.tasks.set(promptId, {
            ...this.tasks.get(promptId),
            ...status,
            lastChecked: Date.now()
        });
        this.saveTasks();
        console.log('Current tasks after update:', Array.from(this.tasks.entries()));
    },
    
    // 获取所有任务
    getAllTasks() {
        return Array.from(this.tasks.entries()).map(([promptId, task]) => ({
            promptId,
            ...task
        }));
    },
    
    // 保存任务到localStorage
    saveTasks() {
        const tasksToSave = Array.from(this.tasks.entries());
        console.log('Saving tasks to localStorage:', tasksToSave);
        localStorage.setItem('videoTasks', JSON.stringify(tasksToSave));
    },
    
    // 从localStorage加载任务
    loadTasks() {
        try {
            const saved = localStorage.getItem('videoTasks');
            console.log('Loading tasks from localStorage:', saved);
            if (saved) {
                this.tasks = new Map(JSON.parse(saved));
                console.log('Loaded tasks:', Array.from(this.tasks.entries()));
            }
        } catch (e) {
            console.error('Failed to load tasks:', e);
        }
    },
    
    // 检查任务状态
    async checkTaskStatus(promptId) {
        try {
            // 从后端Redis获取状态
            const response = await fetch(`/api/task-status/${promptId}`);
            const status = await response.json();
            
            // 更新UI显示
            updateTaskUI(promptId, status);
            
            return status;
        } catch (e) {
            console.error(`Failed to check status for task ${promptId}:`, e);
            return { status: 'error', error: e.message };
        }
    },
    
    // 添加清理过期任务的方法
    cleanupTasks() {
        const now = Date.now();
        const maxAge = 24 * 60 * 60 * 1000; // 24小时
        
        this.tasks.forEach((task, promptId) => {
            if (now - task.lastSeen > maxAge) {
                this.tasks.delete(promptId);
            }
        });
        
        this.saveTasks();
    },
    
    // 启动轮询
    startPolling() {
        setInterval(() => {
            // 获取所有需要监控的任务ID
            const taskElements = document.querySelectorAll('[data-task-id]');
            taskElements.forEach(element => {
                const promptId = element.dataset.taskId;
                this.checkTaskStatus(promptId);
            });
        }, 5000);
    },
    
    // 任务完成的回调
    onTaskCompleted(promptId, status) {
        // 更新UI显示
        updateTaskUI(promptId, status);
    },
    
    // 任务错误的回调
    onTaskError(promptId, status) {
        // 更新UI显示错误状态
        updateTaskUI(promptId, status);
    }
};

// 当点击"使用测试提示词"按钮时
document.getElementById('useTestPrompts').addEventListener('click', function(e) {
    e.preventDefault();
    
    // 检查必填字段
    const model = document.getElementById('model').value;
    if (!model) {
        alert('请选择模型');
        return;
    }
    
    // 显示加载状态
    this.disabled = true;
    this.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 加载中...';
    
    // 获取测试提示词
    fetch('/api/test-prompts')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 显示提示词容器
                document.getElementById('promptsContainer').style.display = 'block';
                
                // 清空并填充提示词列表
                const promptsList = document.getElementById('promptsList');
                promptsList.innerHTML = '';
                
                data.prompts.forEach((prompt, index) => {
                    const promptItem = document.createElement('div');
                    promptItem.className = 'list-group-item';
                    promptItem.innerHTML = `
                        <div class="d-flex justify-content-between align-items-start">
                            <div class="me-auto">
                                <div class="fw-bold">片段 ${index + 1}</div>
                                <p class="mb-1 prompt-text">${prompt}</p>
                            </div>
                            <button class="btn btn-sm btn-outline-secondary edit-prompt" data-index="${index}">
                                <i class="bi bi-pencil"></i>
                            </button>
                        </div>
                    `;
                    promptsList.appendChild(promptItem);
                });
                
                // 添加编辑提示词的事件监听器
                document.querySelectorAll('.edit-prompt').forEach(button => {
                    button.addEventListener('click', function() {
                        const index = this.getAttribute('data-index');
                        const promptText = this.closest('.list-group-item').querySelector('.prompt-text').textContent;
                        editPrompt(index, promptText);
                    });
                });
                
                // 重置按钮状态
                document.getElementById('useTestPrompts').disabled = false;
                document.getElementById('useTestPrompts').textContent = '使用测试提示词';
                
                // 滚动到提示词列表
                document.getElementById('promptsContainer').scrollIntoView({ behavior: 'smooth' });
            } else {
                alert('获取测试提示词失败: ' + (data.error || '未知错误'));
                // 重置按钮状态
                document.getElementById('useTestPrompts').disabled = false;
                document.getElementById('useTestPrompts').textContent = '使用测试提示词';
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('获取测试提示词失败: ' + error.message);
            // 重置按钮状态
            document.getElementById('useTestPrompts').disabled = false;
            document.getElementById('useTestPrompts').textContent = '使用测试提示词';
        });
});

// 测试模式切换
document.getElementById('testModeToggle').addEventListener('click', function() {
    testModeEnabled = !testModeEnabled;
    
    // 更新按钮显示
    if (testModeEnabled) {
        document.querySelector('.test-mode-off').style.display = 'none';
        document.querySelector('.test-mode-on').style.display = 'inline';
        this.classList.remove('btn-outline-warning');
        this.classList.add('btn-warning');
    } else {
        document.querySelector('.test-mode-off').style.display = 'inline';
        document.querySelector('.test-mode-on').style.display = 'none';
        this.classList.remove('btn-warning');
        this.classList.add('btn-outline-warning');
    }
});

// 修改生成视频的函数，添加测试模式支持
document.getElementById('generateVideos').addEventListener('click', function() {
    // 获取所有提示词
    const promptItems = document.querySelectorAll('#promptsList .list-group-item');
    const prompts = Array.from(promptItems).map(item => 
        item.querySelector('.prompt-text').textContent
    );
    
    if (prompts.length === 0) {
        alert('请先生成提示词');
        return;
    }
    
    const model = document.getElementById('model').value;
    if (!model) {
        alert('请选择模型');
        return;
    }
    
    // 显示加载状态
    this.disabled = true;
    this.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 生成中...';
    
    // 批量生成视频
    fetch('/api/generate-videos', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            prompts: prompts,
            model: model,
            test_mode: testModeEnabled  // 添加测试模式标志
        }),
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // 关闭模态框
            const modal = bootstrap.Modal.getInstance(document.getElementById('videoGeneratorModal'));
            modal.hide();
            
            // 将新任务添加到TaskManager缓存
            if (Array.isArray(data.tasks)) {
                data.tasks.forEach(task => {
                    TaskManager.tasks.set(task.prompt_id, {
                        prompt_id: task.prompt_id,
                        status: 'pending',
                        message: '等待处理',
                        prompt: task.prompt,
                        model: model,
                        created_at: Date.now(),
                        lastSeen: Date.now()
                    });
                });
                TaskManager.saveTasks();
            }
            
            // 刷新任务列表
            refreshTasksUI();
            
            // 显示成功消息
            alert('视频生成任务已提交，请在任务监控墙查看进度');
        } else {
            alert('提交视频生成任务失败: ' + (data.error || '未知错误'));
        }
        
        // 重置按钮状态
        document.getElementById('generateVideos').disabled = false;
        document.getElementById('generateVideos').textContent = '开始生成视频';
    })
    .catch(error => {
        console.error('Error:', error);
        alert('提交视频生成任务失败: ' + error.message);
        
        // 重置按钮状态
        document.getElementById('generateVideos').disabled = false;
        document.getElementById('generateVideos').textContent = '开始生成视频';
    });
});

// 添加测试连接功能
document.getElementById('testConnectionBtn').addEventListener('click', function() {
    this.disabled = true;
    this.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 测试中...';
    
    fetch('/api/test-connection')
        .then(response => response.json())
        .then(data => {
            if (data.status === 'connected') {
                alert('连接成功: ' + data.message);
            } else {
                alert('连接失败: ' + data.message);
                console.error('连接详情:', data);
            }
        })
        .catch(error => {
            alert('测试连接时发生错误: ' + error.message);
            console.error('Error:', error);
        })
        .finally(() => {
            this.disabled = false;
            this.textContent = '测试连接';
        });
});

// 页面加载时初始化任务管理器
document.addEventListener('DOMContentLoaded', () => {
    TaskManager.loadTasks();
    TaskManager.startPolling();
    refreshTasksUI();
});

// 更新任务UI的函数
function updateTaskUI(promptId, status) {
    const taskElement = document.querySelector(`[data-task-id="${promptId}"]`);
    if (taskElement) {
        // 根据状态更新UI显示
        if (status.status === 'completed') {
            taskElement.querySelector('.status').textContent = '已完成';
            taskElement.querySelector('.progress-bar').style.width = '100%';
            // 显示预览和下载链接
            if (status.preview_url) {
                const actionsDiv = taskElement.querySelector('.actions');
                // 清除现有的链接
                actionsDiv.innerHTML = '';
                // 添加预览链接
                const previewLink = document.createElement('a');
                previewLink.href = status.preview_url;
                previewLink.textContent = '预览';
                previewLink.className = 'btn btn-sm btn-primary me-2';
                previewLink.target = '_blank';
                actionsDiv.appendChild(previewLink);
                // 添加下载链接
                const downloadLink = document.createElement('a');
                downloadLink.href = status.preview_url;
                downloadLink.textContent = '下载';
                downloadLink.className = 'btn btn-sm btn-success';
                downloadLink.download = '';
                actionsDiv.appendChild(downloadLink);
            }
        } else if (status.status === 'error') {
            taskElement.querySelector('.status').textContent = '错误';
            taskElement.querySelector('.status').className = 'status text-danger';
            taskElement.querySelector('.error-message').textContent = status.error || '未知错误';
        } else if (status.status === 'processing') {
            taskElement.querySelector('.status').textContent = '处理中';
            taskElement.querySelector('.progress-bar').style.width = '60%';
        } else if (status.status === 'pending') {
            taskElement.querySelector('.status').textContent = status.message || '等待中';
            taskElement.querySelector('.progress-bar').style.width = '30%';
        } else {
            taskElement.querySelector('.status').textContent = status.message || '未知状态';
            taskElement.querySelector('.progress-bar').style.width = '0%';
        }
    }
} 