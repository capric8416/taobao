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
        'month ': '//ul[@class="attributes-list"]//li[contains(text(),"月份")]/@title' # 月份


    }
    tree = etree.HTML(response.text)
    result = {}
    for key in xpath_item:
        result[key] = ''.join(tree.xpath(xpath_item[key])).strip()
    print(result)




# https://detailskip.taobao.com/service/getData/1/p1/item/detail/sib.htm?itemId=543885809931&sellerId=26635013&modules=dynStock,qrcode,viewer,price,duty,xmpPromotion,delivery,activity,fqg,zjys,amountRestriction,couponActivity,soldQuantity,originalPrice,tradeContract&callback=onSibRequestSuccess

def taobao_get_sell(response):
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




def tianmao_m_pag(response):
    xpath_item = {
        'shop_name': '//div[@class="shop-t"]/text()',  # 店铺名称
        'name': '//h1/text()',  # 宝贝名称
        'original_price': '//section[@id="s-price"]//span[@class="mui-price-integer"]/text()',  # 原价格
    }
    tree = etree.HTML(response.text)
    item = {}
    for key in xpath_item:
        item[key] = ''.join(tree.xpath(xpath_item[key]))

    products = ''.join(tree.xpath('//div[@class="mui-standardItemProps mdv-standardItemProps"]/@mdv-cfg'))
    props = json.loads(products).get('data', {}).get('props', []) if products else {}

    key_item = {
        '品牌': 'brand',
        '产地': 'origin_place',
        '上市时间': 'market_time',
        '功效': 'effect',
        '月份': 'month',
        '保质期': 'shelf_life',
        '适合肤质': 'suitable_skin'
    }
    for data in props:
        key = data.get('ptext', '')
        if key in key_item:
            item[key_item[key]] = ''.join(data.get('vtexts', ''))

    text = response.text
    item['sell_count'] = re.search(r'"sellCount":(\d*?)\,', text).group(1)  # 销量
    # item['price'] = re.search(r'"price":"(\d.*?\d)\"\,', text)   # 促销价
    item['deliveryAddress'] = re.search(r'"deliveryAddress":"(.*?)\"\,', text).group(1) # 发货地
    item['rate_counts'] = re.search(r'"rateCounts":(\d*?)\,', text).group(1) # 累计评价
    item['totalQuantity'] = re.search(r'"totalQuantity":(\d*?)\,', text).group(1)  # 库存
    item['goods_id'] = re.search(r'id=(\d*)', response.url).group(1)
    json_text  = re.search(r'var _DATA_Mdskip =\s({.*?})\s</script>', text).group(1)
    item['price'] = json.loads(json_text).get('defaultModel', {}).get('newJhsDO', {}).get('activityPrice', 0)
    print (item)

# if __name__ == '__main__':

    # tianmao_m_pag(text)