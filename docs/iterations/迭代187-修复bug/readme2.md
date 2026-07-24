1. 市场数据中报错：部分数据源不可用
akshare_data 查询失败: (pymysql.err.OperationalError) (1044, "Access denied for user 'backtrader_web'@'127.0.0.1' to database 'akshare_data'") (Background on this error at: https://sqlalche.me/e/20/e3q8)  你需要修复这个问题；


2.
 http://localhost:3000/trading/b9e23899-eaad-4dd6-a973-ac47196f86a5 这个里面显示的有50个策略单元，这个不能很快看到，卡了很久才能看到，修复一下，点击运行的时候，并不能运行成功，显示超时，并且把这个工作区和mt5工作区运行成功

 3. http://localhost:3000/trading 这个页面也需要很久才能打开，分析一下打开慢的原因并修复，在ubuntu上基本上很快就打开了

 4. http://localhost:3000/portfolio 这个页面也是，打开很卡，在ubuntu上也是很快就打开了，分析原因并修复

 5. http://localhost:3000/investment/strategies 这个里面，选择方案之后会报错，比如日内均衡投研，报错，请求失败，修复一下

 6. http://localhost:3000/ai/chat  这个生成问题报错，修复一下，默认模型记得改为豆包的GLM5.2, 另外需要验证一下这些常见的问题能够修复成功。现在报错：你好，你是什么模型？An unexpected error occurred. Please contact support if the problem persists. (request_id: aea730ca)  这个知识库主要包含哪些内容？ 未找到相关内容，请先确认知识库已建立索引且问题与文档内容相关。

未找到相关上下文
未找到相关内容，请先确认知识库已建立索引且问题与文档内容相关
