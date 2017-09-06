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

class TaobaoSukPipeline(object):

    collection_name = 'taobao_info'
    collection_name_list = \
        {
              'goods_info': ('goods_id', 'modified', 'date'),
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
    def process_item(self, item, spider):
        #  当去重字段为1个的时候 直接插入， 如果去重判断为多个字段时候拼接字符串生成MD5作为unique_id
        try:
            dict_item = dict(item['detail'])
            goods_info_ = dict_item['goods_info']
            query_item_today = \
                self.db['goods_list'].find_one({'id': goods_info_['goods_id'], 'date': goods_info_['date']})
            spider.logger.debug('query_item_today: {}'.format(query_item_today))
            date = datetime.today() - timedelta(days=1)
            date = date.toordinal()
            date = datetime.fromordinal(date)
            query_item = self.db['goods_list'].find_one({'id': goods_info_['goods_id'], 'date': date})
            
            if query_item:
                quantity = query_item.get('quantity', 0)
            else:
                quantity = 0
            
            dict_item['goods_info']['Daily_Sales'] = query_item_today.get('quantity', 0) - quantity
            
            for k, v in dict_item.items():
                self.db[k].insert(v)

            spider.logger.debug(dict_item)
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

