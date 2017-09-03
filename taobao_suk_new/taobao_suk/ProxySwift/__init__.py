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
    __pool = None
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

    def start(self):
        redis_url = self.redis_url or os.environ.get('REDIS_URL', None)
        assert redis_url is not None, 'redis_url is None'

        pool = redis.ConnectionPool.from_url(redis_url)
        self.__redis = redis.StrictRedis(connection_pool=pool)
        self.__live_time = int(str(self.__redis.get('live_time'), 'utf-8'))
        assert self.advance_time <= self.__live_time, 'advance_time > ip_live_time'

        self.__get_all_ip()
        self.__start_refresh_task()

    def __get_all_ip(self):
        data = self.__redis.smembers(self.__available_ip_pool_key_name)
        self.__pool = [json.loads(str(ip, 'utf-8')) for ip in data]
        tmp = list()
        for i in self.__pool:
            if i['ip'] not in self.__blacklist:
                tmp.append(i)
        self.__pool = tmp
        # self.logger.debug('get_all_ip(): now self.pool : {}'.format(self.__pool))
        self.logger.debug('get_all_ip(): now self.pool len : {}'.format(len(self.__pool)))

    def get(self, _times=0):
        # 从 pool中随机取一个ip
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
                return self.get(_times=_times+1)
        else:
            time.sleep(0.1)
            self.logger.debug('get(): __pool is None')
            self.__get_all_ip()
            return self.get(_times=_times+1)

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
        self.__redis.srem(self.__available_ip_pool_key_name, json.dumps(ip_item))
        self.logger.debug('update_live_time(): origin {}'.format(ip_item))
        ip_item['last_time'] -= self.__get_blacklist_seconds()
        self.logger.debug('update_live_time(): changed {}'.format(ip_item))
        result = self.__redis.sadd(self.__available_ip_pool_key_name, json.dumps(ip_item))
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