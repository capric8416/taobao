const phantom = require('phantom');
const url = require('url');
const yargs = require('yargs');


class NetworkSniffer {
    constructor (
        task, proxy_conf, user_agent, load_images=false,
        view_port={width: 414, height: 736}, resource_timeout=10000
    ) {
        this.task = task

        this.load_images = load_images
        this.resource_timeout = resource_timeout
        this.user_agent = user_agent
        this.view_port = view_port

        this.browser = this.page = null

        this.command_lines = ['--ignore-ssl-errors=true']
        if(proxy_conf !== undefined && proxy_conf != null) {
            this.command_lines.push(`--proxy=${proxy_conf}`)
        }
    }

    is_css(request) {
        return url.parse(request.url).pathname.endsWith('.css') || 
            request.headers['Content-Type'] == 'text/css'
    }

    async monitor () {
        this.browser = await phantom.create(this.command_lines)
        this.page = await this.browser.createPage()

        this.page.property('loadImages', this.load_images)
        this.page.property('resourceTimeout', this.resource_timeout)
        this.page.property('userAgent', this.user_agent)
        this.page.property('viewportSize', this.view_port)

         this.page.on('onResourceTimeout', (res) => {
             console.info(`Timeout #${res.id}: ${res.url}`)
         })

         this.page.on('onResourceError', (res) => {
             console.info(`Error #${res.id}: ${res.url}`)
         })

         this.page.on('onResourceRequested', (res, req) => {
             console.info(`Request #${res.id}: ${res.url}`)
            //  if(this.is_css(res)) {
            //      req.abort()
            //  }
         })

         this.page.on('onResourceReceived', (res) => {
             console.info(`Response #${res.id}: ${res.url}`)
         })

        await this.task(this, this.browser, this.page)
    }
}


async function get_shop_item_list(instance, browser, page) {
    console.log('------------------------------------------------------------------------')

    // // 天猫
    // req_url = 'https://shop113927383.m.taobao.com/#list?q=Shangpree'
    // // 淘宝
    // req_url = 'https://shop34135992.m.taobao.com/#list?q=%E9%9F%A9%E5%9B%BD'

    await page.open(req_url)

    let resp_url = await page.property('url')
    let resp_content = await page.property('content')

    u1 = url.parse(req_url)
    u2 = url.parse(resp_url)

    if(u1.host.endsWith('taobao.com') && u2.host.endsWith('tmall.com')) {
        req_url = `${u2.protocol}//${u2.host}/shop/shop_auction_search.htm?q=${keyword}`
        console.log(req_url)

        await page.open(req_url)

        resp_content = await page.property('content')
    }
    else {

    }
        
    await page.close()
    await browser.exit()

    console.log('------------------------------------------------------------------------')
}


if(require.main == module) {
    let argv = yargs.argv
    let proxy_conf = argv.proxy

    let network_sniffer = new NetworkSniffer(
        task=get_shop_item_list, proxy_conf=proxy_conf,
        user_agent='Mozilla/5.0 (iPhone; CPU iPhone OS 9_1 like Mac OS X) AppleWebKit/601.1.46 (KHTML, like Gecko) Version/9.0 Mobile/13B143 Safari/601.1'
    )
    network_sniffer.monitor()
}
