# -*- coding: utf-8 -*-
# !/usr/bin/env python

import hashlib
import inspect
import json
import logging
import multiprocessing
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timedelta

import fire
import pymongo
import redis
from common.gracefully_exit import GracefullyExit
from common.logger import get_logger
from proxy_swift import *
from pychrome import Launcher, Sniffer
from pyquery import PyQuery
from pyvirtualdisplay import Display

PREFIX = '' if '--debug' not in sys.argv else hashlib.md5('debug'.encode()).hexdigest() + '_'

STEP = 100

TAOBAO_ERROR_URL = 'err.taobao.com'

DATE_TIME_FORMAT = '%Y-%m-%d %H:%M:%S.%f'

REDIS_KEY_USER_AGENTS = PREFIX + 'user_agents'

REDIS_KEY_SHOP_URLS = PREFIX + 'shop_urls'
REDIS_KEY_DUMMY_SHOP_URLS = PREFIX + 'dummy_shop_urls'
REDIS_KEY_GOODS_URLS = PREFIX + 'goods_grab:start_urls'
REDIS_KEY_TASK_RUNNING = PREFIX + 'running_task_goods_list'

MONGO_DB = PREFIX + 'test'
MONGO_COLLECTION_GOODS = 'goods_list'
MONGO_COLLECTION_GOODS_MAIN = 'goods_list_main'
MONGO_COLLECTION_GOODS_LOG = 'goods_list_logs'


class GoodsSniffer(Sniffer):
    """
    在店铺内搜索指定关键字，嗅探并存储找到的商品信息
    """

    def __init__(self, port, logger, redis_client, mongo_client, search_info):
        """
        初始化
        :param port: int, chrome远程调试端口
        :param logger: object, 日志记录器
        :param redis_client: StrictRedis object, redis客户端
        :param mongo_client: MongoClient object, mongo客户端
        :param search_info: list, 本次要爬的店铺信息
        """

        super(GoodsSniffer, self).__init__(remote_debugging_url='http://localhost:{}'.format(port))

        self.logger = logger

        self.redis_client = redis_client
        self.mongo_client = mongo_client

        self.pages = 0
        self.content = []
        self.visited = False

        self.search_info = search_info
        self.search_url = self.search_keyword = ''

    def visit(self, timeout=300):
        """
        店铺访问循环
        :param timeout: int, 最长超时秒数
        :return: int, 本次访问了多少页面
        """

        self.logger.info(f'[*] {self.__class__.__name__}.{inspect.currentframe().f_code.co_name}')

        # 截止时间
        end = datetime.now() + timedelta(seconds=timeout)

        # 打开搜索页面
        if not self.search():
            return self.pages

        # 如果被重定向到访问受限页面，则返回
        if urllib.parse.urlparse(self.tab.url).hostname == TAOBAO_ERROR_URL:
            self.redis_client.sadd(REDIS_KEY_DUMMY_SHOP_URLS, self.search_info)
            self.logger.error(f'{self.__class__.__name__}.{inspect.currentframe().f_code.co_name}: 访问受限')
            return self.pages

        # 等待店铺访问完毕或者超时
        while datetime.now() < end:
            if self.visited:
                break
            else:
                time.sleep(0.3)

        return self.pages

    def search(self):
        """
        打开搜索页面
        :return:
        """

        self.logger.info(f'[*] {self.__class__.__name__}.{inspect.currentframe().f_code.co_name}')

        # 打开链接
        self._build()
        self._search()

        # 淘宝，天猫
        resp_url = urllib.parse.urlparse(self.tab.url)
        if not resp_url.hostname.endswith('tmall.com'):
            selector = '.js-nav-des:not(:empty)'
        else:
            keyword = urllib.parse.quote(self.search_keyword)
            self.search_url = f'{resp_url.scheme}://{resp_url.hostname}/shop/shop_auction_search.htm?q={keyword}'

            self._search()
            selector = '.searchbar'

        status = False
        for _ in range(4):
            status = self.tab.wait(selector=selector)
            if status:
                break
            self.tab.Page.reload()
            self.pages += 1

        return status

    def _build(self):
        """
        构建链接
        :return:
        """

        self.logger.info(f'[*] {self.__class__.__name__}.{inspect.currentframe().f_code.co_name}')

        search_url, keyword = json.loads(self.search_info)
        search_url = re.sub(r'(\d+)\.(taobao\.com)', r'\g<1>.m.\g<2>', search_url)
        search_url = '{}/#list?q={}'.format(search_url, urllib.parse.quote(keyword))

        self.search_url = search_url
        self.search_keyword = keyword

    def _search(self):
        """
        打开页面
        :return:
        """

        self.logger.info(f'[*] {self.__class__.__name__}.{inspect.currentframe().f_code.co_name} {self.search_url}')

        for _ in range(4):
            self.open_url(url=self.search_url, selector='//title')
            self.pages += 1
            if self.tab.wait(
                    expression=lambda: urllib.parse.urlparse(self.tab.url).hostname not in (None, 'localhost')):
                break

    def network_response_received(self, **kwargs):
        """
        网络请求体返回事件
        :param kwargs: dict, response data
        :return:
        """

        _type = kwargs['type']
        _url = kwargs['response']['url']
        _host = urllib.parse.urlparse(_url).hostname

        # 跳过不需要的网络请求
        if not any([_type == 'Script' and 'com.taobao.search.api.getShopItemList' in _url,
                    _type == 'Script' and 'shop_auction_search.do' in _url]):
            return

        # 获取网络请求体的内容
        ret = self.tab.Network.getResponseBody(requestId=kwargs['requestId'])
        data = json.loads(ret['body'].partition('(')[-1].rpartition(')')[0])

        # 获取商品数，如果为空或者为0,则返回
        if _host.endswith('.taobao.com'):
            data = data['data']
            found = 'totalResults' in data
            total = int(data.get('totalResults', '0'))
        else:
            found = 'total_results' in data
            total = int(data.get('total_results', '0'))

        if not data:
            return

        if total < 1:
            if not data or not found:
                return

            self.logger.error(f'{self.__class__.__name__}.{inspect.currentframe().f_code.co_name}: 0个宝贝')
            self.extract_data(host=_host)
            return

        # 记录收到的数据
        self.content.append(data)

        # 翻页，如果没有下一面，执行数据解析
        if self.next_page(host=_host):
            self.extract_data(host=_host)

    def next_page(self, host):
        """
        翻页并判断是否有下一页
        :param host: str, 链接域名
        :return: bool, 是否有下一页
        """

        self.logger.info(f'[*] {self.__class__.__name__}.{inspect.currentframe().f_code.co_name}')

        self.pages += 1
        if host.endswith('.taobao.com'):
            self.tab.wait(timeout=3)
            return not self.tab.click('div#gl-pagenav a.c-p-next:not(.c-btn-off)', limit_one=True)
        else:
            self.tab.Runtime.evaluate(expression='window.scrollBy(0, window.innerHeight)')
            return self.tab.wait(selector='//section[@class="state" and contains(text(), "已经看到最后啦~")]', timeout=3)

    def extract_data(self, host):
        """
        提取商品信息
        :param host: str, 链接域名
        :return:
        """

        if not self.content:
            self.logger.info(f'[*] {self.__class__.__name__}.{inspect.currentframe().f_code.co_name}: 0.0.0')
            self.visited = True
            return

        now = datetime.now()
        today = now.today()
        goods_list = []
        total_1 = total_2 = total_3 = 0

        try:
            if host.endswith('.taobao.com'):
                self._extract_taobao(now=now, today=today, goods_list=goods_list)
                total_1 = PyQuery(self.tab.query(selector=".js-nav-des", limit=1)).text()
            else:
                self._extract_tmall(now=now, today=today, goods_list=goods_list)
                total_1 = None
        except Exception as e:
            self.logger.exception(f'{self.__class__.__name__}.{inspect.currentframe().f_code.co_name}: {e}')

        if goods_list:
            total_2 = goods_list[0]['search_results']
            total_3 = len(goods_list)
            self.mongo_client[MONGO_DB][MONGO_COLLECTION_GOODS].insert_many(goods_list)

        self.logger.info(
            f'{self.__class__.__name__}.{inspect.currentframe().f_code.co_name}: {total_1}.{total_2}.{total_3}')

        self.visited = True

    def _extract_taobao(self, now, today, goods_list):
        """
        提取淘宝商品信息
        :param now: datetime, 当前时间
        :param today: date, 当前日期
        :param goods_list: list, 待填充的商品列表
        :return:
        """

        self.logger.info(f'[*] {self.__class__.__name__}.{inspect.currentframe().f_code.co_name}')

        for page in self.content:
            for item in page['itemsArray']:
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
                self.logger.info('goods: {}'.format(goods_info))

    def _extract_tmall(self, now, today, goods_list):
        """
        提取天猫商品信息
        :param now: datetime, 当前时间
        :param today: date, 当前日期
        :param goods_list: list, 待填充的商品列表
        :return:
        """

        self.logger.info(f'[*] {self.__class__.__name__}.{inspect.currentframe().f_code.co_name}')

        for page in self.content:
            for item in page['items']:
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
                self.logger.info('goods: {}'.format(goods_info))


class GoodsFetcher(object):
    """
    管理代理，嗅探器
    """

    def __init__(self, port, task_id, max_pages, proxy_client, redis_client, mongo_url, log_dir):
        """
        初始化
        :param port: int, chrome远程调试端口
        :param task_id: int, 任务标识
        :param max_pages: int, 代理的生存周期
        :param proxy_client: ProxySwift object, 代理客户端
        :param redis_client: StrictRedis object, redis客户端
        :param mongo_url: str, mongo连接url
        :param log_dir: str, 日志路径
        """

        self.pages = 0

        self.port = port
        self.task_id = task_id
        self.max_pages = max_pages

        self.proxy_client = proxy_client
        self.redis_client = redis_client
        self.mongo_client = pymongo.MongoClient(mongo_url)

        self.mongo_client[MONGO_DB][MONGO_COLLECTION_GOODS].create_index([
            ('id', pymongo.ASCENDING), ('keyword', pymongo.ASCENDING),
            ('date', pymongo.DESCENDING), ('shop_id', pymongo.ASCENDING)
        ])
        self.mongo_client[MONGO_DB][MONGO_COLLECTION_GOODS_LOG].create_index([('date', pymongo.DESCENDING)])

        self.logger = get_logger(name=self.__class__.__name__, task_id=task_id, log_dir=log_dir, log_level=logging.INFO)

    def run(self):
        """
        任务循环
        :return:
        """

        self.logger.info(f'[*] {self.__class__.__name__}.{inspect.currentframe().f_code.co_name}')

        self.logger.info('>' * 100)

        if self.redis_client.exists(REDIS_KEY_DUMMY_SHOP_URLS):
            self.redis_client.hsetnx(REDIS_KEY_TASK_RUNNING, 'start', datetime.now().strftime(DATE_TIME_FORMAT))

        proxy = self._proxy()

        while True:
            if self.pages >= self.max_pages:
                break

            self._report()

            shop_info = self.redis_client.spop(REDIS_KEY_DUMMY_SHOP_URLS)
            if not shop_info:
                self._stop()
                break

            self._sniffer(proxy=proxy, shop_info=shop_info)

        self.logger.info('<' * 100)

    def _proxy(self):
        """
        切换代理
        :return: dict, 代理信息
        """

        self.logger.info(f'[*] {self.__class__.__name__}.{inspect.currentframe().f_code.co_name}')

        proxy = None
        if self.proxy_client:
            proxy = self.proxy_client.change_ip(self.task_id)
            self.logger.info('proxy.{server_id}.{pool_id}.{id}: http://{ip}:{port}'.format(**proxy))
        return proxy

    def _sniffer(self, proxy, shop_info):
        """
        开始嗅探店铺，并更新访问的页面记数
        :param shop_info: list, 待爬店铺信息
        :return:
        """

        self.logger.info(f'[*] {self.__class__.__name__}.{inspect.currentframe().f_code.co_name}')

        # 构造嗅探器
        sniffer = GoodsSniffer(port=self.port, logger=self.logger, search_info=shop_info,
                               redis_client=self.redis_client, mongo_client=self.mongo_client)

        if not self.pages:
            # 执行批量操作: 清空数据，禁用图片和样式，切换代理等
            actions = {'browsing_data': True, 'image': False, 'stylesheet': False}
            if proxy:
                actions['proxy'] = ['regular', 'http', proxy['ip'], proxy['port']]
            sniffer.batch_actions(**actions)

            # 设置UA
            user_agent = self.redis_client.spop(REDIS_KEY_USER_AGENTS)
            if user_agent:
                sniffer.tab.Network.setUserAgentOverride(userAgent=user_agent.decode('utf-8'))

        # 开始访问并更新页面计数
        self.pages += sniffer.visit()

    def _report(self):
        pipeline = self.redis_client.pipeline()
        pipeline.scard(REDIS_KEY_SHOP_URLS)
        pipeline.scard(REDIS_KEY_DUMMY_SHOP_URLS)
        total, left = pipeline.execute()
        finished = total - left
        percentage = 100 * finished / total

        self.logger.info('{0}  {1} / {2} = {3:.2f}%  {0}'.format('=' * 30, finished, total, percentage))

    def _stop(self):
        """
        停止时统计当天的日志
        :return:
        """

        self.logger.info(f'[*] {self.__class__.__name__}.{inspect.currentframe().f_code.co_name}')

        start = (self.redis_client.hget(REDIS_KEY_TASK_RUNNING, 'start') or b'').decode()
        if start and self.redis_client.delete(REDIS_KEY_TASK_RUNNING) > 0:
            start = datetime.strptime(start, DATE_TIME_FORMAT)
            end = datetime.now()
            today = datetime.fromordinal(end.today().toordinal())
            count = self.mongo_client[MONGO_DB][MONGO_COLLECTION_GOODS].find({'date': today}).count()

            self.dump_main_goods(date=today)

            self.mongo_client[MONGO_DB][MONGO_COLLECTION_GOODS_LOG].insert({
                'start': start, 'end': end, 'date': today, 'count': count
            })
            self.logger.info('{0} {1} -> {2} = {3} {0}'.format('=' * 40, start, end, count))

    def dump_main_goods(self, date=datetime.fromordinal(datetime.today().toordinal()), limit=3000):
        """
        按date取所有的关键字，按销量倒序取出limit条记录，将其转储到一个新的集合
        :param date: date, 指定dump哪一天的数据
        :param limit: int, 每个品牌下最多最多取多少条记录
        :return:
        """

        self.logger.info(f'[*] {self.__class__.__name__}.{inspect.currentframe().f_code.co_name}')

        self.logger.info('>' * 100)

        self.mongo_client[MONGO_DB][MONGO_COLLECTION_GOODS_MAIN].create_index([
            ('id', pymongo.ASCENDING), ('shop_id', pymongo.ASCENDING), ('keyword', pymongo.ASCENDING)
        ])

        for keyword in self.mongo_client[MONGO_DB][MONGO_COLLECTION_GOODS].find(
                {'date': {'$gte': date}}).distinct('keyword'):
            self.logger.info('{0} {1}'.format(datetime.now(), keyword))

            goods_list = list(self.mongo_client[MONGO_DB][MONGO_COLLECTION_GOODS].find(
                {'date': date, 'keyword': keyword}).sort([('sales_volume', pymongo.DESCENDING)]).limit(limit=limit))

            for i in range(0, len(goods_list), 100):
                items = goods_list[i: i + 100]
                self.redis_client.sadd(REDIS_KEY_GOODS_URLS, *[item['url'] for item in items])
                self.mongo_client[MONGO_DB][MONGO_COLLECTION_GOODS_MAIN].delete_many({
                    'id': {'$in': [item['id'] for item in items]}
                })
                self.mongo_client[MONGO_DB][MONGO_COLLECTION_GOODS_MAIN].insert_many(items)

        self.logger.info('<' * 100)


class TaskDispatcher(object):
    """
    调度抓取任务
    """

    def __init__(
            self, max_pages, enable_proxy=True,
            enable_xvfb=True, log_dir='~/data/logs/taobao/goods_list/',
            redis_url=os.environ.get('REDIS_URL') or 'redis://localhost:6379/',
            mongo_url=os.environ.get('MONGO_URL') or 'mongodb://localhost:27017/',
            chrome_extension_path='~/data/taobao/get_goods/dynamic_proxy',
            chrome_user_data_path='~/data/taobao/get_goods/chrome_61_conf.tar.xz'):
        """
        初始化
        :param max_pages: int, 代理的生存周期(可以爬几个页面)
        :param enable_proxy: bool, 是否启用代理
        :param enable_xvfb: bool, 是否启用xvfb
        :param log_dir: str, 日志路径
        :param redis_url: str, redis连接url
        :param mongo_url: str, mongo连接url
        :param chrome_extension_path: str, 要加载的chrome插件路径
        :param chrome_user_data_path: str, 要加载的chrome默认配置路径
        """

        self.max_pages = max_pages
        self.enable_proxy = enable_proxy
        self.enable_xvfb = enable_xvfb
        self.log_dir = log_dir

        self.chrome_extension_path = chrome_extension_path
        self.chrome_user_data_path = chrome_user_data_path

        self.gracefully_exit = GracefullyExit()

        self.redis_client = redis.from_url(redis_url)
        self.mongo_client = pymongo.MongoClient(mongo_url)
        self.mongo_url = mongo_url

        self.logger = get_logger(name=self.__class__.__name__, task_id=0, log_dir=log_dir, log_level=logging.INFO)

        if self.enable_xvfb:
            self.display = Display(visible=0, size=(800, 600))
            self.display.start()

        self.tasks = {0: None}
        self.proxy_client = None
        if self.enable_proxy:
            self.proxy_client = ProxySwift(secret_key='Kg6t55fc39FQRJuh92BwZBMXyK3sWFkJ', partner_id='2017072514450843')
            self.tasks = {item['id']: None for item in self.proxy_client.get_ip(pool_id=1)}

        self.chrome = Launcher(
            headless=False, incognito=False, count=len(self.tasks),
            user_data_path=chrome_user_data_path, extension_path=chrome_extension_path)

    def task(self, task_id):
        """
        任务进程
        :param task_id: int, 任务标识
        :return:
        """

        self.logger.info(f'[*] {self.__class__.__name__}.{inspect.currentframe().f_code.co_name}')

        port = 9222 + task_id - sorted(self.tasks.keys())[0]
        fetcher = GoodsFetcher(
            port=port, task_id=task_id, max_pages=self.max_pages, proxy_client=self.proxy_client,
            redis_client=self.redis_client, mongo_url=self.mongo_url, log_dir=self.log_dir)
        fetcher.run()

    def run(self):
        """
        任务调度循环
        :return:
        """

        self.logger.info(f'[*] {self.__class__.__name__}.{inspect.currentframe().f_code.co_name}')

        # 如果当天已经跑过了，则退出
        if self.mongo_client[MONGO_DB][MONGO_COLLECTION_GOODS_MAIN].find_one(
                {'date': datetime.fromordinal(datetime.today().toordinal())}):
            return

        # 加载所有的UA
        with open('user_agents.txt', encoding='utf-8') as fp:
            user_agents = [line.strip() for line in fp]

        # 如果待进行的任务队列为空，则生成一份
        if not self.redis_client.exists(REDIS_KEY_DUMMY_SHOP_URLS):
            values = list(self.redis_client.smembers(REDIS_KEY_SHOP_URLS))
            for i in range(0, len(values), STEP):
                self.redis_client.sadd(REDIS_KEY_DUMMY_SHOP_URLS, *values[i: i + STEP])

        # 如果待进行的任务队列为空，则退出
        if not self.redis_client.exists(REDIS_KEY_DUMMY_SHOP_URLS):
            return

        # 启动浏览器
        self.chrome.start()

        while True:
            # 如果剩余的UA只有当前并发数的一半，则将所有的UA填充进去
            if self.redis_client.scard(REDIS_KEY_USER_AGENTS) <= len(self.tasks) / 2:
                self.redis_client.sadd(REDIS_KEY_USER_AGENTS, *user_agents)

            for task_id in self.tasks:
                if not self.tasks[task_id] or not self.tasks[task_id].is_alive():
                    process = multiprocessing.Process(name=task_id, target=self.task, args=(task_id,))
                    process.start()
                    self.tasks[task_id] = process

            # 捕获到终止信号，清理任务进程，并退出
            if self.gracefully_exit.received:
                for task_id in self.tasks:
                    if self.tasks[task_id].is_alive():
                        self.tasks[task_id].terminate()
                break

            # 如果任务运行标识为空并且任务队列为空，则退出
            if all([not self.redis_client.exists(REDIS_KEY_TASK_RUNNING),
                    not self.redis_client.exists(REDIS_KEY_DUMMY_SHOP_URLS)]):
                break

            # 下次循环前，等待若干秒
            time.sleep(0.3)

        # 循环终止，执行收尾工作
        self.stop()

    def stop(self):
        """
        等待若干秒，关闭浏览器器，关闭xvfb，转储商品数据
        :return:
        """

        self.logger.info(f'[*] {self.__class__.__name__}.{inspect.currentframe().f_code.co_name}')

        time.sleep(300)

        self.chrome.stop()
        if self.enable_xvfb:
            self.display.stop()


if __name__ == '__main__':
    """
    Help: get_goods.py
    
    Example: get_goods.py run --max-pages=20 --enable-proxy=False --enable-xvfb=False
    
    Test data:
    sadd('shop_urls', '["https://shop34029963.taobao.com", "slfkslfjkwlekrsdkfs"]')   # 淘宝: 0页
    sadd('shop_urls', '["https://shop34029963.taobao.com", "The Saem"]')              # 淘宝: 1页
    sadd('shop_urls', '["https://shop34135992.taobao.com", "韩国"]')                   # 淘宝: 5页
    sadd('shop_urls', '["https://shop117058577.taobao.com", "skflsfksldkflwekrjl"]')  # 天猫: 0页
    sadd('shop_urls', '["https://shop117058577.taobao.com", "AHC"]')                  # 天猫: 1页
    sadd('shop_urls', '["https://shop117058577.taobao.com", "A"]')                    # 天猫: 12页
    """

    fire.Fire(TaskDispatcher)
