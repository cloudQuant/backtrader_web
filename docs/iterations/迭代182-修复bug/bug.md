1. http://localhost:3000/data/intelligence/equity 这个里面并不是使用的真实的数据，更像是模拟的mock数据，改成真实的数据，没有数据就空着
2. http://localhost:3000/research/strategies 这个里面并没有显示我现在项目中存在的100多个策略工具
3. http://localhost:3000/trading/brokers 这个功能和http://localhost:3000/trading/gateways这个功能似乎冲突了，前面的broker配置功能在项目的其他地方有使用到吗？如果没有使用，就删除掉
4. http://localhost:3000/trading/ai 这个里面选择不了账户，应该把模拟账户改为账户，另外只要是账户管理里面已经连接的账户都可以选择。
5. 应该把http://localhost:3000/trading/gateways这个给放到配置中心
6. 组合管理里面组合账本这个页面不需要了，模拟交易和实盘交易也不需要了，而是显示交易运营里面的运行着的工作区，当选中这些工作区的时候，会把这些工作区中的持仓和交易添加到组合里面；增加一个仪表盘功能，把原先组合账本里面计算的指标添加到这个仪表盘中。
7. http://localhost:3000/data/intelligence/scanners 这个里面的结果明细并不需要，把结果明细这个给删除
8. 把http://localhost:3000/data/market这个数据管理改成数据查询，除了股票、期货之外，增加债券，基金，外汇，数字货币等，把http://localhost:3000/data/intelligence/options这个作为数据查询的一个tab子页面，就不需要一个单独的期权链了，改成期权。并根据现有的数据表，显示具体的数据。主要是作为数据展示