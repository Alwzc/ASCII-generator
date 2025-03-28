// 任务管理器 - 处理本地存储和任务显示
class TaskManager {
    constructor() {
        this.monitorWall = document.getElementById('taskMonitorWall');
        this.noTasksMessage = document.getElementById('noTasksMessage');
        this.tasks = []; // 只存储当前任务
    }
    
    // 添加新任务
    addTask(taskData) {
        // 确保有正确的创建时间
        if (!taskData.createdAt) {
            taskData.createdAt = Date.now() / 1000; // 使用当前时间戳（秒）
        }
        
        this.tasks.push(taskData);
        this.renderTasks();
        return taskData.id;
    }
    
    // 从 Redis 更新任务状态
    updateTasksFromRedis(redisData) {
        if (!redisData || typeof redisData !== 'object') return;
        
        console.log('Updating tasks from Redis:', redisData);
        
        // 创建新的任务列表
        const newTasks = [];
        
        // 处理 Redis 中的所有任务
        Object.entries(redisData).forEach(([taskId, taskData]) => {
            // 准备任务内容
            let content = taskData.content;
            
            // 如果没有content但有prompt，使用prompt
            if (!content && taskData.prompt) {
                content = taskData.prompt;
            }
            
            // 创建任务对象
            const task = {
                id: taskId,
                prompt_id: taskId,
                content: content || '未知任务',
                status: taskData.status,
                message: this.getChineseMessage(taskData.message) || this.getStatusText(taskData.status),
                progress: taskData.progress || 0,
                videoUrl: taskData.video_url || taskData.preview_url,
                errorMessage: taskData.error || (taskData.status === 'error' ? taskData.message : null),
                createdAt: taskData.created_at ? taskData.created_at : Date.now() / 1000,
                prompt: taskData.prompt,
                model: taskData.model,
                queue_position: taskData.queue_position,
                waiting_time: taskData.waiting_time,
                processing_time: taskData.processing_time,
                last_updated: taskData.last_updated,
                type: taskData.type || 'video',
                output_path: taskData.output_path,
                batch_id: taskData.batch_id,
                segment_index: taskData.segment_index,
                total_segments: taskData.total_segments
            };
            
            newTasks.push(task);
        });
        
        // 按创建时间排序，最新的在前面
        newTasks.sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));
        
        // 更新任务列表
        this.tasks = newTasks;
        
        console.log('Updated tasks:', this.tasks);
        this.renderTasks();
    }
    
    // 渲染所有任务
    renderTasks() {
        if (!this.monitorWall) return;
        
        // 清空现有内容
        this.monitorWall.innerHTML = '';
        
        if (this.tasks.length === 0) {
            this.noTasksMessage.style.display = 'block';
            return;
        }
        
        this.noTasksMessage.style.display = 'none';
        
        // 按创建时间排序，最新的在前面
        this.tasks.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
        
        // 渲染每个任务
        this.tasks.forEach(task => {
            const taskCard = this.createTaskCard(task);
            this.monitorWall.appendChild(taskCard);
        });
    }
    
    // 创建任务卡片
    createTaskCard(task) {
        const col = document.createElement('div');
        col.className = 'col-md-4 col-lg-3 mb-4';
        
        // 根据任务状态设置不同的卡片样式
        let statusClass = '';
        let statusIcon = '';
        switch (task.status) {
            case 'processing':
                statusClass = 'border-primary bg-primary bg-opacity-10';
                statusIcon = '<i class="bi bi-gear-fill me-1 text-primary"></i>';
                break;
            case 'completed':
                statusClass = 'border-success bg-success bg-opacity-10';
                statusIcon = '<i class="bi bi-check-circle-fill me-1 text-success"></i>';
                break;
            case 'error':
                statusClass = 'border-danger bg-danger bg-opacity-10';
                statusIcon = '<i class="bi bi-exclamation-triangle-fill me-1 text-danger"></i>';
                break;
            default:
                statusClass = 'border-warning bg-warning bg-opacity-10';
                statusIcon = '<i class="bi bi-hourglass-split me-1 text-warning"></i>';
        }
        
        // 准备状态详情信息
        let statusDetails = '';
        if (task.status === 'pending' && task.queue_position) {
            statusDetails = `<span class="badge bg-warning text-dark rounded-pill">队列位置: ${task.queue_position}</span>`;
            if (task.waiting_time) {
                const waitingMins = Math.floor(task.waiting_time / 60);
                const waitingSecs = Math.floor(task.waiting_time % 60);
                statusDetails += ` <span class="badge bg-info text-dark rounded-pill">等待: ${waitingMins}分${waitingSecs}秒</span>`;
            }
        } else if (task.status === 'processing' && task.processing_time) {
            const processingMins = Math.floor(task.processing_time / 60);
            const processingSecs = Math.floor(task.processing_time % 60);
            statusDetails = `<span class="badge bg-info text-dark rounded-pill">处理: ${processingMins}分${processingSecs}秒</span>`;
        }
        
        // 检查是否有预览内容
        let previewContent = '';
        let previewButton = '';
        if (task.status === 'completed') {
            // 优先使用output_path，其次使用preview_url
            const previewSource = task.output_path || task.preview_url || task.videoUrl;
            if (previewSource) {
                // 处理路径，确保它是完整的URL
                let fullOutputPath = previewSource;
                
                // 如果是相对路径，构建正确的预览URL
                if (previewSource && !previewSource.startsWith('http') && !previewSource.startsWith('/')) {
                    // 直接使用文件名作为参数
                    fullOutputPath = `/view?filename=${encodeURIComponent(previewSource)}&type=output&preview=true`;
                }
                
                // 准备预览按钮
                previewButton = `
                    <button class="btn btn-sm btn-outline-primary rounded-circle preview-output-btn" 
                            title="${task.type === 'image' ? '查看大图' : '全屏查看'}"
                            data-output="${fullOutputPath}"
                            data-type="${task.type || 'video'}">
                        <i class="bi bi-arrows-fullscreen"></i>
                    </button>`;
                
                // 准备预览内容
                if (task.type === 'image') {
                    previewContent = `
                        <div class="mt-2 text-center">
                            <img src="${fullOutputPath}" class="img-fluid rounded" alt="生成的图片" style="max-height: 180px;">
                        </div>`;
                } else {
                    previewContent = `
                        <div class="mt-2 text-center">
                            <video controls muted loop class="img-fluid rounded" style="max-height: 180px;">
                                <source src="${fullOutputPath}" type="video/mp4">
                                您的浏览器不支持视频标签。
                            </video>
                        </div>`;
                }
            }
        }
        
        // 提取任务内容
        let taskContent = task.content;
        
        // 如果没有content但有prompt，使用完整的prompt
        if (!taskContent && task.prompt) {
            taskContent = task.prompt;
        }
        
        // 如果都没有，使用默认值
        if (!taskContent) {
            taskContent = '未命名任务';
        }
        
        // 在卡片中添加批次信息显示
        let batchInfo = '';
        if (task.batch_id && task.segment_index !== undefined && task.total_segments) {
            batchInfo = `
                <div class="mt-1">
                    <span class="badge bg-info text-dark rounded-pill">
                        <i class="bi bi-collection me-1"></i>
                        片段 ${task.segment_index + 1}/${task.total_segments}
                    </span>
                </div>
            `;
        }
        
        col.innerHTML = `
            <div class="card ${statusClass} h-100 shadow-sm">
                <div class="card-header d-flex justify-content-between align-items-center py-2">
                    <span class="badge ${this.getStatusBadgeClass(task.status)} rounded-pill">
                        ${statusIcon}${task.message || this.getStatusText(task.status)}
                    </span>
                    <div>
                        ${task.status === 'completed' ? previewButton : ''}
                        <button class="btn btn-sm btn-outline-danger rounded-circle delete-btn ms-1" title="删除任务" data-task-id="${task.id}">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </div>
                <div class="card-body p-2">
                    <div class="card-title small fw-bold mb-1" style="font-size: 0.85rem; min-height:3.4em; display: -webkit-box; -webkit-line-clamp: ${task.status === 'completed' ? '3' : '12'}; -webkit-box-orient: vertical; overflow: hidden; line-height: 1.2em; max-height: ${task.status === 'completed' ? '4.4em' : '14em'};" title="${task.prompt || taskContent}">
                        ${taskContent}
                    </div>
                    <div class="card-text small mb-1">
                        ${task.model ? `<span class="badge bg-secondary rounded-pill mb-1">${task.model}</span>` : ''}
                        ${batchInfo}
                        ${statusDetails}
                        ${task.status === 'processing' ? 
                            `<div class="progress mt-2" style="height: 4px">
                                <div class="progress-bar progress-bar-striped progress-bar-animated bg-primary" 
                                     role="progressbar" style="width: ${task.progress || 50}%"></div>
                            </div>` : ''}
                        ${task.status === 'error' ? 
                            `<div class="alert alert-danger py-1 px-2 small mt-1 rounded-3">${task.errorMessage || '处理失败'}</div>` : ''}
                    </div>
                    ${previewContent}
                    <div class="d-flex justify-content-between align-items-center mt-1">
                        <small class="text-muted"><i class="bi bi-clock me-1"></i>${this.formatDate(task.createdAt)}</small>
                        ${this.calculateTotalTime(task)}
                    </div>
                </div>
            </div>
        `;
        
        // 添加事件监听器
        const previewOutputBtn = col.querySelector('.preview-output-btn');
        if (previewOutputBtn) {
            previewOutputBtn.addEventListener('click', () => {
                const outputPath = previewOutputBtn.getAttribute('data-output');
                const outputType = previewOutputBtn.getAttribute('data-type') || 'video';
                this.previewOutput(outputPath, outputType);
            });
        }
        
        const deleteBtn = col.querySelector('.delete-btn');
        if (deleteBtn) {
            deleteBtn.addEventListener('click', () => this.confirmDeleteTask(task.id));
        }
        
        return col;
    }
    
    // 获取状态对应的徽章样式
    getStatusBadgeClass(status) {
        switch (status) {
            case 'pending':
                return 'bg-warning text-dark';
            case 'processing':
                return 'bg-primary';
            case 'completed':
                return 'bg-success';
            case 'error':
                return 'bg-danger';
            default:
                return 'bg-secondary';
        }
    }
    
    // 获取状态文本
    getStatusText(status) {
        switch (status) {
            case 'pending':
                return '等待中';
            case 'processing':
                return '处理中';
            case 'completed':
                return '已完成';
            case 'error':
                return '出错了';
            default:
                return '未知状态';
        }
    }
    
    // 格式化日期
    formatDate(dateStr) {
        try {
            // 如果是时间戳（数字），转换为毫秒
            let date;
            if (typeof dateStr === 'number') {
                date = new Date(dateStr * 1000); // 转换秒为毫秒
            } else {
                date = new Date(dateStr);
            }

            // 检查日期是否有效
            if (isNaN(date.getTime())) {
                console.error('Invalid date:', dateStr);
                return '时间未知';
            }

            const now = new Date();
            
            // 如果是今天的日期，显示"今天 HH:MM"
            if (date.toDateString() === now.toDateString()) {
                return `今天 ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
            }
            
            // 如果是昨天，显示"昨天 HH:MM"
            const yesterday = new Date(now);
            yesterday.setDate(now.getDate() - 1);
            if (date.toDateString() === yesterday.toDateString()) {
                return `昨天 ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
            }
            
            // 其他日期显示"MM月DD日 HH:MM"
            return `${date.getMonth() + 1}月${date.getDate()}日 ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
        } catch (error) {
            console.error('Date formatting error:', error);
            return '时间未知';
        }
    }
    
    // 预览任务
    previewTask(taskId) {
        // 查找任务
        let task = this.tasks.find(t => t.id === taskId);
        
        if (!task || !task.videoUrl) {
            alert('无法预览，视频不存在');
            return;
        }
        
        // 创建预览模态框
        const previewModal = document.createElement('div');
        previewModal.className = 'modal fade';
        previewModal.id = 'videoPreviewModal';
        previewModal.setAttribute('tabindex', '-1');
        previewModal.setAttribute('aria-hidden', 'true');
        
        previewModal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">视频预览</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        <video controls class="w-100" autoplay>
                            <source src="${task.videoUrl}" type="video/webm">
                            您的浏览器不支持视频标签。
                        </video>
                        <div class="mt-3">
                            <h6>提示词:</h6>
                            <p class="small">${task.prompt || '无提示词'}</p>
                        </div>
                    </div>
                    <div class="modal-footer">
                        <a href="${task.videoUrl}" class="btn btn-primary" download>
                            <i class="bi bi-download me-1"></i>下载视频
                        </a>
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(previewModal);
        
        // 显示模态框
        const modal = new bootstrap.Modal(previewModal);
        modal.show();
        
        // 模态框关闭后移除DOM
        previewModal.addEventListener('hidden.bs.modal', function () {
            document.body.removeChild(previewModal);
        });
    }
    
    // 确认删除任务
    confirmDeleteTask(taskId) {
        // 创建确认对话框
        const modal = document.createElement('div');
        modal.className = 'modal fade';
        modal.id = 'deleteConfirmModal';
        modal.setAttribute('tabindex', '-1');
        modal.setAttribute('aria-hidden', 'true');
        
        modal.innerHTML = `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content">
                    <div class="modal-header bg-danger text-white">
                        <h5 class="modal-title">确认删除</h5>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="关闭"></button>
                    </div>
                    <div class="modal-body">
                        <p>您确定要删除这个任务吗？此操作无法撤销。</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
                        <button type="button" class="btn btn-danger confirm-delete-btn">
                            <i class="bi bi-trash me-1"></i>确认删除
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // 显示模态框
        const modalInstance = new bootstrap.Modal(modal);
        modalInstance.show();
        
        // 确认删除按钮事件
        const confirmBtn = modal.querySelector('.confirm-delete-btn');
        confirmBtn.addEventListener('click', () => {
            // 调用后端删除接口
            fetch(`/api/task/${taskId}`, {
                method: 'DELETE'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // 从本地列表中移除
                    this.tasks = this.tasks.filter(t => t.id !== taskId);
                    this.renderTasks();
                    
                    // 显示成功提示
                    this.showToast('删除成功', '任务已成功删除', 'success');
                } else {
                    throw new Error(data.error || '删除失败');
                }
            })
            .catch(error => {
                console.error('删除任务失败:', error);
                this.showToast('删除失败', error.message, 'error');
            })
            .finally(() => {
                modalInstance.hide();
                // 模态框关闭后移除DOM
                modal.addEventListener('hidden.bs.modal', function () {
                    document.body.removeChild(modal);
                });
            });
        });
        
        // 模态框关闭后移除DOM
        modal.addEventListener('hidden.bs.modal', function () {
            document.body.removeChild(modal);
        });
    }

    // 添加显示提示消息的方法
    showToast(title, message, type = 'info') {
        // 创建toast容器（如果不存在）
        let toastContainer = document.querySelector('.toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
            document.body.appendChild(toastContainer);
        }
        
        // 设置toast类型样式
        let bgClass = 'bg-info';
        let icon = '<i class="bi bi-info-circle me-2"></i>';
        
        switch (type) {
            case 'success':
                bgClass = 'bg-success';
                icon = '<i class="bi bi-check-circle me-2"></i>';
                break;
            case 'error':
                bgClass = 'bg-danger';
                icon = '<i class="bi bi-exclamation-triangle me-2"></i>';
                break;
            case 'warning':
                bgClass = 'bg-warning';
                icon = '<i class="bi bi-exclamation-circle me-2"></i>';
                break;
        }
        
        // 创建toast元素
        const toastEl = document.createElement('div');
        toastEl.className = `toast ${bgClass} text-white`;
        toastEl.setAttribute('role', 'alert');
        toastEl.setAttribute('aria-live', 'assertive');
        toastEl.setAttribute('aria-atomic', 'true');
        
        toastEl.innerHTML = `
            <div class="toast-header ${bgClass} text-white">
                ${icon}
                <strong class="me-auto">${title}</strong>
                <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="关闭"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        `;
        
        // 添加到容器
        toastContainer.appendChild(toastEl);
        
        // 初始化并显示toast
        const toast = new bootstrap.Toast(toastEl, {
            autohide: true,
            delay: 5000
        });
        toast.show();
        
        // Toast关闭后移除DOM
        toastEl.addEventListener('hidden.bs.toast', function() {
            toastContainer.removeChild(toastEl);
        });
    }

    // 修改预览输出方法，根据类型显示不同内容
    previewOutput(outputPath, outputType = 'video') {
        // 处理路径，确保它是完整的URL
        let fullOutputPath = outputPath;
        
        // 如果是相对路径，构建正确的预览URL
        if (outputPath && !outputPath.startsWith('http') && !outputPath.startsWith('/')) {
            // 直接使用文件名作为参数
            fullOutputPath = `/view?filename=${encodeURIComponent(outputPath)}&type=output&preview=true`;
        }
        
        console.log('Preview URL:', fullOutputPath);
        
        // 创建预览模态框
        const previewModal = document.createElement('div');
        previewModal.className = 'modal fade';
        previewModal.id = 'outputPreviewModal';
        previewModal.setAttribute('tabindex', '-1');
        previewModal.setAttribute('aria-hidden', 'true');
        
        // 根据类型准备不同的预览内容
        let previewContent = '';
        if (outputType === 'image') {
            previewContent = `
                <div class="text-center">
                    <img src="${fullOutputPath}" class="img-fluid rounded" alt="生成的图片">
                </div>
            `;
        } else {
            previewContent = `
                <div class="text-center">
                    <video controls class="w-100">
                        <source src="${fullOutputPath}" type="video/mp4">
                        您的浏览器不支持视频标签。
                    </video>
                </div>
            `;
        }
        
        previewModal.innerHTML = `
            <div class="modal-dialog modal-lg">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">${outputType === 'image' ? '图片预览' : '视频预览'}</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        ${previewContent}
                    </div>
                    <div class="modal-footer">
                        <a href="${fullOutputPath}" class="btn btn-primary" download>
                            <i class="bi bi-download me-1"></i>下载${outputType === 'image' ? '图片' : '视频'}
                        </a>
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(previewModal);
        
        // 显示模态框
        const modal = new bootstrap.Modal(previewModal);
        modal.show();
        
        // 模态框关闭后移除DOM
        previewModal.addEventListener('hidden.bs.modal', function () {
            document.body.removeChild(previewModal);
        });
    }

    // 添加英文消息转中文的辅助方法
    getChineseMessage(message) {
        if (!message) return null;
        
        // 英文消息映射到中文
        const messageMap = {
            'Video generation completed': '视频生成完成',
            'Image generation completed': '图片生成完成',
            'Task is processing': '任务处理中',
            'Task completed': '任务已完成',
            'Task completed but no output found': '任务已完成但未找到输出',
            'Task failed in ComfyUI': 'ComfyUI处理失败',
            'Task is still processing': '任务仍在处理中',
            'Could not determine task status': '无法确定任务状态',
            'Task not found in history': '在历史记录中未找到任务',
            'No history data found for this task': '未找到此任务的历史数据'
        };
        
        // 检查是否有匹配的中文消息
        if (messageMap[message]) {
            return messageMap[message];
        }
        
        // 处理队列位置消息
        if (message.startsWith('Waiting in queue')) {
            return message.replace('Waiting in queue, position:', '等待队列中，位置:');
        }
        
        // 如果没有匹配项，返回原始消息
        return message;
    }

    // 计算总用时
    calculateTotalTime(task) {
        if (task.status !== 'completed' && task.status !== 'error') {
            return '';
        }
        
        let totalTime = 0;
        
        // 计算等待时间
        if (task.waiting_time) {
            totalTime += parseInt(task.waiting_time);
        }
        
        // 计算处理时间
        if (task.processing_time) {
            totalTime += parseInt(task.processing_time);
        }
        
        // 如果有创建时间和最后更新时间，计算总时间差
        if (!totalTime && task.createdAt && task.last_updated) {
            const startTime = new Date(task.createdAt).getTime();
            const endTime = new Date(task.last_updated * 1000).getTime();
            totalTime = Math.floor((endTime - startTime) / 1000);
        }
        
        if (totalTime > 0) {
            const mins = Math.floor(totalTime / 60);
            const secs = totalTime % 60;
            return `<small class="text-muted">用时: ${mins}分${secs}秒</small>`;
        }
        
        return '';
    }
}

// 定时从 Redis 获取任务状态
window.updateCurrentTask = async function() {
    console.log('Fetching task status...');
    try {
        const response = await fetch('/api/task-status');
        if (!response.ok) throw new Error('获取任务状态失败');
        
        const data = await response.json();
        console.log('Received task status data:', data);
        console.log('Number of tasks:', Object.keys(data).length);
        
        if (window.taskManager) {
            window.taskManager.updateTasksFromRedis(data);
        }
    } catch (error) {
        console.error('Error updating tasks:', error.message);
    }
}

// 页面加载完成后的初始化
document.addEventListener('DOMContentLoaded', function() {
    // 初始化任务管理器
    window.taskManager = new TaskManager();
    
    // 定时更新任务状态 - 每20秒
    let updateInterval = null; // 添加一个变量来存储interval ID

    // 如果已经有定时器在运行，先清除它
    if (updateInterval) {
        clearInterval(updateInterval);
    }

    // 设置新的定时器
    updateInterval = setInterval(updateCurrentTask, 20000);
    
    // 只在初始化时执行一次更新
    if (!window.initialUpdateDone) {
        updateCurrentTask();
        window.initialUpdateDone = true;
    }
    
    // 刷新任务按钮
    const refreshTasksBtn = document.getElementById('refreshTasksBtn');
    if (refreshTasksBtn) {
        refreshTasksBtn.addEventListener('click', function() {
            updateCurrentTask();
        });
    }
    
    // 首先检查必要的 DOM 元素是否存在
    const generatorForm = document.getElementById('generatorForm');
    const promptsContainer = document.getElementById('promptsContainer');
    const promptsList = document.getElementById('promptsList');
    const generateVideosBtn = document.getElementById('generateVideos');

    // 如果不在生成器页面，直接返回
    if (!generatorForm) {
        console.log('Not on generator page, skipping initialization');
        return;
    }

    // 存储当前的提示词数据
    let currentPrompts = [];

    // 表单提交处理
    generatorForm.addEventListener('submit', function(e) {
        e.preventDefault();
        generatePrompts();
    });

    // 生成提示词函数
    async function generatePrompts() {
        const content = document.getElementById('content').value;
        const style = document.getElementById('style').value;
        const numSegments = document.getElementById('numSegments').value;
        const model = document.getElementById('model').value;  // 添加模型参数
        
        if (!content || !style) {
            alert('请填写文案和选择风格');
            return;
        }
        
        // 禁用提交按钮
        const submitBtn = generatorForm.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        submitBtn.textContent = '生成中...';
        
        try {
            const response = await fetch('/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    content: content,
                    style: style,
                    model: model,  // 添加模型参数
                    num_segments: numSegments
                }),
            });
            
            const data = await response.json();
            
            if (!data.success) {
                throw new Error(data.message || data.error || '生成提示词失败');
            }
            
            // 显示提示词
            currentPrompts = data.prompts;
            displayPrompts(data.prompts);
            promptsContainer.style.display = 'block';
            
        } catch (error) {
            console.error('Error:', error);
            handleError(error);
        } finally {
            // 重置按钮状态
            submitBtn.disabled = false;
            submitBtn.textContent = '生成提示词';
        }
    }
    
    // 显示提示词函数
    function displayPrompts(prompts) {
        promptsList.innerHTML = '';
        
        prompts.forEach((prompt, index) => {
            const promptItem = document.createElement('div');
            promptItem.className = 'list-group-item';
            promptItem.innerHTML = `
                <div class="d-flex justify-content-between align-items-start">
                    <div class="ms-2 me-auto">
                        <div class="fw-bold">片段 ${index + 1}</div>
                        <div class="small text-break">${prompt}</div>
                    </div>
                </div>
            `;
            promptsList.appendChild(promptItem);
        });
    }
    
    // 重新生成提示词
    document.getElementById('regeneratePrompts').addEventListener('click', function() {
        generatePrompts();
    });

    // 生成视频按钮点击事件
    if (generateVideosBtn) {
        generateVideosBtn.addEventListener('click', async function() {
            if (currentPrompts.length === 0) {
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
            
            try {
                // 生成批次ID
                const batchId = 'batch_' + Date.now();
                const content = document.getElementById('content').value;
                
                // 为每个片段单独提交任务
                for (let i = 0; i < currentPrompts.length; i++) {
                    const prompt = currentPrompts[i];
                    
                    const response = await fetch('/api/generate-video', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            prompt: prompt,
                            model: model,
                            segment_index: i,
                            total_segments: currentPrompts.length,
                            batch_id: batchId,
                            content: content  // 添加原始内容
                        }),
                    });
                    
                    const data = await response.json();
                    console.log(`片段 ${i+1} 响应:`, data);
                    
                    if (data.success) {
                        // 添加任务到任务管理器，包含批次信息
                        const taskId = window.taskManager.addTask({
                            content: `片段 ${i+1}: ${prompt}`,
                            style: document.getElementById('style').value,
                            modelName: document.getElementById('model').options[document.getElementById('model').selectedIndex].text,
                            prompt: prompt,
                            prompt_id: data.prompt_id,
                            segment_index: i,
                            total_segments: currentPrompts.length,
                            batch_id: batchId
                        });
                        
                        console.log('添加任务:', {
                            taskId: taskId,
                            prompt_id: data.prompt_id,
                            segment_index: i,
                            batch_id: batchId
                        });
                    } else {
                        alert(`片段 ${i+1} 提交失败: ${data.error || '未知错误'}`);
                    }
                }
                
                // 关闭模态框
                const modal = bootstrap.Modal.getInstance(document.getElementById('videoGeneratorModal'));
                modal.hide();
                
                // 显示成功消息
                handleSuccess(`已提交 ${currentPrompts.length} 个视频生成任务，请在监控墙查看进度`);
                
                // 重置表单
                generatorForm.reset();
                promptsContainer.style.display = 'none';
                
            } catch (error) {
                console.error('Error:', error);
                handleError(error);
            } finally {
                // 重置按钮状态
                this.disabled = false;
                this.textContent = '开始生成视频';
            }
        });
    }
});

// 修改错误处理函数，使其更明显
function handleError(error) {
    console.error('Detailed error:', error);
    
    const errorContainer = document.createElement('div');
    errorContainer.className = 'alert alert-danger alert-dismissible fade show mt-3';
    errorContainer.style.position = 'fixed';
    errorContainer.style.top = '20px';
    errorContainer.style.left = '50%';
    errorContainer.style.transform = 'translateX(-50%)';
    errorContainer.style.zIndex = '1050';
    errorContainer.innerHTML = `
        <strong>错误：</strong> ${error.message}
        <br>
        <small class="text-muted">如果问题持续存在，请联系管理员</small>
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(errorContainer);
    
    // 5秒后自动消失
    setTimeout(() => {
        errorContainer.classList.remove('show');
        setTimeout(() => errorContainer.remove(), 150);
    }, 5000);
}

// 添加成功消息处理函数
function handleSuccess(message) {
    const successContainer = document.createElement('div');
    successContainer.className = 'alert alert-success alert-dismissible fade show mt-3';
    successContainer.style.position = 'fixed';
    successContainer.style.top = '20px';
    successContainer.style.left = '50%';
    successContainer.style.transform = 'translateX(-50%)';
    successContainer.style.zIndex = '1050';
    successContainer.innerHTML = `
        <strong>成功：</strong> ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    document.body.appendChild(successContainer);
    
    // 3秒后自动消失
    setTimeout(() => {
        successContainer.classList.remove('show');
        setTimeout(() => successContainer.remove(), 150);
    }, 3000);
}

// 视频预览控制器
class VideoPreviewController {
    constructor() {
        this.player = document.getElementById('previewPlayer');
        this.progressBar = document.getElementById('videoProgress');
        this.currentTimeDisplay = document.getElementById('currentTime');
        this.durationDisplay = document.getElementById('duration');
        this.prevButton = document.getElementById('prevSegment');
        this.nextButton = document.getElementById('nextSegment');
        this.segments = [];
        this.currentSegmentIndex = 0;
        
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        if (!this.player) return;
        
        // 进度条控制
        this.progressBar.addEventListener('input', () => {
            const time = (this.progressBar.value / 100) * this.player.duration;
            this.player.currentTime = time;
        });
        
        // 时间更新
        this.player.addEventListener('timeupdate', () => {
            const progress = (this.player.currentTime / this.player.duration) * 100;
            this.progressBar.value = progress;
            this.currentTimeDisplay.textContent = this.formatTime(this.player.currentTime);
        });
        
        // 视频加载完成
        this.player.addEventListener('loadedmetadata', () => {
            this.durationDisplay.textContent = this.formatTime(this.player.duration);
        });
        
        // 切换片段
        this.prevButton.addEventListener('click', () => this.playSegment(this.currentSegmentIndex - 1));
        this.nextButton.addEventListener('click', () => this.playSegment(this.currentSegmentIndex + 1));
    }
    
    setSegments(segments) {
        this.segments = segments;
        this.currentSegmentIndex = 0;
        this.updateNavigationButtons();
        if (segments.length > 0) {
            this.playSegment(0);
        }
    }
    
    playSegment(index) {
        if (index >= 0 && index < this.segments.length) {
            this.currentSegmentIndex = index;
            const segment = this.segments[index];
            this.player.src = segment.videoUrl;
            this.player.play();
            this.updateNavigationButtons();
        }
    }
    
    updateNavigationButtons() {
        this.prevButton.disabled = this.currentSegmentIndex <= 0;
        this.nextButton.disabled = this.currentSegmentIndex >= this.segments.length - 1;
    }
    
    formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
}

// 初始化预览控制器
document.addEventListener('DOMContentLoaded', function() {
    if (document.getElementById('previewPlayer')) {
        window.videoPreviewController = new VideoPreviewController();
    }
}); 