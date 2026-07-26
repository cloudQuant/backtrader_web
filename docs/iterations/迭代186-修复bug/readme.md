1. http://localhost:3000/data/quote

- 这个里面实时数据在CTP, IB, MT5等网关之间切
  换，耗费时间太多了，尝试切换的时候先显示一部分，比如代码和名称

- 打开图标和删除订阅这两个列已经有名字了，下面只需要图标就行了，不需要继续把名字也加上

- 下现在缺少最低价，最高价等数据，只需要最新价，买价和卖价，代码，名称，分类，更新时间这几个字段即可

- 数据源状态变成一个按钮，点击之后，显示这些内容

- 把数据源状态里面的CTP, IB, MT5等网关，直接移动到行情报价这一行，节省空间

2. http://localhost:3000/data/market

- 这个每个分类下面的类似 `股票行情与估值`这个内容和市场数据工作台重复了，可以尝试把这些内容修改一下，移动到市场数据工作台中；分析一下如何移动比较好，按照行业最佳实践来。

3. http://localhost:3000/investment/strategies

这个页面点击的时候报错：

Request URL
http://localhost:3000/api/v1/strategy/?limit=20&offset=0
Request Method
GET
Status Code
422 Unprocessable Content
Remote Address
127.0.0.1:3000
Referrer Policy
strict-origin-when-cross-origin

Request URL
http://localhost:3000/api/v1/strategy/ai-research/runs?limit=50
Request Method
GET
Status Code
422 Unprocessable Content
Remote Address
127.0.0.1:3000
Referrer Policy
strict-origin-when-cross-origin

4. http://localhost:3000/ai/chat

写一个脚本，放到scripts中，实现爬取这个网站的几百篇文章
https://yunjinqi.top/

然后把这几百篇文章，做成一个知识库，让这里面里面的知识库能够加载这些文章，并且能够用这些文章支持问答


