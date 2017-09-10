# -*- coding: utf-8 -*-

# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: http://doc.scrapy.org/en/latest/topics/item-pipeline.html
from scrapy.conf import settings
import hashlib
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from traceback import format_exc
from datetime import datetime, timedelta
import os
import redis

class TaobaoSukPipeline(object):

    collection_name = 'taobao_info'
    collection_name_list = \
        {
              'goods_info': ('goods_id', 'modified', 'date'),
              'daily_master': ('goods_id', 'modified', 'date'),
         }

    unique_index = 'pag_id'

    def __init__(self, mongo_uri, mongo_db):
        self.mongo_uri = mongo_uri
        self.mongo_db = mongo_db

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            mongo_uri=crawler.settings.get('MONGODB_URI'),
            mongo_db=settings.get('MONGODB_DATABASE', 'items')
        )

    def open_spider(self, spider):
        self.client = MongoClient(self.mongo_uri)
        self.db = self.client[self.mongo_db]
        self.start_time = datetime.now()
        self.date = datetime.fromordinal(datetime.today().toordinal())

        for k, v in self.collection_name_list.items():
            for v_items in v:
                self.db[k].ensure_index(v_items)

        redis_url = os.environ.get('REDIS_URL', None)
        pool = redis.ConnectionPool.from_url(redis_url)
        rds = redis.StrictRedis(connection_pool=pool)
        REDIS_KEY_DUMMY_SHOP_URLS = 'dummy_goods_grab:start_urls'
        REDIS_KEY_SHOP_URLS = 'goods_grab:start_urls'
        if rds.scard(REDIS_KEY_DUMMY_SHOP_URLS) == 0:
            values = list(rds.smembers(REDIS_KEY_SHOP_URLS))
            for i in range(0, len(values), 100):
                rds.sadd(REDIS_KEY_DUMMY_SHOP_URLS, *values[i: i + 100])

    def process_item(self, item, spider):
        #  当去重字段为1个的时候 直接插入， 如果去重判断为多个字段时候拼接字符串生成MD5作为unique_id
        try:
            dict_item = dict(item['detail'])
            for k, v in dict_item.items():
                self.db[k].insert(v)
            spider.logger.debug(dict_item)

            goods_info_ = dict_item['goods_info']
            totalQuantity_today = goods_info_['totalQuantity']
            date = datetime.today() - timedelta(days=1)
            date = date.toordinal()
            date = datetime.fromordinal(date)
            query_item = self.db['goods_info'].find_one({'goods_id': goods_info_['goods_id'], 'date': date})

            if query_item:
                quantity = query_item.get('totalQuantity', totalQuantity_today)
            else:
                quantity = totalQuantity_today

            dict_item['goods_info']['Daily_Sales'] = quantity - totalQuantity_today
            self.db['daily_master'].insert(dict_item['goods_info'])
            spider.logger.debug(dict_item['goods_info'])

        except DuplicateKeyError:
            spider.logger.debug(' duplicate key error collection')
        except:
            spider.logger.error(format_exc())
        return item

    def close_spider(self, spider):
        num = self.db['goods_info'].find({'date': datetime.fromordinal(datetime.today().toordinal())}).count()
        shop_info_log = {'start': self.start_time,
                         'end': datetime.now(),
                         'date': self.date,
                         'count': num}
        self.db['goods_info_log'].insert(shop_info_log)
        self.client.close()

