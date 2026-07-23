# -*- coding: utf-8 -*-
# ============================================
# 华润江中 (600750.XSHG) — 双均线金叉死叉策略
# 平台: JoinQuant (聚宽)
# 功能: 成交量过滤 + 止损止盈 + 风险监控
# ============================================

from jqdata import *


def initialize(context):
    # ======== 1. 基本设置 ========
    set_benchmark('000300.XSHG')           # 沪深300基准
    set_option('use_real_price', True)     # 开启动态复权（真实价格）
    log.info('========== 华润江中双均线策略启动 ==========')

    # ======== 2. 手续费设置 ========
    set_order_cost(
        OrderCost(
            close_tax=0.001,               # 卖出印花税 千分之一
            open_commission=0.0003,         # 买入佣金 万分之三
            close_commission=0.0003,        # 卖出佣金 万分之三
            min_commission=5                # 最低佣金 5元
        ),
        type='stock'
    )

    # ======== 3. 策略参数（可调） ========
    g.security = '600750.XSHG'             # 华润江中
    g.short_ma = 5                         # 短期均线周期
    g.long_ma = 20                         # 长期均线周期
    g.lookback = 60                        # 获取数据的长度（必须大于 long_ma）
    g.stop_loss = 0.08                     # 止损比例 8%
    g.take_profit = 0.20                   # 止盈比例 20%

    # ======== 4. 定时运行 ========
    run_daily(before_market_open, time='before_open', reference_security=g.security)
    run_daily(market_open, time='open', reference_security=g.security)
    run_daily(after_market_close, time='after_close', reference_security=g.security)


# ==========================================================
# 阶段1: 盘前准备
# ==========================================================
def before_market_open(context):
    log.info(f'华润江中 | 当前时间: {context.current_dt}')
    log.info(f'当前参数: MA{g.short_ma} × MA{g.long_ma} | 止损{g.stop_loss:.0%} | 止盈{g.take_profit:.0%}')


# ==========================================================
# 阶段2: 开盘执行（核心逻辑）
# ==========================================================
def market_open(context):
    security = g.security
    lookback = g.lookback

    # ---- 2.1 获取行情数据 ----
    bars = get_bars(security, count=lookback, unit='1d',
                    fields=['close', 'volume', 'high', 'low'],
                    include_now=True)

    if bars is None or len(bars) < g.long_ma:
        log.warn('数据不足，跳过本次交易')
        return

    close = bars['close']
    volume = bars['volume']
    current_price = close[-1]

    # ---- 2.2 计算技术指标 ----
    ma_short = close[-g.short_ma:].mean()   # 短期均线
    ma_long = close[-g.long_ma:].mean()     # 长期均线
    vol_ma_short = volume[-g.short_ma:].mean()
    vol_ma_long = volume[-g.long_ma:].mean()

    prev_close = close[-2]
    prev_ma_short = close[-(g.short_ma+1):-1].mean()

    # 成交量确认：短期均量 > 长期均量（放量）
    volume_confirm = vol_ma_short > vol_ma_long

    # ---- 2.3 获取持仓和现金 ----
    position = context.portfolio.positions.get(security, None)
    cash = context.portfolio.available_cash
    current_value = context.portfolio.portfolio_value

    # 记录日志
    log.info(f'华润江中 | 现价={current_price:.2f} '
             f'MA{g.short_ma}={ma_short:.2f} MA{g.long_ma}={ma_long:.2f} '
             f'放量确认={volume_confirm}')

    # ---- 2.4 买入信号：金叉（短线上穿长线 + 放量确认） ----
    # 前一天短均线 <= 长均线，今天短均线 > 长均线 → 上穿
    if prev_ma_short <= ma_long and ma_short > ma_long and volume_confirm:
        if cash > 1000:  # 至少留1000元不交易
            available_cash = cash * 0.95   # 95%仓位，留5%现金
            order_value(security, available_cash)
            log.info(f'✅ 金叉买入 | 价格={current_price:.2f} '
                     f'MA{g.short_ma}={ma_short:.2f} MA{g.long_ma}={ma_long:.2f} '
                     f'买入金额={available_cash:.0f}')

    # ---- 2.5 卖出信号：死叉（短线下穿长线） ----
    elif prev_ma_short >= ma_long and ma_short < ma_long:
        if position and position.closeable_amount > 0:
            order_target(security, 0)
            log.info(f'🔴 死叉卖出 | 价格={current_price:.2f} '
                     f'MA{g.short_ma}={ma_short:.2f} MA{g.long_ma}={ma_long:.2f}')

    # ---- 2.6 止损止盈（持有中） ----
    if position and position.closeable_amount > 0:
        cost = position.avg_cost
        pnl_pct = (current_price - cost) / cost
        
        if pnl_pct <= -g.stop_loss:
            order_target(security, 0)
            log.info(f'🛑 止损触发 | 成本={cost:.2f} 现价={current_price:.2f} '
                     f'亏损={pnl_pct:.2%}')
        
        elif pnl_pct >= g.take_profit:
            order_target(security, 0)
            log.info(f'💰 止盈触发 | 成本={cost:.2f} 现价={current_price:.2f} '
                     f'盈利={pnl_pct:.2%}')


# ==========================================================
# 阶段3: 收盘后（风险记录）
# ==========================================================
def after_market_close(context):
    security = g.security
    total_value = context.portfolio.portfolio_value
    stock_value = context.portfolio.positions_value
    cash = context.portfolio.available_cash
    stock_ratio = stock_value / total_value if total_value > 0 else 0

    log.info('--- 收盘后风险监控 ---')
    log.info(f'总资产: {total_value:.2f}')
    log.info(f'持仓市值: {stock_value:.2f} (仓位占比: {stock_ratio:.1%})')
    log.info(f'可用现金: {cash:.2f}')
    
    # 单只股票集中度检查
    position = context.portfolio.positions.get(security, None)
    if position and position.value > 0:
        exposure = position.value / total_value
        log.info(f'华润江中集中度: {exposure:.1%}')
        if exposure > 0.9:
            log.warn(f'⚠️ 仓位过重！集中度 = {exposure:.1%}')
    
    # 当日成交记录
    trades = get_trades()
    for trade in trades.values():
        log.info(f'成交记录: {trade}')

    log.info('========== 交易结束 ==========\n')
