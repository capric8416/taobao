#!/usr/bin.env python3
# coding=utf-8
import requests
import time
import hashlib
import random


class ProxySwift(object):

    def requerst_get(self, url, data, *p, **kwargs):
        SecretKey = '3JCx8fAF7Bpq5Aj4t9wS7cfVB7hpXZ7j'

        PartnerID = '2017061217350058'
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

    def get_ip(self, interface_id='', pool_id='2'):
        url = 'https://api.proxyswift.com/ip/get'
        data = {
            'server_id': '1',
            'pool_id': pool_id,
            'interface_id': interface_id,
        }
        r = self.requerst_get(url, data)
        response = r.json()
        return response

    def get_task(self, task_id):
        url = 'https://api.proxyswift.com/task/get'
        data = {'task_id': task_id}
        r = self.requerst_get(url, data)

        return r.json()

    def changes_ip(self, interface_id, filter=24):
        url = 'https://api.proxyswift.com/ip/change'
        data = {
            'server_id': '1',
            'interface_id': interface_id,
            'filter': filter,
        }

        r = self.requerst_get(url, data)
        task_id = r.json()['taskId']
        #status = self(task_id)['status']

        i = 1
        while True:
            time.sleep(i%2+1)
            status = self.get_task(task_id)['status']
            if status == 'success':
                ip_port = self.get_ip(interface_id)
                return ip_port



class ProxyPool(object):
    def __init__(self, proxyswift=ProxySwift(), interval = 4):

        self.interval = interval
        self.ps = proxyswift
        self.count = 0
        self.index = 0
        self.pool = self.ps.get_ip()

    def get(self):
        #从 pool中随机取一个ip
        ip = "{0}:10000".format(random.choice(self.pool)['ip'])
        return ip

    def change_ip(self,proxy_server):
        for ip in self.pool:
            if proxy_server == "http://%(ip)s:%(port)s" % ip:
                self.pool.pop(0)
                self.ps.changes_ip(ip['id'])
                self.pool = self.ps.get_ip()
                time.sleep(1)
                break


if __name__ == '__main__':
    s = ProxySwift()

    s.changes_ip(11)

    print(s.get_ip())
