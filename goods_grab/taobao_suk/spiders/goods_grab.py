# -*- coding: utf-8 -*-
import re
import lxml
import json
import furl
import scrapy
from datetime import datetime
from taobao_suk import items
from scrapy_redis.spiders import RedisSpider


class GoodsGrab(RedisSpider):
    name = "goods_grab"
    redis_key = 'goods_grab:start_urls'
    allowed_domains = ["taobao.com", "tmall.hk", "tmall.com"]

    custom_settings = {
        'SCHEDULER': 'scrapy_redis.scheduler.Scheduler',
        'SCHEDULER_PERSIST': True,
        'SCHEDULER_QUEUE_CLASS': 'scrapy_redis.queue.SpiderPriorityQueue',
        'DUPEFILTER_CLASS': 'taobao_suk.my_dupefilter.RFPDupeFilter',
        # 'ITEM_PIPELINES': {
        #                     'scrapy_redis.pipelines.RedisPipeline': 300,
        #                     }

    }


    def parse(self, response):

        if 'taobao' in response.url:
            # 淘宝
            url_, goods_info = self.toaobao_goods_pag(response)
            headers = {'accept': '*/*',
                         'accept-encoding': 'gzip, deflate, br',
                         'accept-language': 'zh-CN,zh;q=0.8',
                         'authority': 'detailskip.taobao.com',
                         # 'referer': 'https://item.taobao.com/item.htm?spm=a219r.lm5644.14.11.70b3a555eCfx0A&id=541986659658&ns=1&abbucket=18',
                         'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Safari/537.36'}

            yield scrapy.Request(url_, callback=self.get_sell, meta={'data': goods_info}, headers=headers)

        elif 'tmall' in response.url:
            # 天猫
            goods_info = self.tianmao_m_pag(response)
            yield items.TaobaoSukItem(detail={'goods_info': goods_info})

        else:
            self.logger.error('未知url：{}'.format(response.url))

    def toaobao_goods_pag(self, response):

        xpath_item = {
            'shop_name': '//div[@class="tb-shop-name"]//a/text()',  # 店铺名称
            'name': '//h3[@class="tb-main-title"]/text()',  # 宝贝名称
            'original_price': '//strong[@id="J_StrPrice"]/em[@class="tb-rmb-num"]/text()',  # 原价

            'market_time': '//ul[@class="attributes-list"]//li[contains(text(),"上市时间")]/@title',  # i上市时间
            'category': '//ul[@class="attributes-list"]//li[contains(text(),"面膜分类")]/@title',  # 面膜分类
            'suitable_skin': '//ul[@class="attributes-list"]//li[contains(text(),"适合肤质")]/@title',  # 适合肤质
            'effect': '//ul[@class="attributes-list"]//li[contains(text(),"功效")]/@title',  # 功效
            'shelf_life': '//ul[@class="attributes-list"]//li[contains(text(),"保质期")]/@title',  # 保质期

            'goods_name': '//ul[@class="attributes-list"]//li[contains(text(),"品名")]/@title',  # 品名
            'brand': '//ul[@class="attributes-list"]//li[contains(text(),"品牌")]/@title',  # 品牌
            'origin_place': '//ul[@class="attributes-list"]//li[contains(text(),"产地")]/@title',  # 产地
            'color_type': '//ul[@class="attributes-list"]//li[contains(text(),"颜色分类")]/@title',  # 颜色分类
            'rule_type': '//ul[@class="attributes-list"]//li[contains(text(),"规格类型")]/@title',  # 规格类型
            'month': '//ul[@class="attributes-list"]//li[contains(text(),"月份")]/@title',  # 月份
            'is_special': '//ul[@class="attributes-list"]//li[contains(text(),"是否为特殊用途化妆品")]/@title',
            'use_date_range': '//ul[@class="attributes-list"]//li[contains(text(),"限期使用日期范围")]/@title',
            'net_content': '//ul[@class="attributes-list"]//li[contains(text(),"化妆品净含量")]/@title',
            'single_product': '//ul[@class="attributes-list"]//li[contains(text(),"面膜单品")]/@title',
        }
        tree = lxml.etree.HTML(response.text)
        result = {}
        for key in xpath_item:
            result[key] = ''.join(tree.xpath(xpath_item[key])).strip()


        url = "https://detailskip.taobao.com/service/getData/1/p1/item/detail/sib.htm?itemId={}&modules=dynStock," \
              "qrcode,viewer,price,duty,xmpPromotion,delivery,activity,fqg,zjys,couponActivity,soldQuantity,original" \
              "Price,tradeContract"

        goods_id = re.search(r'id=(\d*)', response.url).group(1)
        url_ = url.format(goods_id)

        return url_, result

    def get_sell(self, response):
        item = {}
        text = response.text
        data = json.loads(text.strip('onSibRequestSuccess(').strip(');')).get('data', {})
        item['price'] = data.get('promotion', {}).get('promoData', {}).get('def', [{}])[0].get('price', 0) \
                        or data.get('price', 0)

        item['sell_count'] = data.get('soldQuantity', {}).get('confirmGoodsCount', 0)  # 月销量
        item['totalQuantity'] = data.get('dynStock', {}).get('sellableQuantity', 0)  # 库存
        item['deliveryAddress'] = data.get('deliveryFee', {}).get('data', {}).get('sendCity', '')  # 发货地
        try:
            item['goods_id'] = int(re.search(r'itemId=(\d*)', response.url).group(1))  # 宝贝id
        except Exception as e:
            self.logger.error(e)

        price = str(item['price']).split('-')
        if len(price) >= 2:
            # 30天销售额
            item['month_sales'] = str(item['sell_count'] * float(price[0])) + '-' + str(item['sell_count'] * float(price[-1]))
        else:
            item['month_sales'] = item['sell_count'] * float(price[0])

        base_info = response.meta['data']
        base_info.update(item)
        base_info['shop_type'] = '淘宝'
        base_info['modified'] = datetime.now()
        now_today = datetime.today()
        base_info['date'] = datetime.fromordinal(now_today.toordinal())
        yield items.TaobaoSukItem(detail={'goods_info': base_info})

    def tianmao_m_pag(self, response):
        xpath_item = {
            'shop_name': '//div[@class="shop-name"]/text()',  # 店铺名称
            'name': '//div[@class="main"]/text()',  # 宝贝名称
            'original_price': '//span[@class="price"]/text()',  # 原价格
        }
        tree = lxml.etree.HTML(response.text)

        item = {}
        for key in xpath_item:
            item[key] = ''.join(tree.xpath(xpath_item[key])).replace('\n', '').strip()

        if not item['name']:
            item['name'] = ''.join(tree.xpath('//div[@class="main"]/h1/text()'))

        if not item['original_price']:
            item['original_price'] = ''.join(tree.xpath('//span[@class="mui-price-integer"]/text()'))

        if not item['shop_name']:
            item['shop_name'] = ''.join(tree.xpath('//div[@class="shop-t"]/text()'))

        try:
            item['goods_id'] = int(re.search(r'id=(\d*)', response.url).group(1))
        except Exception as e:
            self.logger.error('tianmao get goods id error,{}:{}'.format(response.url, error))

        products = ''.join(tree.xpath('//div[@class="mui-standardItemProps mdv-standardItemProps"]/@mdv-cfg'))
        try:
            props = json.loads(products).get('data', {}).get('props', [])
        except Exception as e:
            props = []
            self.logger.error(e)

        key_item = {
            '品牌': 'brand',
            '产地': 'origin_place',
            '上市时间': 'market_time',
            '功效': 'effect',
            '月份': 'month',
            '保质期': 'shelf_life',
            '适合肤质': 'suitable_skin'}
        for data in props:
            key = data.get('ptext', '')
            if key in key_item:
                item[key_item[key]] = ''.join(data.get('vtexts', ''))
        if not props:
            for k, v in key_item.items():
                item[v] = ''
	        

        text = response.text

        item['price'] = ''
        item['sell_count'] = int(self.regular_expression_match(r'"sellCount":(\d*?)\,', text, 0))  # 销量
        item['deliveryAddress'] = self.regular_expression_match(r'"deliveryAddress":(.*?),', text, '')

        item['rate_counts'] = self.regular_expression_match(r'"commentCount":(\d+?),', text, 0) # 累计评价
        item['totalQuantity'] = self.regular_expression_match(r'"totalQuantity":(\d*?)\,', text, 0) # 库存

        text = tree.xpath('//script[contains(text(), "_DATA_Mdskip")]/text()')
        text = text[0] if text else '{}'
        json_text = text.replace('var _DATA_Mdskip =  ', '').replace('\n', '').strip()

        # json_text = self.regular_expression_match(r'var _DATA_Mdskip =([\s\S]*) </script>', text, '{}')
        # if not json_text:
        #     json_text = self.regular_expression_match(r'var _DATA_Mdskip =\s({.*?})\s</script>', text, '{}')
        if not item['totalQuantity']: 
            item['totalQuantity'] = self.regular_expression_match(r'"quantity":(\d+)', json_text, 0)
        try:
            json_item = json.loads(json_text)
        except Exception as e:
            self.logger.error(e)
            json_item = {}

        if 'defaultModel' in json_item:
            item['price'] = json_item.get('defaultModel', {}).get('newJhsDO', {}).get('activityPrice', 0)
            if not item['price']:
                item['price'] = json_item.get('defaultModel', {}).get('itemPriceResultDO', {}).get('priceInfo', {}).get('def', {}).get('promotionList', [{}])[0].get('price', 0)

        if 'delivery' in json_item:
            if not item['deliveryAddress']:
                item['deliveryAddress'] = json_item.get('delivery', {}).get('from', '')

        if 'price' in json_item:
            if not item['original_price']:
                item['original_price'] = json_item.get('price').get('extraPrices', [{}])[0].get('priceText', '')
            item['price'] = json_item.get('price').get('price', {}).get('priceText', 0)

        if not item['price']:
            item['price'] = self.regular_expression_match(r'<span class="mui-price-integer">(.*?)</span>', text, 0) # 价格

        self.logger.info('tianmao regular match: {}'.format(item))
        price = str(item['price']).split('-')
        if len(price) >= 2:
            # 30天销售额
            item['month_sales'] = str(item['sell_count'] * float(price[0])) + '-' + str(item['sell_count'] * float(price[-1]))
        else:
            item['month_sales'] = item['sell_count'] * float(price[0])
        item['shop_type'] = '天猫'
        item['modified'] = datetime.now()
        now_today = datetime.today()
        item['date'] = datetime.fromordinal(now_today.toordinal())
        return item

    def regular_expression_match(self, regular, text, default=''):
        try:
            result = re.search(regular, text)
            result = result.group(1) if result else default
            return result
        except Exception as e:
            self.logger.error(e)
            return default
	    
