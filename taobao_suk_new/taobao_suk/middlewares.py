# -*- coding: utf-8 -*-

# Define here the models for your spider middleware
#
# See documentation in:
# http://doc.scrapy.org/en/latest/topics/spider-middleware.html
from scrapy.utils.gz import gunzip, is_gzipped
from scrapy.exceptions import IgnoreRequest
from scrapy import signals
from .ProxySwift import proxy_pool
import logging
# 启动代理池
proxy_pool.blacklist_clean_timing = 60*60*24
# proxy_pool.advance_time = 299
proxy_pool.redis_url = ''
proxy_pool.start()
logger = logging.getLogger(__name__)


class ProxyMiddleware(object):
    proxy_list = []
    # proxy_list = next(proxy_genter)

    def process_request(self, request, spider):

            proxy_server = proxy_pool.get()
            request.meta['proxy'] = "http://%s" % proxy_server


def _retry(max_retry_times, request, reason, spider):
    retries = request.meta.get('retry_times', 0) + 1

    if retries <= max_retry_times:
        logger.debug("Retrying %(request)s (failed %(retries)d times): %(reason)s",
                     {'request': request, 'retries': retries, 'reason': reason},
                     extra={'spider': spider})
        retryreq = request.copy()
        retryreq.meta['retry_times'] = retries
        retryreq.dont_filter = True
        # retryreq.priority = request.priority + self.priority_adjust
        return retryreq
    else:
        logger.debug("Gave "
                     " xc retrying %(request)s (failed %(retries)d times): %(reason)s",
                     {'request': request, 'retries': retries, 'reason': reason},
                     extra={'spider': spider})


def change_ip(request):
    proxy_server = request.meta['proxy']
    proxy_pool.change_ip(proxy_server)



class TaobaoSukSpiderMiddleware(object):
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the spider middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(response, spider):
        # Called for each response that goes through the spider
        # middleware and into the spider.

        # Should return None or raise an exception.
        return None

    def process_spider_output(response, result, spider):
        # Called with the results returned from the Spider, after
        # it has processed the response.

        # Must return an iterable of Request, dict or Item objects.
        for i in result:
            yield i

    def process_spider_exception(response, exception, spider):
        # Called when a spider or process_spider_input() method
        # (from other spider middleware) raises an exception.

        # Should return either None or an iterable of Response, dict
        # or Item objects.
        pass

    def process_start_requests(start_requests, spider):
        # Called with the start requests of the spider, and works
        # similarly to the process_spider_output() method, except
        # that it doesn’t have a response associated.

        # Must return only requests (not items).
        for r in start_requests:
            yield r

    def spider_opened(self, spider):
        spider.logger.info('Spider opened: %s' % spider.name)


class RetryMiddlewareDataIsNull(object):

    # static_max_error_number = settings.Max_Error_Number
    # max_error_number = settings.Max_Error_Number
    # max_retry_times = settings.RETRY_TIMES

    static_max_error_number = 10
    max_error_number = 10
    max_retry_times = 10

    def check_keyword(self, body, response):
        if 'http://www.qichacha.com/index_verify' in body:
            return False
        if '请先登录或者您没有这个权限' in body:
            return False
        elif 'www.qichacha.com/user_login' in response.url:
            return False
        else:
            return True

    def process_response(self, request, response, spider):

        if response.status == 302 and 'Spider-checklogin' in str(response.headers.get('Location', '')):
            retry_return = _retry(self.max_retry_times, request, 'Data Is Null', spider)

            change_ip(request)

            if retry_return:
                return retry_return
            else:
                raise IgnoreRequest()

        return response





