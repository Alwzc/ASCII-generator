#!/usr/bin/env python3
import os
from app import create_app

# 设置环境变量
os.environ['PYTHONUNBUFFERED'] = '1'  # 禁用 Python 输出缓冲
os.environ['FLASK_ENV'] = 'development'  # 设置为开发环境
os.environ['FLASK_DEBUG'] = '1'  # 启用调试模式

def main():
    try:
        print("=== 开始启动应用 ===")
        app = create_app()
        
        # 打印注册的路由
        print("\n=== 已注册的路由 ===")
        for rule in app.url_map.iter_rules():
            print(f"{rule.endpoint}: {rule.methods} - {rule}")
        
        # 启动应用
        print("\n=== 启动 Flask 服务器 ===")
        app.run(
            debug=True,
            port=5000,
            use_reloader=True,  # 启用热重载
            threaded=True  # 启用多线程
        )
        
    except Exception as e:
        print(f"启动失败: {str(e)}")
        return 1

if __name__ == "__main__":
    exit(main()) 