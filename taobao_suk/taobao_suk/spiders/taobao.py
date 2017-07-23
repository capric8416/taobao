# -*- coding: utf-8 -*-
import scrapy
import itertools
import furl
import re
import lxml
from taobao_suk import items


class TaobaoSpider(scrapy.Spider):
    name = "taobao"
    allowed_domains = ["taobao.com", "tmall.hk", "tmall.com"]
    start_urls = ['http://taobao.com/']

    def start_requests(self):

        # 重跑所有链接


        base_url = 'https://shopsearch.taobao.com/search?app=shopsearch&q={}'
        world_list = ['papa recipe']

        addrs_url = '&loc={}'
        addrs_list = ['']

        shop_type_url = '&isb=1&shop_type=&ratesum={}'
        shop_type = ['jin', '']

        haoping_url = '&isb=0&goodrate={}00%2C'
        haoping_list = ['97', '']

        for w in itertools.product(world_list, addrs_list, shop_type, haoping_list):
            url_ = base_url + addrs_url + shop_type_url + haoping_url
            url = url_.format(*w)
            yield scrapy.Request(url, callback=self.parse)

    def parse(self, response):
        url_list = re.findall(r'shopUrl":"(//.*?.taobao.com)"', response.text)
        for url in url_list:
            yield scrapy.Request('https:{}/search.htm'.format(url), callback=self.get_shop_id)

        # 翻页
        furl_obj = furl.furl(response.url)
        if len(url_list) == 20:
            s = furl_obj.args.get('s', None)
            if s:
                s += int(s) + 20
                furl_obj.args['s'] = s
            else:
                furl_obj.args['s'] = 20
            next_url = furl_obj.url
            yield scrapy.Request(next_url, callback=self.parse)

    def get_shop_id(self, response):
        shop_id = re.findall(r'data-widgetid="(\d*?)"', response.text)[4]
        # https://dcxgz.taobao.com/i/asynSearch.htm?callback=jsonp273&mid=w-15094675485-0&wid=15094675485&path=/view_shop.htm&search=y&keyword=papa+recip
        base_url = 'https://{}/i/asynSearch.htm?callback=jsonp273&mid=w-{}-0&wid={}' \
                   '&path=/view_shop.htm&search=y&keyword={}'

        tianmao_base_url = 'https://{}/i/asynSearch.htm?callback=jsonp126&mid=w-{}-0&wid={}' \
                   '&path=/view_shop.htm&search=y&keyword={}'

        host = response.url.split('/')[2]

        if host.endswith('tmall.hk') or host.endswith('tmall.com'):
            url = tianmao_base_url.format(host, shop_id, shop_id, 'papa recipe')
            yield scrapy.Request(url, callback=self.shop_search_pag)
        elif host.endswith('taobao.com'):
            url = base_url.format(host, shop_id, shop_id, 'papa recipe')
            yield scrapy.Request(url, callback=self.shop_search_pag)

    def shop_search_pag(self, response):
        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Safari/537.36'
        }

        if 'tmall.hk' in response.url or 'tmall.com' in response.url:
            # 60
            url_list = set(re.findall(r'item.htm\?id=\d+', response.text))
            for url in url_list:
                host = response.url.split('/')[2].split('.')[-1]
                url_ = 'https://detail.m.tmall.{}/{}'.format(host, url)
                yield scrapy.Request(url_, callback=self.tianmao_m_pag, headers=headers)

            # 翻页
            if '没找到符合条件的商品,换个条件或关键词试试吧' not in response.text:
                pass
                furl_obj = furl.furl(response.url)
                if furl_obj.args.get('pageNo', None):
                    furl_obj.args['pageNo'] = int(furl_obj.args['pageNo']) + 1
                else:
                    furl_obj.args['pageNo'] = 2
                yield scrapy.Request(furl_obj.url, callback=self.shop_search_pag)

        elif 'taobao.com' in response.url:
            # 24
            pass
            r'<a class=\"item-name J_TGoldData\" href=\"//item.taobao.com/item.htm\?id=\d+\"'
            url_list = set(re.findall(r'item.htm\?id=\d+', response.text))
            for url in url_list:
                url_ = 'https://item.taobao.com/{}'.format(url)
                yield scrapy.Request(url_, callback=self.goods_pag, headers=headers)

            # 翻页

            goods_num = re.findall(r'共搜索到<span> (\d*?) </span>个符合条件的商品', response.text)

            if int(goods_num[0]):
                pass
                furl_obj = furl.furl(response.url)
                if furl_obj.args.get('pageNo', None):
                    furl_obj.args['pageNo'] = int(furl_obj.args['pageNo']) + 1
                else:
                    furl_obj.args['pageNo'] = 2
                yield scrapy.Request(furl_obj.url, callback=self.shop_search_pag)
            else:
                pass
                print(response.url)

    def goods_pag(self, response):
        print(response.text)

    def tianmao_m_pag(self, response):
        xpath_item = {
            'shop_name': '//div[@class="shop-t"]/text()',  # 店铺名称
            'name': '//h1/text()',  # 宝贝名称
            # 'price': '//section[@id="s-price"]//span[@class="mui-price-integer"]/text()',  # 价格
        }
        tree = lxml.etree.HTML(response.text)
        result = {}
        for key in xpath_item:
            result[key] = ''.join(tree.xpath(xpath_item[key]))
        result['sell_count'] = re.search(r'"sellCount":(\d*?)\,', response.text).group(1)
        result['price'] = re.search(r'"price":"(\d.*?\d)\"\,', response.text).group(1)

        # id
        result['goods_id'] = re.search(r'id=(\d*)', response.url).group(1)

        yield items.TaobaoSukItem(detail=result)



