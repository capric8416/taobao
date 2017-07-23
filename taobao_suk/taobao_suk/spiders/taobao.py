# -*- coding: utf-8 -*-
import scrapy
import itertools
import furl
import re
import lxml
import json
from taobao_suk import items


class TaobaoSpider(scrapy.Spider):
    name = "taobao"
    allowed_domains = ["taobao.com", "tmall.hk", "tmall.com"]
    start_urls = ['http://taobao.com/']

    def start_requests(self):

        # 重跑所有链接


        base_url = 'https://shopsearch.taobao.com/search?app=shopsearch&q={}'
        # world_list = ['papa recipe']
        world_list = ['papa recipe', 'LEADERS', 'CNP',
                      'JAYJUN', 'SNP', 'MEDIHEAL', 'JM Solution',
                      'It’s Skin',         'The Saem', 'Innisfree', 'Tony Moly',
        'AHC', 'Shangpree']

        addrs_url = '&loc={}'
        addrs_list =['']
        # addrs_list = ["北京", "上海", "广州", "深圳", "杭州", "海外", "江浙沪", "珠三角", "京津冀", "东三省", "港澳台",
        # "江浙沪皖", "长沙", "长春", "成都", "重庆", "大连", "东莞", "佛山", "福州", "贵阳", "合肥",
        # "金华", "济南", "嘉兴", "昆明", "宁波", "南昌", "南京", "青岛", "泉州", "沈阳", "苏州", "天津",
        # "温州", "无锡", "武汉", "西安", "厦门", "郑州", "中山", "石家庄", "哈尔滨", "安徽", "福建",
        # "甘肃", "广东", "广西", "贵州", "海南", "河北", "河南", "湖北", "湖南", "江苏", "江西", "吉林",
        # "辽宁", "宁夏", "青海", "山东", "山西", "陕西", "云南", "四川", "西藏", "新疆", "浙江", "澳门",
        # "香港", "台湾", "内蒙古", "黑龙江"]

        shop_type_url = '&isb={}'
        shop_type = ['0', '1']

        haoping_url = '&isb=0&goodrate={}00%2C'
        haoping_list = ['97']

        # haoping_list = ['97', '100', '99', '98', '96']

        for w in itertools.product(world_list, addrs_list, shop_type, haoping_list):
            url_ = base_url + addrs_url + shop_type_url + haoping_url
            url = url_.format(*w)
            yield scrapy.Request(url, callback=self.parse)

    def parse(self, response):
        url_list = re.findall(r'shopUrl":"(//.*?.taobao.com)"', response.text)
        for url in url_list:
            yield scrapy.Request('https:{}/search.htm'.format(url), callback=self.get_shop_id)

        # 翻页
        # furl_obj = furl.furl(response.url)
        # if len(url_list) == 20:
        #     s = furl_obj.args.get('s', None)
        #     if s:
        #         s = int(s) + 20
        #         furl_obj.args['s'] = s
        #     else:
        #         furl_obj.args['s'] = 20
        #     next_url = furl_obj.url
        #     yield scrapy.Request(next_url, callback=self.parse)

    def get_shop_id(self, response):
        # shop_id = re.findall(r'data-widgetid="(\d*?)"', response.text)[4]

        # https://dcxgz.taobao.com/i/asynSearch.htm?callback=jsonp273&mid=w-15094675485-0&wid=15094675485&path=/view_shop.htm&search=y&keyword=papa+recip
        base_url = 'https://{}/i/asynSearch.htm?callback=jsonp273&mid=w-{}-0&wid={}' \
                   '&path=/view_shop.htm&search=y&keyword={}'

        tianmao_base_url = 'https://{}/i/asynSearch.htm?callback=jsonp126&mid=w-{}-0&wid={}' \
                   '&path=/view_shop.htm&search=y&keyword={}'

        host = response.url.split('/')[2]

        if host.endswith('tmall.hk') or host.endswith('tmall.com'):
            shop_id = response.xpath(
                '//div[@class="layout grid-s5m0 J_TLayout"]/div/div/div[@class="J_TModule"][1]/@data-widgetid').extract_first()
            url = tianmao_base_url.format(host, shop_id, shop_id, 'papa recipe')
            yield scrapy.Request(url, callback=self.shop_search_pag)
        elif host.endswith('taobao.com'):
            shop_id = re.findall(r'data-widgetid="(\d*?)"', response.text)[4]
            url = base_url.format(host, shop_id, shop_id, 'papa recipe')
            yield scrapy.Request(url, callback=self.shop_search_pag)

    def shop_search_pag(self, response):
        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/59.0.3071.115 Safari/537.36'
        }

        if 'tmall.hk' in response.url or 'tmall.com' in response.url:
            # 60
            text_base = response.text.partition('本店内推荐')[0]
            url_list = set(re.findall(r'item.htm\?id=\d+', text_base))
            for url in url_list:
                host = response.url.split('/')[2].split('.')[-1]
                url_ = 'https://detail.m.tmall.{}/{}'.format(host, url)
                yield scrapy.Request(url_, callback=self.tianmao_m_pag, headers=headers)

            # 翻页
            # if '没找到符合条件的商品,换个条件或关键词试试吧' not in response.text:
            #     pass
            #     furl_obj = furl.furl(response.url)
            #     if furl_obj.args.get('pageNo', None):
            #         furl_obj.args['pageNo'] = int(furl_obj.args['pageNo']) + 1
            #     else:
            #         furl_obj.args['pageNo'] = 2
            #     yield scrapy.Request(furl_obj.url, callback=self.shop_search_pag)

        elif 'taobao.com' in response.url:
            # 24
            pass

            # 翻页

            goods_num = re.findall(r'共搜索到<span> (\d*?) </span>个符合条件的商品', response.text)
            if int(goods_num[0]):
                return
            # try:
            #     int(goods_num[0])
            # except:
            #     pass
            #     print('-----------')
            #
            # if int(goods_num[0]):
            #     pass
            #     furl_obj = furl.furl(response.url)
            #     if furl_obj.args.get('pageNo', None):
            #         furl_obj.args['pageNo'] = int(furl_obj.args['pageNo']) + 1
            #     else:
            #         furl_obj.args['pageNo'] = 2
            #     yield scrapy.Request(furl_obj.url, callback=self.shop_search_pag)
            # else:
            #     pass

            r'<a class=\"item-name J_TGoldData\" href=\"//item.taobao.com/item.htm\?id=\d+\"'
            url_list = set(re.findall(r'item.htm\?id=\d+', response.text))
            for url in url_list:
                url_ = 'https://item.taobao.com/{}'.format(url)
                yield scrapy.Request(url_, callback=self.goods_pag, headers=headers)



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



