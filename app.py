import streamlit as st
import random
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm # 必须引入这个
import os

# --- 核心修复代码开始 ---
# 获取当前文件所在的文件夹路径
current_dir = os.path.dirname(os.path.abspath(__file__))
# 拼接字体文件的绝对路径 (假设字体文件叫 SimHei.ttf)
font_path = os.path.join(current_dir, 'SimHei.ttf')

# 检查字体文件是否存在
if os.path.exists(font_path):
    # 使用 matplotlib 的 font_manager 加载这个字体
    fm.fontManager.addfont(font_path)
    # 设置全局字体为这个文件名
    plt.rcParams['font.family'] = fm.FontProperties(fname=font_path).get_name()
else:
    # 如果没找到文件(比如本地运行没下载字体)，回退到系统默认
    # Windows/Mac/Linux 备选方案
    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'Microsoft YaHei', 'WenQuanYi Zen Hei']

plt.rcParams['axes.unicode_minus'] = False
# --- 核心修复代码结束 ---


# --- 1. 页面基础配置 ---
st.set_page_config(
    page_title="TFT 概率计算器 V3.0",
    page_icon="🧮",
    layout="wide"
)

# --- 2. 赛季数据配置 ---
SEASON_CONFIG = {
    "S13 (当前赛季)": {
        "POOL_SIZES": {1: 22, 2: 20, 3: 17, 4: 10, 5: 9}, 
        "DISTINCT_CHAMPS": {1: 13, 2: 13, 3: 13, 4: 12, 5: 8},
        "DROP_RATES": {
            6: {1: 0.25, 2: 0.40, 3: 0.30, 4: 0.05, 5: 0.00},
            7: {1: 0.19, 2: 0.30, 3: 0.35, 4: 0.15, 5: 0.01},
            8: {1: 0.18, 2: 0.25, 3: 0.36, 4: 0.18, 5: 0.03},
            9: {1: 0.10, 2: 0.20, 3: 0.25, 4: 0.35, 5: 0.10},
            10: {1: 0.05, 2: 0.10, 3: 0.20, 4: 0.40, 5: 0.25},
        }
    },
    "S11 (画之灵)": {
        "POOL_SIZES": {1: 22, 2: 20, 3: 17, 4: 13, 5: 10},
        "DISTINCT_CHAMPS": {1: 13, 2: 13, 3: 13, 4: 12, 5: 8},
        "DROP_RATES": {
            8: {1: 0.18, 2: 0.25, 3: 0.32, 4: 0.22, 5: 0.03},
            9: {1: 0.10, 2: 0.20, 3: 0.25, 4: 0.35, 5: 0.10},
        }
    }
}

# --- 3. 模拟核心逻辑 (精度升级) ---
def run_simulation(season_data, level, target_cost, current_gold, target_copies, 
                   target_taken_by_others, other_same_cost_taken, num_trials):
    
    rates = season_data["DROP_RATES"].get(level, {})
    if not rates:
        return "ERROR_LEVEL"

    # 1. 基础概率
    prob_cost_hit = rates.get(target_cost, 0) # D出一张卡是该费用的概率 (比如8级出4费=18%)
    
    # 2. 卡池参数计算
    one_card_total = season_data["POOL_SIZES"][target_cost] # 单张卡总数 (如4费卡每种10张)
    distinct_champs = season_data["DISTINCT_CHAMPS"][target_cost] # 该费用有多少种不同的卡 (如4费卡有12种)
    
    total_pool_size = one_card_total * distinct_champs # 该费用总卡池大小 (10 * 12 = 120张)
    
    # 3. 初始卡池状态 (静态扣除场外因素)
    # 分子：我要的卡还剩多少？
    start_remaining_target = one_card_total - target_taken_by_others
    if start_remaining_target < 0:
        return "ERROR_TARGET_LIMIT"
        
    # 分母：该费用卡池还剩多少？
    # 总池子 - 别人拿走的我的卡 - 别人拿走的其他的卡
    start_current_pool = total_pool_size - target_taken_by_others - other_same_cost_taken
    if start_current_pool <= 0:
        return "ERROR_POOL_LIMIT"

    results = []
    progress_bar = st.progress(0)
    
    for i in range(num_trials):
        if i % (num_trials // 10) == 0:
            progress_bar.progress(i / num_trials)
            
        copies_found = 0
        cost_spent = 0
        gold = current_gold
        
        # 每次模拟开始时，重置为初始卡池状态
        current_remaining_target = start_remaining_target
        current_pool = start_current_pool
        
        # 开始 D 牌
        while gold >= 2:
            gold -= 2
            cost_spent += 2
            
            # 商店刷新 5 个位置
            for _ in range(5):
                # 第一层判定：这次是否随机到了该费用 (比如是不是4费卡)
                if random.random() < prob_cost_hit:
                    # 第二层判定：在剩下的4费卡堆里，是不是我要的那张？
                    # 动态概率 = 剩余目标卡 / 剩余总卡池
                    real_time_prob = current_remaining_target / max(current_pool, 1)
                    
                    if random.random() < real_time_prob:
                        copies_found += 1
                        current_remaining_target -= 1 # 拿走一张，分子减1
                        current_pool -= 1         # 总池子减1
                        # 注意：如果是"D到但没买"，在真实TFT机制里是放回卡池的。
                        # 这里我们只统计"拿走"，即假设你只要看到就会买。
                        # 对于"D到了其他4费卡"，我们假设不买，所以不影响 current_pool (除非你考虑商店暂时移除机制，这里忽略微小误差)
            
            if copies_found >= target_copies:
                break
        
        results.append({"success": copies_found >= target_copies, "cost": cost_spent, "copies": copies_found})
    
    progress_bar.empty()
    return pd.DataFrame(results)

# --- 4. UI 前端布局 ---

st.title("🎲 金铲铲(TFT) 高精度卡池模拟器 V3.0")
st.markdown("""
<style>
.small-font {font-size:14px !important; color: gray;}
</style>
""", unsafe_allow_html=True)
st.caption("双重卡池变量算法 | 模拟同行互卡与清卡池效应")
st.divider()

# --- 侧边栏 ---
with st.sidebar:
    st.header("⚙️ 基础设置")
    selected_season_name = st.selectbox("赛季版本", list(SEASON_CONFIG.keys()), index=0)
    current_season_data = SEASON_CONFIG[selected_season_name]
    
    col_base1, col_base2 = st.columns(2)
    with col_base1:
        level = st.slider("当前等级", 6, 10, 8)
    with col_base2:
        gold = st.number_input("金币", 0, 200, 50, step=10)
    
    st.markdown("---")
    st.header("🎯 目标设定")
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        target_cost = st.selectbox("几费卡", [1, 2, 3, 4, 5], index=3)
    with col_t2:
        target_copies = st.selectbox("缺几张", [1, 2, 3, 4, 5, 6, 7, 8, 9], index=2)
        
    # 获取卡池上限用于校验
    max_single_card = current_season_data["POOL_SIZES"][target_cost]
    max_total_pool = max_single_card * current_season_data["DISTINCT_CHAMPS"][target_cost]
    
    st.markdown("---")
    st.header("🧮 场外卡池变量 (核心)")
    
    # 变量1：对我不利的
    st.markdown(f"**1. 竞争项 (别人拿了我的卡)** <span style='color:red'>[概率 ↓]</span>", unsafe_allow_html=True)
    target_taken = st.number_input(
        f"外面有几张我要的卡？(Max {max_single_card})", 
        min_value=0, max_value=max_single_card, value=0,
        help="比如你要阿狸，外面如果有一家2星阿狸，这里就填3。"
    )
    
    # 变量2：对我有利的
    st.markdown(f"**2. 干扰项 (别人拿了别的同费卡)** <span style='color:green'>[概率 ↑]</span>", unsafe_allow_html=True)
    # 估算上限：总卡池减去我要的那种卡的所有张数
    max_other_cards = max_total_pool - max_single_card
    other_taken = st.number_input(
        f"外面拿了多少张**其他** {target_cost} 费卡？", 
        min_value=0, max_value=max_other_cards, value=10, step=5,
        help=f"这是'清卡池'效应。该费用卡池共有 {max_total_pool} 张。如果外面几家都在玩4费卡，这里可能填 20~30。"
    )

    st.markdown("---")
    num_trials = st.selectbox("模拟次数", [1000, 5000, 10000], index=1)

# --- 主界面逻辑 ---
if st.button("🚀 运行蒙特卡洛模拟", type="primary", use_container_width=True):
    
    df = run_simulation(
        current_season_data, level, target_cost, gold, 
        target_copies, target_taken, other_taken, num_trials
    )
    
    # 错误处理
    if isinstance(df, str):
        if df == "ERROR_TARGET_LIMIT":
            st.error(f"❌ 数据冲突：该卡一共只有 {max_single_card} 张，外面已经有 {target_taken} 张了，不可能再搜到。")
        elif df == "ERROR_POOL_LIMIT":
            st.error("❌ 数据冲突：卡池已被抽干，请检查输入的'场外'卡牌数量。")
        elif df == "ERROR_LEVEL":
            st.error("❌ 配置缺失：当前赛季数据中没有该等级的概率配置。")
    elif not df.empty:
        success_rate = df["success"].mean()
        success_cases = df[df["success"] == True]
        avg_cost = success_cases["cost"].mean() if not success_cases.empty else 0
        
        # --- 结果展示面板 ---
        st.subheader("📊 模拟报告")
        
        # 1. 关键指标
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🎯 成功概率", f"{success_rate*100:.1f}%")
        c2.metric("💰 预期花费", f"{avg_cost:.0f} 金币")
        
        # 剩余卡量展示
        left_target = max_single_card - target_taken
        c3.metric("🃏 剩余目标卡", f"{left_target} 张", help="卡池里还剩几张阿狸")
        
        # 真实概率展示 (条件概率)
        current_pool_left = max_total_pool - target_taken - other_taken
        real_prob = (left_target / current_pool_left) if current_pool_left > 0 else 0
        base_rate = current_season_data["DROP_RATES"][level][target_cost]
        final_single_slot_prob = base_rate * real_prob
        
        c4.metric("🎲 单个格子真率", f"{final_single_slot_prob*100:.2f}%", 
                  help=f"计算公式：{level}级概率({base_rate}) × (剩余目标{left_target}/剩余池子{current_pool_left})")

        # 2. 图表
        st.markdown("#### 📉 资金分布图")
        if not success_cases.empty:
            fig, ax = plt.subplots(figsize=(10, 3))
            ax.hist(success_cases["cost"], bins=20, color='#0984e3', alpha=0.75, edgecolor='white')
            ax.set_xlabel("消耗金币")
            ax.set_ylabel("频次")
            ax.axvline(gold, color='#d63031', linestyle='--', linewidth=2, label=f'你的预算 ({gold})')
            ax.legend()
            st.pyplot(fig)
        else:
            st.warning("⚠️ 在所有模拟中，您一次都没有成功。这就是绝对的绝望。")
            
        # 3. 结论生成 (AI 分析员风格)
        st.info(f"""
        **💡 量化分析结论：**
        在 {level} 级 D {target_cost} 费卡的场景下：
        * 由于外面有 **{other_taken} 张** 同费杂卡被拿走，你的搜牌概率获得了 **{'提升' if other_taken > 0 else '无变化'}**。
        * 由于外面有 **{target_taken} 张** 你的核心卡被拿走，你的卡池剩余仅 **{left_target} 张**。
        * 综合来看，每一个商店格子出现你要的卡的真实概率约为 **{final_single_slot_prob*100:.2f}%**。
        """)

    else:

        st.error("未知错误，请检查参数。")
