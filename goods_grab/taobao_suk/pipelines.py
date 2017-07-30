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


class TaobaoSukPipeline(object):

    collection_name = 'taobao_info'
    collection_name_list = \
        {
              'goods_info': ('goods_id',),
              'shop_info': ('shop_id',),
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

        for k, v in self.collection_name_list.items():
            if len(v) == 1:
                self.db[k].ensure_index(v[0], unique=True)

    def process_item(self, item, spider):
        #  当去重字段为1个的时候 直接插入， 如果去重判断为多个字段时候拼接字符串生成MD5作为unique_id
        try:
            dict_item = dict(item['detail'])
            # self.db[self.collection_name].insert(dict_item)
            for k, v in dict_item.items():
                self.db[k].insert(v)

            spider.logger.debug(dict_item)
        except DuplicateKeyError:
            spider.logger.debug(' duplicate key error collection')
        except:
            spider.logger.error(format_exc())
        return item

    def close_spider(self, spider):
        self.client.close()
