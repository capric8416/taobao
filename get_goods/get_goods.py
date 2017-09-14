# -*- coding: utf-8 -*-
# !/usr/bin/env python

import asyncio
import copy
import hashlib
import json
import math
import os
import re
import sys
import time
from datetime import datetime
from urllib import parse

import aiohttp
import aioredis
import motor.motor_asyncio
from pyquery import PyQuery
from proxy_swift import get_logger


DEBUG = True if '--debug' in sys.argv else False

PREFIX = '' if not DEBUG else 'Q1H4siXpVa_'

STEP = 100

TAOBAO_ERROR_URL = 'err.taobao.com'

DATE_TIME_FORMAT = '%Y-%m-%d %H:%M:%S.%f'

REDIS_KEY_USER_AGENTS = PREFIX + 'user_agents'

REDIS_KEY_SHOP_URLS = 'shop_urls'
REDIS_KEY_DUMMY_SHOP_URLS = PREFIX + 'dummy_shop_urls'
REDIS_KEY_GOODS_URLS = PREFIX + 'goods_grab:start_urls'
REDIS_KEY_TASK_RUNNING = PREFIX + 'running_task_goods_list'

MONGO_DB = PREFIX + 'test'
MONGO_COLLECTION_GOODS = 'goods_list'
MONGO_COLLECTION_GOODS_MAIN = 'goods_list_main'
MONGO_COLLECTION_GOODS_LOG = 'goods_list_logs'


class AuthError(Exception):
    pass


class GetShopItemList(aiohttp.ClientSession):
    def __init__(self, delay=3, timeout=15, user_agent='', proxy=None):
        super(GetShopItemList, self).__init__()

        self.logger = get_logger(__name__)

        self.delay = delay
        self.timeout = timeout
        self.proxy = proxy
        self.user_agent = user_agent or 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ' \
                                        '(KHTML, like Gecko) Chrome/61.0.3163.39 Safari/537.36'

        self.tmall = 'tmall'
        self.taobao = 'taobao'

        self.search_url = ''
        self.search_keyword = ''

        self.host_error_taobao = 'err.taobao.com'

        self.params = {
            self.tmall: {
                'q': '',
                'p': None,
                'ajson': 1,
                'sort': 'd',
                'from': 'h5',
                'shop_id': None,
                'page_size': None,
                '_input_charset': 'utf-8',
                '_tm_source': 'tmallsearch',
                'callback': 'jsonp_23748483'
            },
            self.taobao: {
                't': '',
                'v': '2.0',
                'data': '',
                '_m_h5_tk': '',
                'type': 'jsonp',
                'dataType': 'jsonp',
                'appKey': '12574478',
                'callback': 'mtopjsonp1',
                'api': 'com.taobao.search.api.getShopItemList'
            }
        }

    async def search(self, shop_id, query):
        self.search_keyword = query

        resp = await self._open(shop_id=shop_id, query=query)
        if resp.url.host == self.host_error_taobao:
            raise AuthError('访问受限')

        results = []

        data = {}
        if resp.url.host.endswith('.tmall.com'):
            shop_type = self.tmall
            self.search_url = f'https://{resp.url.host}/shop/shop_auction_search.htm' \
                              f'?q={query}&_input_charset=utf-8&sort=d'

            text = await self._search(hostname=resp.url.host, shop_id=shop_id, shop_type=shop_type, query=query)
            data = self._json(text=text, callback=self.params[shop_type]['callback'])
            results.append(data)

            total_page = int(data['total_page'])
            if total_page:
                for page in range(2, total_page + 1):
                    await asyncio.sleep(self.delay)

                    text = await self._search(
                        hostname=resp.url.host, shop_id=shop_id, shop_type=shop_type, query=query, page=page)
                    data = self._json(text=text, callback=self.params[shop_type]['callback'])
                    results.append(data)
        else:
            shop_type = self.taobao
            for _ in range(10):
                text = await self._search(hostname='', shop_id=shop_id, shop_type=shop_type, query=query)
                data = self._json(text=text, callback=self.params[shop_type]['callback'])
                if data['ret'] == ['SUCCESS::调用成功']:
                    break
                elif data['ret'] == ['RGV587_ERROR::SM']:
                    raise AuthError('要求登录')

            if not data:
                raise AuthError('调用接口失败')

            results.append(data)

            total_results = int(data['data']['totalResults'])
            if total_results:
                page_size = int(data['data']['pageSize'])
                pages = int(math.ceil(total_results / page_size))
                for page in range(2, pages + 1):
                    await asyncio.sleep(self.delay)

                    text = await self._search(hostname='', shop_id=shop_id, shop_type=shop_type, query=query, page=page)
                    data = self._json(text=text, callback=self.params[shop_type]['callback'])
                    results.append(data)

        now = datetime.now()
        return self._extract(shop_type=shop_type, now=now, today=now.today(), results=results)

    async def _open(self, shop_id, query):
        url = f'http://shop.m.taobao.com/shop/shop_index.htm?shop_id={shop_id}#list?q={parse.quote(query)}'
        self.search_url = url

        resp = await self._request_data(url=url)
        return resp

    async def _search(self, shop_id, shop_type, hostname, query, page=1):
        if shop_type == self.taobao:
            self.params[shop_type].update({
                't': self._timestamp(),
                '_m_h5_tk': self._token(),
                'data': f'{{"shopId": "{shop_id}", "currentPage": {page}, '
                        f'"pageSize": 30, "q": "{query}", "sort": "hotsell"}}'
            })
            self.params[shop_type]['sign'] = self._sign()

            return await self._request_data(
                url='https://api.m.taobao.com/h5/com.taobao.search.api.getshopitemlist/2.0/',
                params=self.params[shop_type], as_text=True,
                headers={'Referer': f'http://shop.m.taobao.com/shop/shop_index.htm?shop_id={shop_id}'}
            )
        else:
            url = f'https://{hostname}/shop/shop_auction_search.do'
            self.params[shop_type].update({
                'p': page,
                'q': query,
                'page_size': 24,
                'shop_id': shop_id,
            })

            return await self._request_data(
                url=url, params=self.params[shop_type], as_text=True,
                headers={'Referer': f'https://{hostname}/shop/shop_auction_search.htm'
                                    f'?q={parse.quote(query)}&_input_charset=utf-8&sort=d'}
            )

    def _extract(self, shop_type, now, today, results):
        goods_list = []

        if shop_type == self.tmall:
            for page in results:
                for item in page.get('items', []):
                    goods_url = 'https:' + item['url'] if item['url'].startswith('//') else item['url']
                    goods_info = {
                        'keyword': self.search_keyword,
                        'search': self.search_url,
                        'search_results': int(page['total_results']),
                        'id': int(item['item_id']),
                        'url': goods_url,
                        'from': '天猫',
                        'shop_id': int(page['shop_id']),
                        'shop_title': page['shop_title'],
                        'image': 'https:' + item['img'] if item['img'].startswith('//') else item['img'],
                        'title': PyQuery(item['title']).text().strip(),
                        'price_highlight': float(item['price']),
                        'price_del': None,
                        'sales': int(item['sold']),
                        'sales_volume': int(item['totalSoldQuantity']),
                        'quantity': int(item['quantity']),
                        'raw': item,
                        'date': datetime.fromordinal(today.toordinal()),
                        'modified': now,
                    }

                    goods_list.append(goods_info)
        else:
            for page in results:
                page = page['data']
                for item in page.get('itemsArray', []):
                    goods_url = 'https://item.taobao.com/item.htm?id=' + item['auctionId']
                    goods_info = {
                        'keyword': self.search_keyword,
                        'search': self.search_url,
                        'search_results': int(page['totalResults']),
                        'id': int(item['auctionId']),
                        'url': goods_url,
                        'from': '淘宝',
                        'shop_id': int(page['shopId']),
                        'shop_title': page['shopTitle'],
                        'image': 'https:' + item['picUrl'] if item['picUrl'].startswith('//') else item['picUrl'],
                        'title': item['title'],
                        'price_highlight': float(item['salePrice']),
                        'price_del': float(item['reservePrice']) if item['reservePrice'] else None,
                        'sales': int(item['sold']),
                        'sales_volume': int(item['totalSoldQuantity']),
                        'quantity': int(item['quantity']),
                        'raw': item,
                        'date': datetime.fromordinal(today.toordinal()),
                        'modified': now,
                    }

                    goods_list.append(goods_info)

        return goods_list

    async def _request_data(self, *args, **kwargs):
        as_text = kwargs.pop('as_text', False)
        as_json = kwargs.pop('as_json', False)

        kwargs = copy.deepcopy(kwargs)
        kwargs['timeout'] = self.timeout
        kwargs['proxy'] = self.proxy
        kwargs['headers'] = kwargs.pop('headers', {})
        kwargs['headers'].update({'User-Agent': self.user_agent})

        async with self.get(*args, **kwargs) as resp:
            if as_json:
                return await resp.json()
            elif as_text:
                return await resp.text()
            else:
                return resp

    def _timestamp(self, as_str=True):
        _ = self

        t = int(time.time())
        return str(t) if as_str else t

    def _token(self):
        for cookie in self.cookie_jar:
            if cookie.key == '_m_h5_tk':
                return cookie.value.partition('_')[0]

        return 'undefined'

    def _sign(self):
        return hashlib.md5('&'.join([
            self.params[self.taobao]['_m_h5_tk'], self.params[self.taobao]['t'],
            self.params[self.taobao]['appKey'], self.params[self.taobao]['data']
        ]).encode()).hexdigest()

    def _json(self, text, callback):
        _ = self

        result = re.search(r'%s\((.*)\)' % callback, text.strip())
        if result and result.group(1):
            return json.loads(result.group(1))

        return {}


class Dispatcher(object):
    def __init__(self, workers, shops_per_proxy, proxy_service_url='http://localhost:8080',
                 redis_url=os.environ.get('REDIS_URL') or 'redis://localhost:6379',
                 mongo_url=os.environ.get('MONGO_URL') or 'mongodb://localhost:27017/'):
        self.logger = get_logger(__name__)

        self.workers = workers
        self.shops_per_proxy = shops_per_proxy

        self.proxy_service_url = proxy_service_url
        self.redis_redis = redis_url
        self.mongo_url = mongo_url

        self.redis_client = None
        self.mongo_client = None

        self.user_agents = []

        self.exceptions = (asyncio.TimeoutError, aiohttp.ClientConnectorError,
                           aiohttp.ClientResponseError, aiohttp.ClientOSError)

    async def start(self):
        self._load_user_agents()

        await self._connect_storage()
        await self._connect_proxy(full_restart=not DEBUG)
        await self._check_shop_urls()

        tasks = [self._check_user_agents(), self._report_progress()]
        for identity in range(self.workers):
            tasks.append(self.get_shop_item_list(identity=identity))

        await asyncio.gather(*tasks)

    async def get_shop_item_list(self, identity):
        async with aiohttp.ClientSession() as session:
            mongo_client, redis_client = await self._connect_storage()
            while True:
                proxy = await self._get_proxy(session=session)
                if not proxy:
                    await asyncio.sleep(1)
                    continue

                for _ in range(self.shops_per_proxy):
                    user_agent = await self._get_user_agent(redis_client=redis_client)
                    if not user_agent:
                        await asyncio.sleep(1)
                        continue

                    shop_info, shop_id, query = await self._pop_shop_info(redis_client=redis_client)
                    if not all([shop_id, query]):
                        return

                    async with GetShopItemList(user_agent=user_agent, proxy=proxy) as client:
                        dt1 = datetime.now()

                        try:
                            goods_list = await client.search(shop_id=int(shop_id), query=query)
                        except self.exceptions as e:
                            self.logger.exception(e)
                            goods_list = []
                            await self._add_shop_info(redis_client=redis_client, shop_info=shop_info)
                            if isinstance(e, AuthError):
                                break
                        else:
                            await self._insert_goods_list(mongo_client=mongo_client, goods_list=goods_list)
                        finally:
                            dt2 = datetime.now()
                            print(identity, (dt2 - dt1).total_seconds(), shop_id, query, proxy, goods_list)

    async def _connect_storage(self):
        mongo_client = motor.motor_asyncio.AsyncIOMotorClient(self.mongo_url)

        _ = parse.urlparse(url=self.redis_redis)
        redis_client = await aioredis.create_redis(address=(_.hostname, _.port), password=_.password)

        if not self.mongo_client:
            self.mongo_client = mongo_client

        if not self.redis_client:
            self.redis_client = redis_client

        return mongo_client, redis_client

    async def _check_shop_urls(self):
        if not await self.redis_client.exists(REDIS_KEY_DUMMY_SHOP_URLS):
            values = list(await self.redis_client.smembers(REDIS_KEY_SHOP_URLS))
            for i in range(0, len(values), STEP):
                await self.redis_client.sadd(REDIS_KEY_DUMMY_SHOP_URLS, *values[i: i + STEP])

    def _load_user_agents(self):
        if not self.user_agents:
            with open('user_agents.txt', encoding='utf-8') as fp:
                self.user_agents = [line.strip() for line in fp]

    async def _check_user_agents(self):
        while True:
            if await self.redis_client.scard(REDIS_KEY_USER_AGENTS) <= self.workers / 2:
                await self.redis_client.sadd(REDIS_KEY_USER_AGENTS, *self.user_agents)

            if not await self.redis_client.exists(REDIS_KEY_DUMMY_SHOP_URLS):
                break

            await asyncio.sleep(10)

    @staticmethod
    async def _get_user_agent(redis_client):
        user_agent = await redis_client.spop(REDIS_KEY_USER_AGENTS)
        return (user_agent or b'').decode()

    async def _connect_proxy(self, full_restart=True):
        async with aiohttp.ClientSession() as client:
            async with client.get(self.proxy_service_url + '/restart' + ('?full=1' if full_restart else '')) as resp:
                data = await resp.json()
                self.workers = min(self.workers, len(data['interfaces']) * 3 // 4)

    async def _get_proxy(self, session):
        async with session.get(self.proxy_service_url + '/get/ip') as resp:
            proxy = await resp.json()
            proxy = None if not proxy else 'http://{ip}:{port}'.format(**proxy)

        return proxy

    @staticmethod
    async def _pop_shop_info(redis_client):
        shop_info = await redis_client.spop(REDIS_KEY_DUMMY_SHOP_URLS)
        if not shop_info:
            return shop_info, None, None

        shop_url, keyword = json.loads(shop_info.decode())
        shop_id = re.search(r'(\d+)\.(taobao\.com)', shop_url).group(1)

        return shop_info, shop_id, keyword

    @staticmethod
    async def _add_shop_info(redis_client, shop_info):
        if shop_info:
            await redis_client.sadd(REDIS_KEY_DUMMY_SHOP_URLS, shop_info)

    @staticmethod
    async def _insert_goods_list(mongo_client, goods_list):
        if goods_list:
            await mongo_client[MONGO_DB][MONGO_COLLECTION_GOODS].insert_many(goods_list)

    async def _report_progress(self):
        while True:
            pipeline = self.redis_client.pipeline()
            pipeline.scard(REDIS_KEY_SHOP_URLS)
            pipeline.scard(REDIS_KEY_DUMMY_SHOP_URLS)
            total, left = await pipeline.execute()
            finished = total - left
            percentage = 100 * finished / total

            print('{0}  {1} / {2} = {3:.2f}%  {0}'.format('=' * 30, finished, total, percentage))

            if not left:
                break

            await asyncio.sleep(10)


if __name__ == '__main__':
    dispatcher = Dispatcher(workers=20, shops_per_proxy=10)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(dispatcher.start())
