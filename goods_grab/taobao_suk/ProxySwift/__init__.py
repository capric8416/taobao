#!/usr/bin/env python3
# coding=utf-8
#!/usr/bin/env python3
# coding=utf-8
import time
import datetime
import logging
import logging.handlers
import os
import json
import random
import redis
from threading import Thread
'''
使用说明：
单例模式，请不要自行实例化类生产对象
直接导入proxy_pool使用即可，目前兼容老接口change_ip（请使用新接口push_blacklist）和get
启动代理池需要配置
proxy_pool.redis_url = ''    # 远端redis_url,不填自动从环境变量获取
proxy_pool.blacklist_clean_timing = 60 * 60 * 24   # 多长时间清理一次黑名单列表默认24小时清理一次
proxy_pool.advance_time = 0 # ip存活预留时间 默认不填的话是10秒，不能大于ip的存活时间
proxy_pool.start()     #  启动代理池   只启动一次不要重复启动，在所有配置完了之后启动就好

函数说明：
get函数随机获取一个ip
例子：
proxy_pool.get()

push_blacklist和change_ip目前为同一个接口，会自动通知主服务器，加快ip更换速度，并且再调用get函数的时候不会再出现拉黑的ip
请在新项目中使用push_blacklist，主要用于拉黑ip，把ip加入黑名单，拉黑后
例子：

proxy_pool.push_blacklist('http://121.226.59.116:10000')
'''
root_path, file_name = os.path.split(os.path.realpath(__file__))


def init_logger(name, task_id, log_dir):
    _logger = logging.getLogger(name)
    _logger.setLevel(logging.DEBUG)

    log_dir = os.path.expanduser(log_dir)
    if not os.path.exists(log_dir) or not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_dir, f'{task_id}.log'), when='D', encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(name)s - %(lineno)d - %(levelname)s - %(message)s')
    )

    _logger.addHandler(file_handler)

    return _logger


class ProxyPool(object):

    # __start_time = datetime.datetime.now()
    __available_ip_pool_key_name = 'available_ip_set'
    __death_ip_set_key_name = 'death_ip_set'
    __blacklist = set()
    redis_url = None
    blacklist_clean_timing = 60 * 60 * 24
    advance_time = 0
    __pool = []
    __pool_status = False

    def __init__(self):

        self.logger = init_logger(file_name,
                                  'ProxyPool',
                                  ''.join([root_path, os.path.sep, 'RedisProxyPoolLog']))
        self.logger.info(''.center(50, "*"))
        self.logger.info('proxy_pool is running'.center(50, "*"))
        self.logger.info(''.center(50, "*"))
        self.__redis = None
        self.__live_time = None
        self.type_able_code = None
        self.type_backup_code = None

    def start(self):
        redis_url = self.redis_url or os.environ.get('REDIS_URL', None)
        self.type_able_code = self.type_able_code if self.type_able_code is not None else [1000000]
        self.type_backup_code = \
            self.type_backup_code if self.type_backup_code is not None else [1000000, 1000001, 1000002]
        assert redis_url is not None, 'redis_url is None'

        pool = redis.ConnectionPool.from_url(redis_url)
        self.__redis = redis.StrictRedis(connection_pool=pool)
        self.__live_time = int(str(self.__redis.get('live_time'), 'utf-8'))
        assert self.advance_time <= self.__live_time, 'advance_time > ip_live_time'

        self.__get_all_ip()
        self.__start_refresh_task()

    def __get_all_ip(self):
        data = self.__redis.smembers(self.__available_ip_pool_key_name)
        __pool = [json.loads(str(ip, 'utf-8')) for ip in data]
        tmp = dict()
        tmp[1000000] = list()
        tmp[1000001] = list()
        tmp[1000002] = list()
        for i in __pool:
            if i['ip'] not in self.__blacklist:
                if i['id'] < 1000000:
                    tmp[1000000].append(i)
                elif i['id'] == 1000001:
                    tmp[1000001].append(i)
                elif i['id'] == 1000002:
                    tmp[1000002].append(i)
        tmp_pool = list()
        for code in self.type_able_code:
            tmp_pool += tmp[code]
        #  如果没有取到符合要求的ip  就启动备用方案

        if not tmp_pool:
            for code in self.type_backup_code:
                tmp_pool += tmp[code]
        self.__pool = tmp_pool
        # self.logger.debug('get_all_ip(): now self.pool : {}'.format(self.__pool))
        self.logger.debug('get_all_ip(): now self.pool len : {}'.format(len(self.__pool)))

    def get(self, _times=0):
        # 从 pool中随机取一个ip
        while True:
            if _times >= 10:
                logging.info('retry times too many'.center(50, '*'))
                time.sleep(20)

            if self.__pool:
                ip_port = random.choice(self.__pool)

                now = datetime.datetime.now().timestamp()
                if ip_port['last_time'] >= int(now) + self.advance_time and ip_port['ip'] not in self.__blacklist:
                    tmp_ip = "{0}:{1}".format(ip_port['ip'], ip_port['port'])
                    return tmp_ip
                else:
                    self.logger.debug('get(): ip in blacklist, or living is None, again')
                    # self.__get_all_ip()
                    _times += 1
                    continue
            else:
                time.sleep(0.1)
                self.logger.debug('get(): __pool is None')
                self.__get_all_ip()
                _times += 1
                continue

    def change_ip(self, proxy_server):
        self.push_blacklist(proxy_server)

    def push_blacklist(self, proxy_server):
        task = Thread(target=self.__push_blacklist_task, args=(proxy_server,))
        task.start()

    def __push_blacklist_task(self, proxy_server):
        for ip_item in self.__pool:
            if proxy_server == "http://%(ip)s:%(port)s" % ip_item:
                self.logger.debug('push_blacklist(): {}'.format(ip_item))
                self.__update_live_time(ip_item)
                self.__add_blacklist(ip_item)
        # self.__get_all_ip()

    def __add_blacklist(self, ip_item):
        self.__blacklist.add(ip_item['ip'])
        self.logger.debug('add_blacklist(): blacklist num = {}'.format(len(self.__blacklist)))

    def __get_connected_clients(self):
        connected_clients = self.__redis.info()['connected_clients']
        connected_num = connected_clients - 3
        return int(connected_num) or 1

    def __get_blacklist_seconds(self):
        clients = self.__get_connected_clients()
        return int(self.__live_time / clients)

    def __update_live_time(self, ip_item):
        self.__redis.srem(self.__available_ip_pool_key_name,
                          '{{"id": {id}, "ip": "{ip}", "port": {port}, "last_time": {last_time}}}'.format(**ip_item))
        self.logger.debug('update_live_time(): origin {}'.format(ip_item))
        ip_item['last_time'] -= self.__get_blacklist_seconds()
        self.logger.debug('update_live_time(): changed {}'.format(ip_item))
        result = self.__redis.sadd(self.__available_ip_pool_key_name,
                                   '{{"id": {id}, "ip": "{ip}", "port": {port}, "last_time": {last_time}}}'.
                                   format(**ip_item))
        self.logger.debug('update_live_time(): push redis available_ip_pool result{}'.format(result))
        # self.__get_all_ip()

    def __refresh_task(self):
        while True:
            time.sleep(7)
            try:
                self.__get_all_ip()
            except None:
                pass

    def __timing_clean_blacklist_task(self):
        while True:
            time.sleep(self.blacklist_clean_timing)
            self.__blacklist = set()

    def __start_refresh_task(self):
        pass
        task = Thread(target=self.__refresh_task)
        task.setDaemon(True)
        task.start()
        task = Thread(target=self.__timing_clean_blacklist_task)
        task.setDaemon(True)
        task.start()


proxy_pool = ProxyPool()
'''
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

# refresh()

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



'''