#! /usr/bin/env python3
# -*- code: utf-8 -*-
import os
import time

import redis
import subprocess

redis_url = os.environ.get('REDIS_URL', None) or 'redis://10.10.10.51:6378'
pool = redis.ConnectionPool.from_url(redis_url)
rds = redis.StrictRedis(connection_pool=pool)


def close_spider():
    subprocess.call(['supervisorctl', 'stop', 'goods_detail'], shell=True)


def check_redis_key():
    return rds.exists('dummy_goods_grab:start_urls')


def __main():
    if check_redis_key():
        time.sleep(5 * 60)
        if not check_redis_key():
            close_spider()
            print('close spider')
        else:
            print('can not close spider')

if __name__ == '__main__':
    __main()
