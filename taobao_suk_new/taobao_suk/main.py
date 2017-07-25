#!/usr/bin/env python3
# -*- coding: utf8 -*-

# import os
#
# os.system("scrapy crawl ershoufang")
from scrapy import cmdline
# cmdline.execute("scrapy crawl qichacha_other_spider".split())
# cmdline.execute("scrapy crawl qichacha_spider".split())
cmdline.execute("scrapy crawl taobao".split())
# cmdline.execute("scrapy crawl qichacha_search".split())
