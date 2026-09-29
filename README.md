# ConfigGuideAgent

销售用一句话配单。系统查出标准方案和热推方案，写成逐步点击清单，再用代码核对型号有没有编造。

目录是 20 条合成 SKU，名称、规格和菜单都是教学数据，不是任何厂商的真实价格或菜单。热推是目录里标了热推的高毛利型号。`qty` 是采购台数。

情景记忆用 Qdrant 云集群，集合名固定为 `configguide_episodic`。对话模型、嵌入和 Qdrant 的键写在本目录 `.env`，或写在 Hello-Agents 仓库根目录的 `.env`。每一项是做什么的、哪条命令要用，见 `.env.example`。不要提交填好密钥的 `.env`。

case4 必须在新进程里跑。上一进程退出后，它仍要想起星海制造上次的产品线和数量，只把预算改成高，热推从 `SYN-PC-03` 换成 `SYN-PC-04`。

## 四条例的期望型号


| 用例                     | 标准方案      | 热推方案      |
| ---------------------- | --------- | --------- |
| case1，PC，预算中           | SYN-PC-02 | SYN-PC-03 |
| case2，Server，预算高，货期优先  | SYN-SV-02 | SYN-SV-04 |
| case2，Storage，预算高，货期优先 | SYN-ST-02 | SYN-ST-04 |
| case3，缺预算              | 无         | 无         |
| case4，沿用 case1，预算改为高   | SYN-PC-02 | SYN-PC-04 |


case3 只追问，不查目录，也不调用撰写和质检。

## 课程能力


| 章      | 在本项目中的组件                                                       |
| ------ | -------------------------------------------------------------- |
| 第 4 章  | `ReActAgent` 查证，`PlanAndSolveAgent` 写点击清单，`ReflectionAgent` 改稿 |
| 第 7 章  | `HelloAgentsLLM`、`ToolRegistry`、`ReActAgent.add_tool`          |
| 第 8 章  | `MemoryTool` 的工作记忆和情景记忆。配单成功后写入的是需求，不是型号                       |
| 第 9 章  | `ContextBuilder` 打上下文包。`NoteTool` 只存结论，质检不读笔记                  |
| 第 10 章 | 目录是 MCP。撰写在 5001，质检在 5002，Host 用 `A2ATool` 交接                  |
| 第 12 章 | 型号用代码精确匹配，不把反思稿当合格线                                            |


第 11 章的强化学习、语义记忆和 ANP 没有启用。

## 运行

在本目录、已安装依赖的环境中：

```bash
python main.py --check-only
python main.py --case case1
python main.py --case case4
python main.py
```

`a2a-sdk` 使用 0.2.16。更新的版本去掉了课程库要检查的导入，服务会起不来。