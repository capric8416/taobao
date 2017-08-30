# -*- coding: utf-8 -*-
# !/usr/bin/env python


import logging
import logging.handlers
import os


def get_logger(name, task_id, log_dir, log_level=logging.INFO):
    """
    构造并返回日志记录器
    :param name: str, 名字
    :param task_id: int, 任务id
    :param log_dir: str, 日志路径
    :param log_level: int, 日志级别
    :return: object, 日志记录器
    """

    _logger = logging.getLogger(name)
    _logger.setLevel(log_level)

    log_dir = os.path.expanduser(log_dir)
    if not os.path.exists(log_dir) or not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_dir, f'{task_id}.log'), when='D', backupCount=30, encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(name)s - %(lineno)d - %(levelname)s - %(message)s')
    )

    _logger.addHandler(file_handler)

    return _logger
