# -*- coding: utf-8 -*-
# !/usr/bin/env python

from proxy_swift import *

from datetime import datetime
import json
import logging
import logging.handlers
import multiprocessing
import os
import re
import signal
import time
import urllib.parse

import fire

from pyvirtualdisplay import Display

import redis

from selenium import webdriver
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait


def init_logger(name, task_id, log_dir):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    log_dir = os.path.expanduser(log_dir)
    if not os.path.exists(log_dir) or not os.path.isdir(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_dir, f'{task_id}.log'), when='H', encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(name)s - %(lineno)d - %(levelname)s - %(message)s')
    )

    logger.addHandler(file_handler)

    return logger


class GetShopItem(object):
    def __init__(self, task_id, max_pages, proxy, redis_url, log_dir):
        self.task_id = task_id
        self.max_pages = max_pages
        self.proxy = proxy

        self.key_shop = 'shop_urls'
        self.key_item = 'goods_grab:start_urls'
        self.key_goods = 'goods'
        self.redis = redis.from_url(redis_url)

        self.logger = init_logger(name=self.__class__.__name__, task_id=self.task_id, log_dir=log_dir)

        self.display = Display(visible=0, size=(800, 600))
        self.browser = self.open_browser()

    def open_browser(self, default='Chrome'):
        self.logger.info('browser: launching')

        self.display.start()

        if default == 'Chrome':
            chrome_options = webdriver.ChromeOptions()
            chrome_options.add_argument('-incognito')
            # chrome_options.add_argument('--headless')
            # chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('window-size=360,640')
            chrome_options.add_experimental_option('prefs', {'profile.managed_default_content_settings.images': 2})

            if self.proxy:
                chrome_options.add_argument('--proxy-server={}'.format(self.proxy))

            browser_kwargs = {'chrome_options': chrome_options}
            browser_class = webdriver.Chrome
        elif default == 'PhantomJS':
            desired_capabilities = dict(DesiredCapabilities.PHANTOMJS)
            desired_capabilities['phantomjs.page.settings.userAgent'] = (
                'Mozilla/5.0 (iPhone; CPU iPhone OS 9_1 like Mac OS X) '
                'AppleWebKit/601.1.46 (KHTML, like Gecko) Version/9.0 Mobile/13B143 Safari/601.1'
            )

            browser_class = webdriver.PhantomJS

            service_args = ['--load-images=no']
            if self.proxy:
                service_args.append('--proxy={}'.format(self.proxy))

            browser_kwargs = {'desired_capabilities': desired_capabilities, 'service_args': service_args}
        else:
            raise NotImplementedError

        while True:
            try:
                browser = browser_class(**browser_kwargs)
            except Exception as e:
                self.logger.warning('browser: {}'.format(e))
            else:
                self.logger.info('browser: ' + default)
                return browser

    def close_browser(self):
        self.browser.close()
        self.browser.service.process.send_signal(signal.SIGTERM)
        self.browser.quit()
        self.display.stop()

    def find_taobao_goods(self, keyword):
        try:
            for a in self.browser.find_elements_by_xpath('//ul[@class="goods-list-items"]//a'):
                goods_url = a.get_attribute('href')
                goods_id = urllib.parse.parse_qs(urllib.parse.urlparse(goods_url).query)['id'][0]
                goods_url = 'https://item.taobao.com/item.htm?id={}'.format(goods_id)

                left = a.find_element_by_xpath('child::div[@class="left"]')
                right = a.find_element_by_xpath('child::div[@class="right"]')

                goods_info = {
                    'id': goods_id,
                    'url': goods_url,
                    'from': '淘宝',
                    'keyword': urllib.parse.unquote(keyword),
                    'search': self.browser.current_url,
                    'modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                    'image': left.find_element_by_xpath('child::img').get_attribute('src'),
                    'title': right.find_element_by_xpath('child::h3[@class="d-title"]').text,
                    'price_highlight': right.find_element_by_xpath('child::p[@class="d-price"]/em[@class="h"]').text,
                    'price_del': right.find_element_by_xpath('child::p[@class="d-price"]/del').text,
                    'sales_volume': right.find_element_by_xpath('child::p[@class="info"]/span[@class="d-num"]/em').text
                }

                self.logger.info('goods: {}'.format(goods_info))
                self.redis.sadd(self.key_item, goods_url)
                self.redis.hset(
                    '{}@{}'.format(self.key_goods, goods_info['modified'].split()[0]),
                    goods_id, json.dumps(obj=goods_info, ensure_ascii=False, sort_keys=True)
                )
        except Exception as e:
            self.logger.warning(e)

    def find_tmall_goods(self, keyword):
        try:
            for a in self.browser.find_elements_by_xpath('//div[@class="tile_box"]//a[@class="tile_item"]'):
                goods_url = a.get_attribute('href')
                goods_id = urllib.parse.parse_qs(urllib.parse.urlparse(goods_url).query)['id'][0]
                goods_url = 'https://detail.m.tmall.com/item.htm?id={}'.format(goods_id)

                goods_info = {
                    'id': goods_id,
                    'url': goods_url,
                    'from': '天猫',
                    'keyword': urllib.parse.unquote(keyword),
                    'search': self.browser.current_url,
                    'modified': datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
                    'image': a.find_element_by_xpath('descendant::img[@class="ti_img"]').get_attribute('src'),
                    'title': a.find_element_by_xpath('descendant::div[@class="tii_title"]/h3').text,
                    'price_highlight': a.find_element_by_xpath('descendant::div[@class="tii_price"]').text.split()[0],
                    'price_del': '',
                    'sales_volume': a.find_element_by_xpath(
                        'descendant::div[@class="tii_price"]/span[@class="tii_sold"]').text
                }
                goods_info['price_highlight'] = re.sub(r'.*?(\d+).*', r'\g<1>', goods_info['price_highlight'])
                goods_info['sales_volume'] = re.sub(r'.*?(\d+).*', r'\g<1>', goods_info['sales_volume'])

                self.logger.info('goods: {}'.format(goods_info))
                self.redis.sadd(self.key_item, goods_url)
                self.redis.hset(
                    '{}@{}'.format(self.key_goods, goods_info['modified'].split()[0]),
                    goods_id, json.dumps(obj=goods_info, ensure_ascii=False, sort_keys=True)
                )
        except Exception as e:
            self.logger.warning(e)

    def traversal_tabao_shop(self, keyword):
        pages = 0

        try:
            WebDriverWait(self.browser, 15).until(
                expected_conditions.presence_of_element_located((By.CSS_SELECTOR, 'h3.d-title'))
            )
        except Exception as e:
            _ = e
        else:
            self.find_taobao_goods(keyword)

            # 下一页
            xpath = (
                '//div[@id="gl-pagenav"]//'
                'a[contains(@class, "c-p-next") and not(contains(@class, "c-btn-off"))]'
            )
            while True:
                try:
                    self.browser.find_element_by_xpath(xpath).click()
                    self.browser.implicitly_wait(3)
                    pages += 1
                except Exception as e:
                    _ = e
                    break
                else:
                    self.find_taobao_goods(keyword)

        return pages

    def traversal_tmall_shop(self, p2, keyword):
        pages = 0

        request_url = f'{p2.scheme}://{p2.hostname}/shop/shop_auction_search.htm?q={keyword}'
        self.logger.info('shop: ' + request_url)

        self.browser.get(request_url)
        pages += 1

        try:
            WebDriverWait(self.browser, 15).until(
                expected_conditions.presence_of_element_located((By.CSS_SELECTOR, '.tii_title h3'))
            )
        except Exception as e:
            _ = e
        else:
            # 上拉加载
            xpath = '//section[@class="state" and contains(text(), "已经看到最后啦~")]'
            for _ in range(100):
                try:
                    self.browser.find_element_by_xpath(xpath)
                except Exception as e:
                    _ = e
                    self.browser.execute_script('document.body.scrollTop += 500')
                    self.browser.implicitly_wait(3)
                    pages += 1
                else:
                    break

            self.find_tmall_goods(keyword)

        return pages

    def run(self):
        self.logger.info('-' * 100)

        pages = 0

        while True:
            if pages > 0 and pages % self.max_pages == 0:
                break

            shop_info = self.redis.spop(self.key_shop)
            if not shop_info:
                break

            shop_url, keyword = json.loads(shop_info)
            keyword = urllib.parse.quote(keyword)
            shop_url = re.sub(r'(\d+)\.(taobao\.com)', r'\g<1>.m.\g<2>', shop_url)

            request_url = '{}/#list?q={}'.format(shop_url, keyword)
            self.logger.info('shop: ' + request_url)

            # # 测试天猫
            # keyword = 'AHC'
            # request_url = 'https://shop114223508.m.taobao.com/#list?q=AHC'
            # 测试淘宝
            # keyword = '%E9%9F%A9%E5%9B%BD'
            # request_url = 'https://shop34135992.m.taobao.com/#list?q=%E9%9F%A9%E5%9B%BD'

            self.browser.get(request_url)

            response_url = self.browser.current_url
            pages += 1

            p1 = urllib.parse.urlparse(request_url)
            p2 = urllib.parse.urlparse(response_url)

            if p1.hostname.endswith('taobao.com') and p2.hostname.endswith('tmall.com'):
                # 天猫
                pages += self.traversal_tmall_shop(p2=p2, keyword=keyword)
            else:
                # 淘宝
                pages += self.traversal_tabao_shop(keyword=keyword)

        self.close_browser()
        self.logger.info('-' * 100)


class TaskDispatcher(object):
    def __init__(
        self, max_pages, enable_proxy=True, log_dir='~/data/logs/shop_items/',
        redis_url=os.environ.get('REDIS_URL') or 'redis://localhost:6379/1'
    ):
        self.max_pages = max_pages
        self.enable_proxy = enable_proxy
        self.redis_url = redis_url
        self.log_dir = log_dir

        self.proxy_pool = ProxyPool()
        self.proxy_swift = ProxySwift()

        self.logger = init_logger(name=self.__class__.__name__, task_id=0, log_dir=log_dir)

    def reset_proxy(self, proxy_id):
        self.logger.info('proxy.{}: launching'.format(proxy_id))

        self.proxy_pool.change_ip('http://115.237.237.167:10003')
        self.proxy_swift.changes_ip(proxy_id)

        proxy = 'http://{ip}:{port}'.format(**self.proxy_swift.get_ip(proxy_id)[0])
        self.logger.info('proxy.{}: {}'.format(proxy_id, proxy))

        return proxy

    def task(self, task_id, proxy):
        get_shop_items = GetShopItem(
            task_id=task_id, max_pages=self.max_pages, proxy=proxy, redis_url=self.redis_url, log_dir=self.log_dir
        )
        get_shop_items.run()

    def run(self):
        tasks = {i: None for i in (range(27, 33) if self.enable_proxy else range(27, 28))}

        while True:
            for task_id in tasks:
                if not tasks[task_id] or not tasks[task_id].is_alive():
                    proxy = self.reset_proxy(proxy_id=task_id) if self.enable_proxy else None

                    process = multiprocessing.Process(name=task_id, target=self.task, args=(task_id, proxy))
                    process.start()

                    tasks[task_id] = process

            time.sleep(0.1)


if __name__ == '__main__':
    """
    Usage: shop_items.py MAX_PAGES [ENABLE_PROXY] [REDIS_URL] [LOG_DIR]
           shop_items.py --max-pages MAX_PAGES [--enable-proxy ENABLE_PROXY] [--redis-url REDIS_URL] [--log-dir LOG_DIR]

    Example: shop_items.py run --max-pages=25
             screen -dmS get_shop_item shop_items.py run --max-pages=25
    """

    fire.Fire(TaskDispatcher)