#!/usr/bin/env python3
# coding=utf-8
import requests
import time
import hashlib
import random


class ProxySwift(object):
    server_id = '2'
    pool_id = '1'

    def requerst_get(self, url, data, *p, **kwargs):
        SecretKey = 'Kg6t55fc39FQRJuh92BwZBMXyK3sWFkJ'

        PartnerID = '2017072514450843'
        TimeStamp = int(time.time())

        source_data = {
            'partner_id': PartnerID,
            'timestamp': TimeStamp
        }

        source_data.update(data)

        tmp_data = [i for i in source_data.items()]
        tmp_data = sorted(tmp_data, key=lambda i: i[0])

        url_list = ['{}{}'.format(*i) for i in tmp_data]
        # url_list.reverse()
        # sign = ''.join(url_list)
        # sign = ''.join(sorted(sign))

        sign = ''.join(url_list)
        # sign = ''.join(sorted(sign))

        data = sign + SecretKey
        md_5 = hashlib.md5()
        md_5.update(data.encode("utf-8"))
        sign = md_5.hexdigest()
        source_data.update({'sign': sign})
        return requests.get(url, params=source_data, verify=False, *p, **kwargs)

    def get_ip(self, interface_id=''):
        url = 'https://api.proxyswift.com/ip/get'
        data = {
            'server_id': self.server_id,
            'pool_id': self.pool_id,
            'interface_id': interface_id,
        }
        r = self.requerst_get(url, data)
        response = r.json()
        for item in response['data']:
            del item['server_id']
            del item['pool_id']
        return response['data']

    def get_task(self, task_id):
        url = 'https://api.proxyswift.com/task/get'
        data = {'task_id': task_id}
        r = self.requerst_get(url, data)

        return r.json()

    def changes_ip(self, interface_id, filter=24):
        url = 'https://api.proxyswift.com/ip/change'
        data = {
            'server_id': self.server_id,
            'interface_id': interface_id,
            'filter': filter,
        }

        r = self.requerst_get(url, data)
        data = r.json()
        assert data['code'] == 202, '换ip失败'
        task_id = data['data']['task_id']
        assert task_id is not None, 'taskId is None, response_result:{}'.format(r.text)

        i = 1
        while True:
            time.sleep(i%2+1)
            data = self.get_task(task_id)

            assert data['code'] == 200, '获取任务失败'
            status = data['data']['status']
            if status == 'success':
                ip_port = self.get_ip(interface_id)
                return ip_port
            elif status == 'failed':
                return None


class ProxyPool(object):
    def __init__(self, proxyswift=ProxySwift(), interval=4):

        self.interval = interval
        self.ps = proxyswift
        self.count = 0
        self.index = 0
        self.pool = self.ps.get_ip()

    def get(self):
        # 从 pool中随机取一个ip
        ip_port = random.choice(self.pool)
        ip = "{0}:{1}".format(ip_port['ip'], ip_port['port'])
        return ip

    def change_ip(self, proxy_server):
        for ip in self.pool:
            if proxy_server == "http://%(ip)s:%(port)s" % ip:
                self.pool.pop(0)
                if self.ps.changes_ip(ip['id']):
                    self.pool = self.ps.get_ip()
                    time.sleep(1)
                    break
                else:
                    self.change_ip(proxy_server)


def refresh():
    s = ProxySwift()
    ip_info_list = s.get_ip()

    for ip_list in ip_info_list:
        s.changes_ip(ip_list['id'])

refresh()

proxyPool = ProxyPool()

if __name__ == '__main__':
    # p = ProxyPool()
    # #
    # # # 随机获取一个ip
    # print(p.get())
    # # # 换ip,  参数为http://115.237.237.167:10003
    # p.change_ip('http://114.231.145.115:10000')

    p = ProxySwift()
    # 参数为 ip的id
    p.changes_ip(11)
    # 参数也为ip的id，不给时  获取所有ip
    # print(p.get_ip())
    # import requests
    # ip_list = p.get_ip()
    # for item in ip_list:
    #     proxies = {
    #         'https': 'http://{}:{}'.format(item['ip'], item['port'])
    #     }
    #     r = requests.get('http://bj.58.com/', proxies=proxies)
    #     pass



