# -*- coding: utf-8 -*-
# !/usr/bin/env python


import signal


class GracefullyExit(object):
    """
    捕获终止信号
    """

    received = False

    def __init__(self):
        """
        注册终止信号回调函数
        """

        for _signal in (signal.SIGINT, signal.SIGTERM):
            signal.signal(_signal, self.exit_gracefully)

    def exit_gracefully(self, signum, frame):
        """
        如果收到终止信号，设置标志位
        :param signum:
        :param frame:
        :return:
        """

        _ = signum
        _ = frame
        self.received = True
