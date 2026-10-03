---
research_classification: diagnostic_topic
---

# batch009 六ID离线恢复入口

本主题补充可公开、无行情的恢复配方；不是新研究运行、远端备份或Library保存成功。恢复对象为M0311、M0302、M0305、M0306、M0307、M0300，均为已有2024诊断窗口的ADAPTED_EXECUTION_PROXY，PIT未知、非OOS、未晋升。

现有私有完整包及其清单保持原样。公开Git只有代码与轻量预期指纹，不能替代用户合法持有的原始snapshot、原源码和依赖环境；若这些缺失，入口会阻塞，没有在线获取、代理、换源或自动安装。

- [轻量入口](scripts/restore_offline.py)
- [输入、源码、代码及88结果预期指纹](specs/expectations.json)
- [本次非历史验证](specs/wrapper-validation.json)
- [完整私有包逻辑映射](specs/package-member-map.json)
- [决策记录](decision-log.md)

## 固定环境与输入

代码基线为`eca7ad8e`完整commit见expectations.json。使用该基线加本恢复topic的固定Git checkout；入口逐项核81份既有代码/规格和6份原恢复回执的哈希，不改共享v1或各策略冻结代码。

Python **3.12.14**；numpy **2.3.5**，pandas **2.2.3**，TA-Lib Python **0.6.8**/原生库 **0.6.4**，freqtrade **2026.9**，technical **1.7.0**，ft-pandas-ta **0.3.16**。TA compatibility=0、EMA unstable=0。完整安装版本锁见[M0311 requirements](../M0311/specs/requirements.lock.txt)。只有用户已有合法离线wheel/source环境可用于事先安装；完整离线从空机器安装未验证。版本不可用时停在DEPENDENCY_BLOCKED，不放宽版本、不访问网络、不自动安装。

snapshot目录必须包含原manifest `fb84e080…c058`、13个月×CHECKSUM/ZIP/CSV共39文件及canonical CSV。后者SHA `91e5bb0b…0af2`、31428289B、114336行。原相对路径及完整SHA见expectations；单凭同CSV不接受另一capture manifest。本入口不采用其他批次的capture兼容addendum。

sources目录由用户从已合法持有资料组成扁平目录，包含expectations.sources列明14个原文件。完整包中这些来自`shared/sources/M0311/`的8文件和`shared/sources/batch009/`中的5策略与qtpylib.py；可在自己的私有目录保留两目录的完整许可说明后合并文件，文件名不冲突。GPL/Apache来源仅记录固定URL/hash，入口不重新分发或下载源码；各原目录LICENSE及消费者ATTRIBUTION仍须保留。原始行情与派生输出依原许可私用，不因恢复成功获得公开传播许可。

## 精确命令

从固定checkout根目录，使用已经满足上述锁定依赖的Python运行。替换三个用户自备路径；output父目录须存在、output本身不存在且位于Git外。

```sh
python research/public-strategies/batch009-offline-recovery-20261003/scripts/restore_offline.py \
  --snapshot /path/to/lawfully-held/snapshot \
  --sources /path/to/lawfully-held/combined-sources \
  --output /path/to/private/new-recovery \
  --preflight-only
```

预检只检查原输入/源代码/冻结代码/依赖，不生成目标目录，也不运行策略。预检通过后删除`--preflight-only`参数执行恢复。不要用Python `-O`，既有验证器使用assert。起始须>6GiB空闲；逐ID再检查并留>5GiB。失败保留新目录证据，不覆盖或删除旧运行。

完整恢复依次：复制固定41个snapshot文件到新输出目录；仅调用一次既有M0311 audit_input，从39原对象校验checksum/CRC/UTC/OHLCV并重建canonical；调用六ID各自既有入口；调用原独立账户oracle；要求全部88结果文件名、字节数、SHA与公开恢复回执一致。M0311保留冻结四策略配置+一个buyhold（18结果文件）；其余五ID各四配置（各14文件），合计24策略配置+1已有控制的恢复，不计新试验。子进程禁用socket connect/connect_ex，无第三方自动安装。

M0311调用原类/CMF对照；五ID的run入口自身对照原类信号与独立Boolean。未额外重做全套因果前缀/源码审计；已有证据按原hash保留。独立oracle仍有各自文档列明的字段覆盖边界，本主题不提升其保证。

## 本次实际验证边界

--help、错误manifest hash、缺输入拒绝、实际输入/源/锁定依赖预检通过；另一个缺freqtrade的环境真实被DEPENDENCY_BLOCKED拒绝，没有安装。88份已有fresh-restore结果重新读取后与预期hash一致。本次**没有运行六ID engine、没有再次执行输入QA重建**；新wrapper端到端全流程尚未新跑，恢复步骤沿用之前已通过的冻结入口，不能将本次预检称为新全流程恢复成功。
