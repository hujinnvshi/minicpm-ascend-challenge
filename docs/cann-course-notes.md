# CANN NEXT 算子编程必修课 - 官方 QA 笔记（2026-08-01）

> 来源：gitcode.com/org/cann/discussions/62（课程直播 QA 汇总，专家回答）
> 课程系列：《面向下一代硬件的算子编程必修课（Ascend C）》2026-03-02~03-06 直播
> 视频归档（B 站）：
> - Ascend C 算子编程概述：BV12fAdzcEDe
> - SIMT 编程介绍：BV1zNPwzaEeB
> - Reg 矢量编程、SIMD&SIMT 混合编程：BV1uPPvzGEnt
> - Cube 编程：BV118P1zPESw
> - 编译与调试调优能力概述：BV15AP8zqEme
> - 下一代架构变与不变：BV1LAw7zwEnt
> 直播 PPT：gitcode.com/cann/community/tree/master/events/meetup/slides/sig-ascendc/20260302-20260306

## 一、硬件规格（官方确认）

- **910B 不支持 SIMT，下一代芯片（950）才开始支持** —— 910C 同属当前代，也不支持 SIMT！
- AIV 数量：物理 64 个/卡，每个 AIV 只有 1 个矢量计算单元
  （同一时刻要么执行 SIMD 模式，要么 SIMT 模式）
- SIMT VF 逻辑上 = 1 个 Thread Block，最大 2048 线程（线程数用户可指定）
- SIMD Reg 物理寄存器：32 个；SIMT 与 SIMD 的 reg file 物理独立（两套）
- UB（统一缓冲区）：950 比 910B 大幅提升——可缓存更多数据，减少 GM↔UB 传输
- 参数传递寄存器开销约 100Byte，超出影响性能
- ssbuffer：3K，不需 32 对齐
- AICPU ≠ AI Core 内 scalar 单元（AICPU 与 AICore 是并列单元）

## 二、SIMT vs SIMD 适用场景（官方定义）

| 模式 | 适合场景 | 特点 |
|---|---|---|
| SIMT | 离散内存访问（gather/scatter）、复杂分支判断 | 易用性高，新手友好；类 CUDA |
| SIMD | 连续密集计算（elementwise） | 计算效率更高，指令双发/高带宽连续传输 |
| 混合 | 融合算子里两者可同时存在 | SIMT 处理离散段 + SIMD 处理密集段 |

- Cube（矩阵）不加 SIMT：矩阵是大块连续数据计算，没必要
- 虽然 SIMD/SIMT 共享 ALU，但 GM/UB 访问效率、寄存器规格、指令发射均不同
- VF 之间只能通过 UB 交换数据（reg 不能跨 VF 驻留，寄存器由编译器自动分配）
- GM 数据不能直接与 SIMD Reg 搬运，必须经过 UB
- 当代（910B/910C）gather API 不是 SIMT 机制（当代不支持 SIMT）
- 当代 Ascend C 基础 API 内部实现在下一代将用 reg 矢量计算重写

## 三、调试调优

- mssanitizer 可一把检查所有内存和竞争：
  mssanitizer --tool=memcheck --tool=racecheck ./application
- block dim = 计算该算子用到的核数

## 四、对比赛的意义（关键结论）

1. **910C 无 SIMT**：比赛环境（910C + CANN 9.1.0-beta1）的算子执行是传统
   SIMD/Cube 模式——不需要考虑 SIMT 对 llama.cpp-omni 的影响
2. **950 算力预演注意**：若通过 CANN 社区任务拿到 950 环境，其算子行为
   （SIMT 支持 + 更大 UB）与 910C 有代差，性能数字参考性低于 910B
   ——950 预演价值 = 工具链/脚本/流程验证，正式数据仍需 910C
3. mssanitizer 可用于 950 环境的内存/竞争调试
4. 理解 SIMD/UB/寄存器层次 = 读懂 msprof 报告和图模式行为的基础
