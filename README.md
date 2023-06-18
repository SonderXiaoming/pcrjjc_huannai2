## 警告：本插件代码质量很差，介意请使用其他版本，欢迎大佬改了pr。

## 自动过码问题建议直接找路路

## 未经大量测试，有任何bug，正规群/hoshino群找一个叫雨中流浪汉的狗头或者提issue(最好直接pr)

## 配置方法

### 安装前置插件[multicq_send](https://github.com/SonderXiaoming/multicq_send)

在hoshino的modules文件夹放着就行，不需要开启或加载

### 对于b服和渠道服

在account文件夹中按照模板改一下account.json

渠道服自行抓包，有空可能写类似台服读xml，最好有人pr

### 对于台服

把data/data/tw.sonet.princessconnect/shared_prefs/tw.sonet.princessconnect.v2.playerprefs.xml复制到account文件夹中

对于多个文件只需要重命名即可，确保xml后缀即可

最好台一和二三四都有一个确保功能完整

仅支持新版xml，旧版重获取（我新插件为什么要管历史包袱）

### 你可能需要的额外配置

client里面api.json设置自动过码api，不然b服没法用（原版手动过码不适合多服，你直接cv原版的过码应该勉强能用，等pr。懒得搞）

client里面proxy.json设置代理，不然台服可能被墙

var.py里面BaseSet设置私聊上限

### 基本说明：

没有requirements，等pr，自行装到没报错为止，我不太清楚你们缺什么

数据储存在database里面的db文件

tool.py作为初始化数据库，有兴趣可以自行查看，比如导入旧版的绑定之类的小功能，自行使用

## 功能：

1）自动过验证码

2）每个人可以绑定多个uid

3）每个uid可以设置不同的推送内容

4）多服支持

#### 6）大部分指令仅支持群聊，支持私聊/群聊推送。

## 指令（台服前面加台，渠道服前面加渠）：

![`(PO411}PP~PZR~}6 J4(99_tmb](https://github.com/SonderXiaoming/pcrjjc_huannai2/assets/98363578/c843c181-7496-4f1c-9e5d-6b02df868308)

# TODO：（等pr）

1. 代码优化，之前以为四个服务器合一块的，谁知道台一不变。后来临时加了许多垃圾代码，有人急着要

2. requirements文件
3. 渠道服xml支持（懒得写了，我会是会，不如直接抓包方便）
4. b服手动过码（应该写成类似gocq的形式，自动上传，有多少个号就滑多少次，和bot私聊需要等超时加锁之类的并不方便，听说cq还有私聊bug）
5. 有没有大佬能搞日服（好像说几乎不可能）

## 特别感谢

**[cc004](https://github.com/cc004/pcrjjc2/commits?author=cc004)**的**[pcrjjc2](https://github.com/cc004/pcrjjc2)**b服支持

**[azmiao](https://github.com/azmiao/pcrjjc_tw_new/commits?author=azmiao)**的**[pcrjjc_tw_new](https://github.com/azmiao/pcrjjc_tw_new)**台服支持

渠道抄的露娜来着，找不到了，寄，渠道服支持

**[Syne-lucky](https://github.com/Syne-lucky/pcrjjc2/commits?author=Syne-lucky)**的**[pcrjjc2](https://github.com/Syne-lucky/pcrjjc2)**指令参考

**[Mira19971102](https://github.com/Mira19971102)**台服账号提供

