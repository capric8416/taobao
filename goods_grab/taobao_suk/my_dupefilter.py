from scrapy_redis.dupefilter import RFPDupeFilter
from scrapy.utils.request import _fingerprint_cache
from scrapy.utils.request import *


def request_fingerprint(request, include_headers=None):
    """
    Return the request fingerprint.

    The request fingerprint is a hash that uniquely identifies the resource the
    request points to. For example, take the following two urls:

    http://www.example.com/query?id=111&cat=222
    http://www.example.com/query?cat=222&id=111

    Even though those are two different URLs both point to the same resource
    and are equivalent (ie. they should return the same response).

    Another example are cookies used to store session ids. Suppose the
    following page is only accesible to authenticated users:

    http://www.example.com/members/offers.html

    Lot of sites use a cookie to store the session id, which adds a random
    component to the HTTP Request and thus should be ignored when calculating
    the fingerprint.

    For this reason, request headers are ignored by default when calculating
    the fingeprint. If you want to include specific headers use the
    include_headers argument, which is a list of Request headers to include.

    """
    if include_headers:
        include_headers = tuple(to_bytes(h.lower())
                                 for h in sorted(include_headers))
    cache = _fingerprint_cache.setdefault(request, {})
    if include_headers not in cache:
        fp = hashlib.sha1()
        fp.update(to_bytes(canonicalize_url(request.url)))
        cache[include_headers] = fp.hexdigest()
    return cache[include_headers]


class RFPDupeFilter(RFPDupeFilter):

    def request_seen(self, request):
        """Returns True if request was already seen.

        Parameters
        ----------
        request : scrapy.http.Request

        Returns
        -------
        bool

        """
        fp = self.request_fingerprint(request)
        # This returns the number of values added, zero if already exists.
        added = self.server.sadd(self.key, fp)
        return added == 0

    def request_fingerprint(self, request):
        """Returns a fingerprint for a given request.

        Parameters
        ----------
        request : scrapy.http.Request

        Returns
        -------
        str

        """
        return request_fingerprint(request)