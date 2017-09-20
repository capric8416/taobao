# -*- coding: utf-8 -*-
# !/usr/bin/env python

import itertools
import os
import re
from multiprocessing.dummy import Pool as ThreadPool

import openpyxl
import pymongo


class TranslateGoodsName(object):
    def __init__(self, mapping_excel, workers=20, mongo_db='test', mongo_collection='name_mapping',
                 mongo_url=os.environ.get('MONGO_URL') or 'mongodb://localhost:27017/'):
        self.mapping_excel = mapping_excel
        self.workers = workers
        self.mongo_db = mongo_db
        self.mongo_collection = mongo_collection
        self.mongo_client = pymongo.MongoClient(mongo_url)

    def load_excel(self):
        workbook = openpyxl.load_workbook(self.mapping_excel)

        return [[cell.value for cell in row] for row in workbook.active.iter_rows()]

    def import_mapping(self):
        data = self.load_excel()

        body = data[1:]

        head = data[0]
        for index, item in enumerate(head):
            head[index] = re.sub('\s+', '_', item.strip())

        pool = ThreadPool(processes=self.workers)
        pool.starmap(self._import_mapping, zip(itertools.repeat(head, len(body)), body))
        pool.close()
        pool.join()

    def _import_mapping(self, head, body):
        data = {}
        for key, value in zip(head, body):
            data[key] = value.strip() if isinstance(value, str) else value

        print(data)

        self.mongo_client[self.mongo_db][self.mongo_collection].update_one(
            filter={'goods_id': data['goods_id']}, update={'$set': data}, upsert=True)

    def update_goods_main(self, collection_name):
        mapping = {
            item['goods_id']: item['goods_name']
            for item in self.mongo_client[self.mongo_db][self.mongo_collection].find()
        }

        data = []
        for item in self.mongo_client[self.mongo_db][collection_name].find():
            item['standard_name'] = mapping.get(item['id'], '')
            data.append(item)

        pool = ThreadPool(processes=self.workers)
        pool.starmap(self._update_goods_main, zip(itertools.repeat(collection_name, len(data)), data))
        pool.close()
        pool.join()

    def _update_goods_main(self, collection_name, record):
        print(record['id'], record['standard_name'])

        self.mongo_client[self.mongo_db][collection_name].update_one(
            filter={'_id': record['_id']}, update={'$set': {'standard_name': record['standard_name']}})


if __name__ == '__main__':
    translate = TranslateGoodsName(mapping_excel='mapping.xlsx')
    translate.import_mapping()
    # translate.update_goods_main(collection_name='goods_list')
