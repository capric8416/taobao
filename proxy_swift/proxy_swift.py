# -*- coding: utf-8 -*-
# !/usr/bin/env python

import requests
import time
import hashlib
import random

requests.packages.urllib3.disable_warnings()


class ProxySwift(object):
    @staticmethod
    def request_get(url, data):
        secret_key = 'Kg6t55fc39FQRJuh92BwZBMXyK3sWFkJ'
        partner_id = '2017072514450843'
        timestamp = int(time.time())

        source_data = {
            'partner_id': partner_id,
            'timestamp': timestamp
        }

        source_data.update(data)

        sign = ''.join([
            '{}{}'.format(*i)
            for i in sorted(
                [i for i in source_data.items()],
                key=lambda i: i[0]
            )
        ])

        md_5 = hashlib.md5()
        md_5.update((sign + secret_key).encode('utf-8'))
        sign = md_5.hexdigest()
        source_data.update({'sign': sign})

        return requests.get(url, params=source_data, verify=False)

    def get_ip(self, interface_id='', server_id='2', pool_id='3'):
        url = 'https://api.proxyswift.com/ip/get'
        data = {
            'server_id': server_id,
            'pool_id': pool_id,
            'interface_id': interface_id,
        }
        resp = self.request_get(url, data)
        return resp.json()

    def get_task(self, task_id):
        url = 'https://api.proxyswift.com/task/get'
        data = {'task_id': task_id}
        resp = self.request_get(url, data)
        return resp.json()

    def changes_ip(self, interface_id, server_id='2', _filter=24):
        url = 'https://api.proxyswift.com/ip/change'
        data = {
            'server_id': server_id,
            'interface_id': interface_id,
            'filter': _filter,
        }

        resp = self.request_get(url, data)
        task_id = resp.json()['taskId']

        i = 1
        while True:
            time.sleep(i % 2 + 1)
            status = self.get_task(task_id)['status']
            if status == 'success':
                ip_port = self.get_ip(interface_id)
                return ip_port


class ProxyPool(object):
    def __init__(self, proxy_swift=ProxySwift(), interval=4):
        self.interval = interval
        self.proxy_swift = proxy_swift
        self.count = 0
        self.index = 0
        self.pool = self.proxy_swift.get_ip()

    def get(self):
        # 从 pool中随机取一个ip
        ip = '{0}:10000'.format(random.choice(self.pool)['ip'])
        return ip

    def change_ip(self, proxy_server):
        for ip in self.pool:
            if proxy_server == 'http://%(ip)s:%(port)s' % ip:
                self.pool.pop(0)
                self.proxy_swift.changes_ip(ip['id'])
                self.pool = self.proxy_swift.get_ip()
                time.sleep(1)
                break


if __name__ == '__main__':
    _proxy_pool = ProxyPool()

    # 随机获取一个ip
    print(_proxy_pool.get())
    # 换ip, 参数为http://115.237.237.167:10003
    _proxy_pool.change_ip('http://115.237.237.167:10003')

    _proxy_swift = ProxySwift()
    # 参数为ip的id
    _proxy_swift.changes_ip(31)
    # 参数也为ip的id, 不给时获取所有ip
    print(_proxy_swift.get_ip())
