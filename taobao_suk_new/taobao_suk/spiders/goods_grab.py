# -*- coding: utf-8 -*-
import scrapy
from scrapy_redis.spiders import RedisSpider
import itertools
import furl
import re
import lxml
import json
from taobao_suk import items


class GoodsGrab(RedisSpider):
    name = "goods_grab"
    redis_key = 'goods_grab:start_urls'
    allowed_domains = ["taobao.com", "tmall.hk", "tmall.com"]

    def parse(self, response):
        pass

    def goods_pag(self, response):

        xpath_item = {
            'shop_name': '//div[@class="tb-shop-name"]//a/text()',
            'name': '//h3[@class="tb-main-title"]/text()'
        }
        tree = lxml.etree.HTML(response.text)
        result = {}
        for key in xpath_item:
            result[key] = ''.join(tree.xpath(xpath_item[key])).strip()


        # headers = {
        #     'referer': 'https://item.taobao.com/item.htm?spm=a230r.1.14.147.ebb2eb2HRxQCC&id=549073432347&ns=1&abbucket=18'}

        # data = {'itemId': '549073432347',
        #         'modules': 'dynStock,qrcode,viewer,price,duty,xmpPromotion,delivery,activity,fqg,zjys,couponActivity,soldQuantity,originalPrice,tradeContract'}

        url = "https://detailskip.taobao.com/service/getData/1/p1/item/detail/sib.htm?itemId={}&modules=dynStock," \
              "qrcode,viewer,price,duty,xmpPromotion,delivery,activity,fqg,zjys,couponActivity,soldQuantity,original" \
              "Price,tradeContract"

        goods_id = re.search(r'id=(\d*)', response.url).group(1)
        url_ = url.format(goods_id)

        yield scrapy.Request(url_,
                             # headers=headers,
                             callback=self.get_sell, meta={'data': result})

    def get_sell(self, response):
        item = {}
        text = response.text
        data = json.loads(text.strip('onSibRequestSuccess(').strip(');')).get('data', {})
        item['price'] = data.get('promotion', {}).get('promoData', {}).get('def', [{}])[0].get('price', 0)\
                        or data.get('price', 0)
        item['sell_count'] = data.get('soldQuantity', {}).get('confirmGoodsCount', 0)

        base_info = response.meta['data']
        base_info.update(item)

        base_info['goods_id'] = re.search(r'itemId=(\d*)', response.url).group(1)

        yield items.TaobaoSukItem(detail={'base_info': base_info})

    def tianmao_m_pag(self, response):
        xpath_item = {
            'shop_name': '//div[@class="shop-t"]/text()',  # 店铺名称
            'name': '//h1/text()',  # 宝贝名称
            # 'price': '//section[@id="s-price"]//span[@class="mui-price-integer"]/text()',  # 价格
        }
        tree = lxml.etree.HTML(response.text)

        base_info = {}
        for key in xpath_item:
            base_info[key] = ''.join(tree.xpath(xpath_item[key]))
        base_info['sell_count'] = re.search(r'"sellCount":(\d*?)\,', response.text).group(1)
        base_info['price'] = re.search(r'"price":"(\d.*?\d)\"\,', response.text).group(1)

        # id
        base_info['goods_id'] = re.search(r'id=(\d*)', response.url).group(1)

        yield items.TaobaoSukItem(detail={'base_info': base_info})
