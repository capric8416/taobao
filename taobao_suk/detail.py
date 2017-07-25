import json
import re
from lxml import etree

def parse(response):
    # 淘宝
    xpath_item = {
        'shop_name': '//div[@class="tb-shop-name"]//a/text()',  # 店铺名称
        'name': '//h3[@class="tb-main-title"]/text()',  # 宝贝名称
        'original_price': '//strong[@id="J_StrPrice"]/em[@class="tb-rmb-num"]/text()', # 原价

        'market_time': '//ul[@class="attributes-list"]//li[contains(text(),"上市时间")]/@title', # i上市时间
        'category': '//ul[@class="attributes-list"]//li[contains(text(),"面膜分类")]/@title', # 面膜分类
        'suitable_skin  ': '//ul[@class="attributes-list"]//li[contains(text(),"适合肤质")]/@title',  # 适合肤质
        'effect': '//ul[@class="attributes-list"]//li[contains(text(),"功效")]/@title',  # 功效
        'shelf_life ': '//ul[@class="attributes-list"]//li[contains(text(),"保质期")]/@title', # 保质期

        'goods_name ': '//ul[@class="attributes-list"]//li[contains(text(),"品名")]/@title',  # 品名
        'brand ': '//ul[@class="attributes-list"]//li[contains(text(),"品牌")]/@title',  # 品牌
        'origin_place ': '//ul[@class="attributes-list"]//li[contains(text(),"产地")]/@title',  # 产地
        'color_type ': '//ul[@class="attributes-list"]//li[contains(text(),"颜色分类")]/@title',  # 颜色分类
        'rule_type ': '//ul[@class="attributes-list"]//li[contains(text(),"规格类型")]/@title',  # 规格类型
        'rule_type ': '//ul[@class="attributes-list"]//li[contains(text(),"月份")]/@title' # 月份


    }
    tree = etree.HTML(response.text)
    result = {}
    for key in xpath_item:
        result[key] = ''.join(tree.xpath(xpath_item[key])).strip()
    print(result)




# https://detailskip.taobao.com/service/getData/1/p1/item/detail/sib.htm?itemId=543885809931&sellerId=26635013&modules=dynStock,qrcode,viewer,price,duty,xmpPromotion,delivery,activity,fqg,zjys,amountRestriction,couponActivity,soldQuantity,originalPrice,tradeContract&callback=onSibRequestSuccess

def get_sell(response):
    item = {}
    text = response.text
    data = json.loads(text.strip('onSibRequestSuccess(').strip(');')).get('data', {})
    item['price'] = data.get('promotion', {}).get('promoData', {}).get('def', [{}])[0].get('price', 0)\
                        or data.get('price', 0)

    item['sell_count'] = data.get('soldQuantity', {}).get('confirmGoodsCount', 0)  # 月销量
    item['totalQuantity'] = data.get('dynStock', {}).get('sellableQuantity', 0) # 库存
    item['deliveryAddress'] = data.get('deliveryFee', {}).get('data', {}).get('sendCity', '') # 发货地
    item['goods_id'] = re.search(r'itemId=(\d*)', response.url).group(1)  # 宝贝id

    price = item['price'].split('-')
    if len(price) >= 2:
        # 30天销售额
        item['month_sales'] = item['sell_count'] * price[0] * 30 + '-' + item['sell_count'] * price[-1] * 30
    else:
        item['month_sales'] = item['sell_count'] * price[0] * 30


if __name__ == '__main__':
    parse(text)