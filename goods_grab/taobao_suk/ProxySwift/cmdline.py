#!/usr/bin/env python3
# coding=utf-8
import os
import subprocess

root_path, file_name = os.path.split(os.path.realpath(__file__))
ProxyPool_path = ''.join([root_path, os.path.sep, 'ProxyPool.py'])
python_path = 'D:\Python36\python.exe'


def change_ip(proxy_server):
    subprocess.Popen([python_path, ProxyPool_path, 'change_ip', proxy_server],
                     shell=True,
                     stdout=subprocess.PIPE
                     )


def refresh_ip():
    subprocess.Popen([python_path, ProxyPool_path, 'refresh_ip'],
                     shell=True,
                     stdout=subprocess.PIPE
                     )

if __name__ == '__main__':
    refresh_ip()
    pass