# -*- coding: utf-8 -*-
# !/usr/bin/env python

import json
import multiprocessing
import random
import time

import redis


REDIS = redis.Redis.from_url('redis://localhost:6379/1')


def import_shops():
    key = 'shops'
    path = 'data/shop_urls.json'

    REDIS.delete(key)

    with open(path, encoding='utf-8') as fp:
        shops = json.load(fp)
        for index, item in enumerate(shops):
            if not isinstance(item, str):
                item = json.dumps(item, ensure_ascii=False)
            print('import:', index, item)
            REDIS.sadd(key, item)


def export_items():
    key = 'items'
    path = 'data/shop_goods.json'

    with open(path, mode='w', encoding='utf-8') as fp:
        items = []

        index = 0
        while True:
            try:
                item = REDIS.spop(key)
                index += 1
                print('export:', index, item)
                items.append(item.decode('utf-8'))
            except Exception as e:
                _ = e
                break

        json.dump(items, fp, ensure_ascii=False)

        for item in items:
            REDIS.sadd(key, item)


def export_goods():
    key = 'goods'
    path = 'data/goods_lite.json'

    with open(path, mode='w', encoding='utf-8') as fp:
        items = {
            k.decode('utf-8'): json.loads(v.decode('utf-8'), encoding='utf-8')
            for k, v in REDIS.hgetall(key).items()
        }

        json.dump(obj=items, fp=fp, ensure_ascii=False)



class Test(object):
    def f(self, name):
        print('start', name)

        for _ in range(10):
            time.sleep(random.randint(1, 2))

        print('end', name)


    def t(self):
        container = {i: None for i in range(6)}

        while True:
            for k in container:
                if not container[k] or not container[k].is_alive():
                    p = multiprocessing.Process(name=k, target=self.f, args=(k,))
                    p.start()
                    container[k] = p

            time.sleep(0.1)


if __name__ == '__main__':
    # import_shops()
    # export_items()
    export_goods()

    # t = Test()
    # t.t()
