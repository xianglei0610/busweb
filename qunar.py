# coding: utf-8
import numpy as np
from pandas import DataFrame
import pandas as pd

#file_list = ["1512.xlsx","1601.xlsx","1602.xlsx","1603.xlsx","1604.xlsx","1605.xlsx","1606.xlsx","1607.xlsx","1608.xlsx","1609.xlsx","1610.xlsx"]
file_list = ["1512.xlsx"]
data = pd.concat([pd.ExcelFile("qunar/%s" % n).parse("sheet1") for n in file_list], ignore_index=True)

# 增加列：’业务线订单2’
data_small = DataFrame(data, columns=[ u"业务线订单号",u"业务线订单号2", u"支付流水号",u"入账金额",u"出账金额", u"订单金额", u"账务类型"])
data_small[data_small[u"账务类型"].isin([u"一次解冻入账", u"现金到退款出账", np.nan])]
data_small[u"业务线订单号2"]=data_small[u"支付流水号"].map(lambda s: s.replace("qcoach", "12308q")[:21])
del data_small[u"支付流水号"]

# 手续费单子
data_fee=data_small[data_small[u"账务类型"].isnull()]
c1 = len(data_fee)
c2 = len(data_fee.groupby(u"业务线订单号2").sum())
print "手续费单，去重前:%s, 去重后:%s" % (c1, c2)
print "手续费单，入账金额不等于订单金额数量: %s" % len(data_fee[data_fee[u"入账金额"]!=data_fee[u"订单金额"]])
data_fee = data_fee[[u"业务线订单号2",u"入账金额"]]
data_fee.rename(columns={u"入账金额":u"入账手续费"}, inplace=True)

# 一次性入账单子
data_once=data_small[data_small[u"账务类型"]==u"一次解冻入账"]
c1 = len(data_once)
c2 = len(data_once.groupby(u"业务线订单号2").sum())
print "一次入账单，去重前:%s, 去重后:%s" % (c1, c2)
# 确认出账金额都为空
print "一次入账单，出账金额数量: %s" % len(data_once.groupby(u"出账金额").count())
data_once=data_once[[u"业务线订单号2",u"入账金额", u"订单金额"]]

# 退款单子
data_back=data_small[data_small[u"账务类型"]==u"现金到退款出账"]
c1 = len(data_back)
data_back=data_back.groupby(u"业务线订单号2").sum().reset_index()
c2 = len(data_back)
print "退款单，去重前:%s, 去重后:%s" % (c1, c2)
data_back=data_back[[u"业务线订单号2",u"出账金额"]]

# 合并生成新的表
data_new=pd.merge(pd.merge(data_fee, data_once, on=u"业务线订单号2", how="outer"), data_back, on=u"业务线订单号2", how="outer")
trans_name = {
    u"业务线订单号2": u"去哪儿订单号",
    u"入账手续费":u"q入账手续费",
    u"入账金额": u"q入账金额",
    u"订单金额": u"q订单金额",
    u"出账金额":u"q出账金额"
}
data_new.rename(columns=trans_name, inplace=True)
data_new[:5]


# 读取mis后台数据
#file_list = ["%s.xls" % i for i in range(1, 9)]+["%s.xlsx" % i for i in range(9, 12)]
file_list = ["%s.xls" % i for i in range(1, 2)]+["%s.xlsx" % i for i in range(9, 9)]
mis_data = pd.concat([pd.read_excel("mis/%s" % n, header=1, sheetname=0) for n in file_list], ignore_index=True)

# 裁剪，重命名列名
columns =[u"第三方订单号",u"订单号",u"票价", u"手续费",u"下单日期"]
mis_data_small = DataFrame(mis_data, columns=columns)
mis_data_small[u"第三方订单号"]=mis_data_small[u"第三方订单号"].map(lambda s: s[:21])
trans_name={u"订单号":u"h订单号",u"第三方订单号":u"去哪儿订单号",u"票价":u"h票价", u"手续费":u"h手续费", u"下单日期":u"h下单日期"}
mis_data_small.rename(columns=trans_name, inplace=True)
mis_data_small[u"h下单日期"]=mis_data_small[u"h下单日期"].str[:10]

mis_data_new = mis_data_small.groupby([u"去哪儿订单号", u"h订单号", u"h下单日期"]).sum().reset_index()
print "去重后%s to %s" % (len(mis_data_small), len(mis_data_new))
mis_data_new[:5]


# 合并mis后台和去哪儿数据
result = pd.merge(mis_data_new, data_new, on=u"去哪儿订单号", how="outer")
result.fillna(0, inplace=True)
result[:5]


result.to_excel("result.xlsx")

