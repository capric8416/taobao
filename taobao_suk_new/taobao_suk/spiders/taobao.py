# -*- coding: utf-8 -*-
import scrapy
import itertools
import furl
import re
import os
import redis
from datetime import datetime
import lxml
import json
from taobao_suk import items


class TaobaoSpider(scrapy.Spider):
    name = "taobao"
    allowed_domains = ["taobao.com", "tmall.hk", "tmall.com"]
    start_urls = ['http://taobao.com/']

    redis_url = os.environ.get('REDIS_URL')
    pool = redis.ConnectionPool.from_url(redis_url)
    rds = redis.StrictRedis(connection_pool=pool)

    def start_requests(self):

        # 重跑所有链接

        base_url = 'https://shopsearch.taobao.com/search?app=shopsearch&q={}'
        # world_list = ['papa recipe']
        world_list = ['papa recipe', 'LEADERS', 'CNP',
                      'JAYJUN', 'SNP', 'MEDIHEAL', 'JM Solution',
                      'It’s Skin', 'The Saem', 'Innisfree', 'Tony Moly',
                      'AHC', 'Shangpree']

        addrs_url = '&loc={}'
        # addrs_list =['']
        addrs_list = ["北京", "上海", "广州", "深圳", "杭州", "海外", "江浙沪", "珠三角", "京津冀", "东三省", "港澳台",
        "江浙沪皖", "长沙", "长春", "成都", "重庆", "大连", "东莞", "佛山", "福州", "贵阳", "合肥",
        "金华", "济南", "嘉兴", "昆明", "宁波", "南昌", "南京", "青岛", "泉州", "沈阳", "苏州", "天津",
        "温州", "无锡", "武汉", "西安", "厦门", "郑州", "中山", "石家庄", "哈尔滨", "安徽", "福建",
        "甘肃", "广东", "广西", "贵州", "海南", "河北", "河南", "湖北", "湖南", "江苏", "江西", "吉林",
        "辽宁", "宁夏", "青海", "山东", "山西", "陕西", "云南", "四川", "西藏", "新疆", "浙江", "澳门",
        "香港", "台湾", "内蒙古", "黑龙江", ""]

        shop_type_url = '&isb={}'
        shop_type = ['0']

        xing_ji_url = '&ratesum={}'
        xing_ji = ['jin', 'huang', 'zhuan', 'xin', '']

        haoping_url = '&goodrate={}00%2C'
        # haoping_list = ['97']

        haoping_list = ['97', '100', '99', '98', '96']

        tianmao_url = 'https://shopsearch.taobao.com/search?app=shopsearch&q={}&ie=utf8&isb=1'

        for w in world_list:
            yield scrapy.Request(tianmao_url.format(w), callback=self.parse, meta={'word': w, 'shop_type': 1})

        quanqiugou_url = 'https://shopsearch.taobao.com/search?app=shopsearch&q={}&ie=utf8&shop_type=2&isb=&ratesum='

        for w in world_list:
            yield scrapy.Request(quanqiugou_url.format(w), callback=self.parse, meta={'word': w, 'shop_type': 0})

        for w in itertools.product(world_list, addrs_list, shop_type, xing_ji):
            url_ = base_url + addrs_url + shop_type_url + xing_ji_url
            url = url_.format(*w)
            yield scrapy.Request(url, callback=self.parse, meta={'word': w[0], 'shop_type': 0})

    def parse(self, response):
        # url_list = re.findall(r'shopUrl":"(//.*?.taobao.com)"', response.text)

        relust_list = re.findall(r'g_page_config = ({.*?});', response.text)
        data_dict = json.loads(relust_list[0].strip())
        shopItems = data_dict['mods']['shoplist'].get('data', {'shopItems': []})['shopItems']
        for item in shopItems:
            shop_info = dict()
            shop_info['shop_name'] = item['rawTitle']
            shop_info['address'] = item['provcity']
            shop_info['zhang_gui'] = item['nick']
            shop_info['shop_id'] = item['nid']
            shop_info['shop_deng_ji'] = item['shopIcon']['iconClass']
            shop_info['shop_type'] = '天猫' if response.meta['shop_type'] else '淘宝'
            shop_info['url'] = 'https:{}'.format(item['shopUrl'])
            shop_info['modified'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

            self.rds.sadd('shop_urls', json.dumps(('https:{}'.format(item['shopUrl']), response.meta['word'])))
            yield items.TaobaoSukItem(detail={'shop_info': shop_info})

        # 翻页
        furl_obj = furl.furl(response.url)
        if len(shopItems) == 20:
            s = furl_obj.args.get('s', None)
            if s:
                s = int(s) + 20
                furl_obj.args['s'] = s
            else:
                furl_obj.args['s'] = 20
            next_url = furl_obj.url
            yield scrapy.Request(next_url, callback=self.parse, meta=response.meta)