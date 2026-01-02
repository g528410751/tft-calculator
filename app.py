import streamlit as st
import random
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import os
import platform
from openai import OpenAI

# --- 0. 基础环境配置 & 字体修复 ---
# 尝试修复中文乱码 (兼容云端/本地)
system_name = platform.system()
current_dir = os.path.dirname(os.path.abspath(__file__))
font_path = os.path.join(current_dir, 'SimHei.ttf')

if os.path.exists(font_path):
    fm.fontManager.addfont(font_path)
    plt.rcParams['font.family'] = fm.FontProperties(fname=font_path).get_name()
else:
    if system_name == 'Windows':
        plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
    elif system_name == 'Darwin':
        plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'Heiti TC']
    else:
        plt.rcParams['font.sans-serif'] = ['WenQuanYi Zen Hei']
plt.rcParams['axes.unicode_minus'] = False

st.set_page_config(page_title="TFT 概率计算器 S16/S10", page_icon="🎲", layout="wide")

# --- 1. 赛季核心数据配置 (已根据CSV更新) ---
SEASON_CONFIG = {
    "S16 (英雄联盟传奇 - 任务赛季)": {
        "POOL_SIZES": {1: 30, 2: 25, 3: 18, 4: 10, 5: 9},
        "DISTINCT_CHAMPS": {1: 14, 2: 19, 3: 18, 4: 25, 5: 24}, # 包含未解锁的总数
        "DEFAULT_LOCKED": {1: 0, 2: 6, 3: 5, 4: 13, 5: 16},    # 默认锁住的数量(来自CSV)
        "DROP_RATES": {
            1: {1: 1.00, 2: 0.00, 3: 0.00, 4: 0.00, 5: 0.00},
            2: {1: 1.00, 2: 0.00, 3: 0.00, 4: 0.00, 5: 0.00},
            3: {1: 0.75, 2: 0.25, 3: 0.00, 4: 0.00, 5: 0.00},
            4: {1: 0.55, 2: 0.30, 3: 0.15, 4: 0.00, 5: 0.00},
            5: {1: 0.45, 2: 0.33, 3: 0.20, 4: 0.02, 5: 0.00},
            6: {1: 0.30, 2: 0.40, 3: 0.25, 4: 0.05, 5: 0.00},
            7: {1: 0.19, 2: 0.30, 3: 0.40, 4: 0.10, 5: 0.01},
            8: {1: 0.15, 2: 0.20, 3: 0.32, 4: 0.30, 5: 0.03},
            9: {1: 0.12, 2: 0.18, 3: 0.25, 4: 0.33, 5: 0.12},
            10: {1: 0.05, 2: 0.10, 3: 0.20, 4: 0.40, 5: 0.25},
        }
    },
    "S10 (强音对决 - 怀旧服)": {
        "POOL_SIZES": {1: 30, 2: 25, 3: 18, 4: 12, 5: 10},
        "DISTINCT_CHAMPS": {1: 13, 2: 13, 3: 13, 4: 13, 5: 11},
        "DEFAULT_LOCKED": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}, # S10无锁定机制
        "DROP_RATES": {
            1: {1: 1.00, 2: 0.00, 3: 0.00, 4: 0.00, 5: 0.00},
            2: {1: 1.00, 2: 0.00, 3: 0.00, 4: 0.00, 5: 0.00},
            3: {1: 0.75, 2: 0.25, 3: 0.00, 4: 0.00, 5: 0.00},
            4: {1: 0.55, 2: 0.30, 3: 0.15, 4: 0.00, 5: 0.00},
            5: {1: 0.45, 2: 0.33, 3: 0.20, 4: 0.02, 5: 0.00},
            6: {1: 0.30, 2: 0.40, 3: 0.25, 4: 0.05, 5: 0.00},
            7: {1: 0.19, 2: 0.35, 3: 0.35, 4: 0.10, 5: 0.01},
            8: {1: 0.18, 2: 0.25, 3: 0.36, 4: 0.18, 5: 0.03},
            9: {1: 0.10, 2: 0.20, 3: 0.25, 4: 0.35, 5: 0.10},
            10: {1: 0.05, 2: 0.10, 3: 0.20, 4: 0.40, 5: 0.25},
        }
    }
}

# --- 2. 核心模拟逻辑 ---
def run_simulation(season_data, level, target_cost, current_gold, target_copies, 
                   target_taken, other_taken, num_trials, locked_types_count=0):
    
    rates = season_data["DROP_RATES"].get(level, {})
    if not rates:
        return "ERROR_LEVEL"

    prob_cost_hit = rates.get(target_cost, 0)
    
    # 获取该费用基础数据
    one_card_total = season_data["POOL_SIZES"][target_cost]
    total_distinct_champs = season_data["DISTINCT_CHAMPS"][target_cost]
    
    # [关键逻辑] 计算有效的卡种数量 = 总种类 - 锁住的种类
    effective_distinct_champs = total_distinct_champs - locked_types_count
    
    if effective_distinct_champs <= 0:
        return "ERROR_ALL_LOCKED" 

    # 总卡池大小 (分母) = 单张数量 * 有效种类
    total_pool_size = one_card_total * effective_distinct_champs
    
    # 初始卡池状态
    start_remaining_target = one_card_total - target_taken
    if start_remaining_target < 0:
        return "ERROR_TARGET_LIMIT"
        
    start_current_pool = total_pool_size - target_taken - other_taken
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
        
        current_remaining_target = start_remaining_target
        current_pool = start_current_pool
        
        while gold >= 2:
            gold -= 2
            cost_spent += 2
            
            for _ in range(5): # 商店5个位置
                if random.random() < prob_cost_hit: # 1. 命中费用
                    # 2. 命中具体卡片 (基于动态卡池)
                    real_time_prob = current_remaining_target / max(current_pool, 1)
                    
                    if random.random() < real_time_prob:
                        copies_found += 1
                        current_remaining_target -= 1
                        current_pool -= 1
            
            if copies_found >= target_copies:
                break
        
        results.append({"success": copies_found >= target_copies, "cost": cost_spent})
    
    progress_bar.empty()
    return pd.DataFrame(results)

# --- 3. UI 布局 ---
st.title("🎲 金铲铲(TFT) 量化计算器")
st.caption("*> 基于蒙特卡洛算法模拟 1000 次D牌结果，拒绝玄学，相信数学。*")
st.divider()

# 侧边栏
with st.sidebar:
    st.header("🤖 AI 教练 (可选)")
    # 优先从 Secrets 读取，否则允许手动输入
    if "DEEPSEEK_API_KEY" in st.secrets:
        api_key = st.secrets["DEEPSEEK_API_KEY"]
        st.success("已连接开发者密钥")
    else:
        api_key = st.text_input("DeepSeek API Key", type="password")

    st.markdown("### 模型选择")
    model_choice = st.radio(
        "选择大脑类型:",
        ("DeepSeek-R1 (深度思考)", "DeepSeek-V3 (极速响应)"),
        index=0,
        help="R1 会展示思考过程，适合复杂分析；V3 速度极快，适合快速给建议。"
    )
    # 映射为真实的 API 模型名称
    selected_model = "deepseek-reasoner" if "R1" in model_choice else "deepseek-chat"
    
    st.markdown("---")
    st.header("⚙️ 游戏设置")
    
    # 1. 赛季选择
    selected_season_name = st.selectbox("选择赛季", list(SEASON_CONFIG.keys()), index=0)
    current_season_data = SEASON_CONFIG[selected_season_name]
    
    col1, col2 = st.columns(2)
    with col1:
        level = st.slider("当前等级", 3, 10, 8)
    with col2:
        gold = st.number_input("金币", 0, 200, 50, step=10)
        
    st.markdown("---")
    st.header("🎯 目标卡片")
    c_t1, c_t2 = st.columns(2)
    with c_t1:
        target_cost = st.selectbox("几费卡", [1, 2, 3, 4, 5], index=3)
    with c_t2:
        target_copies = st.selectbox("缺几张", [1, 2, 3, 4, 5, 6, 7, 8, 9], index=2)

    # --- S16 专属逻辑：解锁数量 ---
    locked_types = 0 # 最终传给后台计算的“不在卡池里的卡种数”
    
    # 获取该费用的总卡种数
    total_types = current_season_data["DISTINCT_CHAMPS"][target_cost]
    # 获取默认被锁住的数量 (即 S16 的任务卡数量)
    default_locked_count = current_season_data["DEFAULT_LOCKED"].get(target_cost, 0)
    
    if default_locked_count > 0 or "S16" in selected_season_name:
        # 计算基础卡数量 (不用解锁就在池子里的)
        base_pool_count = total_types - default_locked_count
        
        st.info(f"💡 S16机制：{target_cost}费卡共 {total_types} 种")
        st.caption(f"- 基础卡 (默认在池): {base_pool_count} 种")
        st.caption(f"- 任务卡 (需解锁): {default_locked_count} 种")
        
        # 让用户输入：额外解锁了多少张任务卡？
        unlocked_task_cards = st.number_input(
            f"你解锁了其中几张**任务卡**？",
            min_value=0,                  # 最少解锁0张
            max_value=default_locked_count, # 最多把任务卡全解了
            value=0,                      # 默认还是0 (只玩基础卡)
            step=1,
            help="只计算那些需要做任务才能拿到的卡。解锁越少，卡池越干净！"
        )
        
        # [核心修正逻辑]
        # 实际在卡池里的总数 = 基础卡 + 你解锁的任务卡
        active_pool_count = base_pool_count + unlocked_task_cards
        
        # 传给后台的 locked_types = 总数 - 实际在池数
        # (或者直接理解为：没解锁的任务卡数量)
        locked_types = default_locked_count - unlocked_task_cards
        
        st.write(f"📊 当前卡池有效种类: **{active_pool_count}** / {total_types}")
    # ----------------------------

    st.markdown("---")
    st.header("🧮 场外干扰")
    
    max_single_card = current_season_data["POOL_SIZES"][target_cost]
    st.caption(f"单卡卡池上限: {max_single_card} 张")
    
    target_taken = st.number_input(f"外面有几张我要的卡？", min_value=0, value=0)
    
    # 智能估算干扰项上限
    effective_pool_count = total_types - locked_types
    max_other_cards_pool = (effective_pool_count - 1) * max_single_card
    
    other_taken = st.number_input(
        f"外面拿了多少张**其他同费**卡？", 
        min_value=0, 
        value=10, 
        step=5,
        help=f"卡池里现在实际上有 {effective_pool_count} 种卡。如果不算你的卡，其他同费卡总数上限约为 {max_other_cards_pool}。"
    )

    num_trials = st.selectbox("模拟次数", [500, 1000, 2000], index=1)

# 主运行逻辑
if st.button("🚀 开始量化回测", type="primary", use_container_width=True):
    
    df = run_simulation(
        current_season_data, level, target_cost, gold, 
        target_copies, target_taken, other_taken, num_trials,
        locked_types_count=locked_types
    )
    
    # 错误处理
    if isinstance(df, str):
        error_map = {
            "ERROR_ALL_LOCKED": "所有该费用的卡都被锁住了，卡池是空的！",
            "ERROR_TARGET_LIMIT": "卡池里这张卡已经被拿光了！",
            "ERROR_POOL_LIMIT": "同费卡池已被抽干，请检查场外数据。",
            "ERROR_LEVEL": "该等级无法D到此费用的卡。"
        }
        st.error(f"❌ {error_map.get(df, '未知错误')}")
        
    elif not df.empty:
        success_rate = df["success"].mean()
        avg_cost = df[df["success"]]["cost"].mean() if success_rate > 0 else 0
        
        # 结果展示
        st.subheader("📊 模拟报告")
        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("🎯 成功概率", f"{success_rate*100:.1f}%")
        kpi2.metric("💰 预期花费", f"{avg_cost:.0f} 金币")
        
        # 真实概率计算 (展示给用户看)
        rates = current_season_data["DROP_RATES"][level]
        base_rate = rates[target_cost]
        
        # 现在的分母
        current_pool_size = (max_single_card * (total_types - locked_types)) - target_taken - other_taken
        # 现在的分子
        current_target_left = max_single_card - target_taken
        
        real_prob = 0
        if current_pool_size > 0:
            real_prob = base_rate * (current_target_left / current_pool_size)
            
        kpi3.metric("🎲 真实出卡率/格", f"{real_prob*100:.2f}%", help=f"基础概率 {base_rate} x 卡池占比修正")

        # 图表
        if success_rate > 0:
            fig, ax = plt.subplots(figsize=(10, 3))
            ax.hist(df[df["success"]]["cost"], bins=20, color='#6c5ce7', alpha=0.8)
            ax.set_title("资金消耗分布")
            ax.set_xlabel("花费金币")
            ax.axvline(gold, color='red', linestyle='--')
            st.pyplot(fig)

        # --- AI 分析接入 ---
        st.subheader("💡 决策建议")
        current_level_probs = SEASON_CONFIG[selected_season_name]["DROP_RATES"][level]
        total_types_count = SEASON_CONFIG[selected_season_name]["DISTINCT_CHAMPS"][target_cost]
        prompt = f"""
        你是一个精通云顶之弈S16概率学的职业教练。请分析我的D牌决策。
        
        【当前局势】
        - 赛季：{selected_season_name}
        - 现状：{level}级，存款{gold}，搜{target_cost}费卡(缺{target_copies}张)。
        
        【关键机制：卡池锁定】
        - S16特殊规则：{target_cost}费卡总共有 {total_types_count} 种，但我有 {locked_types} 种【未解锁】。
        - **重要推论**：这意味着商店刷新时，这 {locked_types} 种卡**绝对不会出现**。
        - **结论**：卡池分母被大幅压缩了！这比正常情况下更容易搜到我要的卡（即“控卡池”战术）。请务必将此优势考虑在内。
        
        【量化回测数据】
        - 模拟成功率：{success_rate*100:.1f}% (指在花光钱之前搜到的概率)
        - 真实单格概率：{real_prob*100:.2f}% (基础D牌概率: {current_level_probs[target_cost]}) 
        - 预期花费：{avg_cost:.0f} 金币
        
        请结合我的“锁卡”优势和量化数据，简短毒舌地评价我的处境（是天胡开局还是依然很难搜？），并直接给出操作建议（梭哈/慢D/存钱拉人口）。
        """
        
        if api_key:
            try:
                client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                
                with st.chat_message("assistant", avatar="🧠"):
                    # 动态调整状态栏标题
                    status_label = "DeepSeek-R1 正在深度思考..." if "reasoner" in selected_model else "DeepSeek-V3 正在生成..."
                    
                    # 2. 创建状态容器
                    status_container = st.status(status_label, expanded=True)
                    with status_container:
                        reasoning_placeholder = st.empty()
                        # 如果是 V3 模型，提示一下用户没有思考过程
                        if "chat" in selected_model:
                            st.caption("⚡ V3 模型追求速度，不展示思维链")
                        else:
                            st.caption("🤔 正在进行思维链推导...")
                    
                    answer_placeholder = st.empty()
                    
                    # 3. 发起请求 (使用 selected_model)
                    stream = client.chat.completions.create(
                        model=selected_model,  # <--- 这里使用了侧边栏选中的变量
                        messages=[
                            {"role": "system", "content": "你是一个精通概率和云顶S16机制的职业教练。"},
                            {"role": "user", "content": prompt}
                        ],
                        stream=True
                    )
                    
                    # 4. 处理流式数据
                    reasoning_content = ""
                    final_content = ""
                    
                    for chunk in stream:
                        if chunk.choices:
                            delta = chunk.choices[0].delta
                            
                            # A. 尝试获取思考过程 (只有 R1 会进入这里)
                            r_content = getattr(delta, 'reasoning_content', None)
                            if r_content:
                                reasoning_content += r_content
                                reasoning_placeholder.markdown(f"_{reasoning_content}_")
                            
                            # B. 获取正式回答 (R1 和 V3 都有)
                            content = delta.content
                            if content:
                                final_content += content
                                answer_placeholder.markdown(final_content)
                    
                    # 5. 完成
                    status_container.update(label="分析完毕", state="complete", expanded=False)
        
            except Exception as e:
                st.error(f"AI 连接失败: {e}")
        else:
             st.info(f"**分析结论：** 当前成功率为 {success_rate*100:.1f}%。{'建议冲刺！' if success_rate > 0.6 else '风险极高，建议观望。'}")











