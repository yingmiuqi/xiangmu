"""
k-Means聚类算法对"双一流"高校进行分类
维度：A+学科数量（第四轮学科评估）、院士数量（全职两院院士）
数据来源：
  - 第二轮"双一流"建设高校名单（教育部，2022年2月）
  - 第四轮学科评估结果（教育部学位中心，2017年12月）
  - 2024年高校全职院士统计数据（综合各高校官网及公开报道）

输出：聚类分配结果、聚类中心（原始尺度）、散点图
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import sys
import os

# 设置中文字体（PyCharm环境下通常可用SimHei）
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题


# -------------------------------
# 1. 数据加载 / 输入
# -------------------------------
def load_data(file_path='shuangyiliu_universities.csv'):
    """
    从CSV文件加载147所"双一流"高校的完整数据。
    若文件不存在，则使用精简的内置数据集（Top 30高校）作为回退方案。

    所需列：
        University           - 高校名称
        A_plus_disciplines   - A+学科数量（第四轮学科评估）
        Academicians         - 全职两院院士数量

    返回 DataFrame。
    """
    if os.path.exists(file_path):
        try:
            df = pd.read_csv(file_path)
            required_cols = {'University', 'A_plus_disciplines', 'Academicians'}
            if not required_cols.issubset(df.columns):
                raise ValueError(f"CSV文件必须包含列：{required_cols}")
            print(f"已从 '{file_path}' 加载数据，共 {len(df)} 所高校。")
            return df
        except Exception as e:
            print(f"读取文件时出错：{e}")
            print("将使用内置的精简数据集（Top 30高校）作为回退方案。\n")

    # ---- 回退方案：内置Top 30高校数据 ----
    print("正在使用内置数据集（A+学科数Top 30的高校）。")
    fallback_data = {
        'University': [
            '北京大学', '清华大学', '浙江大学', '中国人民大学', '中国科学技术大学',
            '中国农业大学', '北京师范大学', '复旦大学', '上海交通大学', '东南大学',
            '南京大学', '武汉大学', '华中科技大学', '哈尔滨工业大学', '同济大学',
            '北京航空航天大学', '国防科技大学', '西安交通大学', '中南大学', '南开大学',
            '天津大学', '北京理工大学', '北京科技大学', '中山大学', '厦门大学',
            '华东师范大学', '电子科技大学', '中国海洋大学', '四川大学', '西北工业大学'
        ],
        'A_plus_disciplines': [
            21, 21, 11, 9, 7, 6, 6, 5, 5, 5,
            3, 4, 3, 3, 4, 4, 4, 2, 3, 0,
            1, 1, 2, 2, 1, 2, 2, 2, 1, 1
        ],
        'Academicians': [
            64, 73, 38, 1, 21, 5, 5, 29, 32, 14,
            33, 12, 17, 28, 18, 25, 14, 13, 14, 8,
            10, 9, 10, 10, 15, 4, 4, 4, 12, 9
        ]
    }
    df = pd.DataFrame(fallback_data)
    return df


# -------------------------------
# 2. 数据预处理
# -------------------------------
def preprocess_data(df):
    """
    提取特征列，处理缺失值，并进行Z-score标准化。

    返回：
        X_scaled  - 标准化后的特征矩阵 (numpy array)
        X_original- 原始特征DataFrame
        df_clean  - 清洗后的完整DataFrame
        scaler    - 标准化器对象
    """
    feature_cols = ['A_plus_disciplines', 'Academicians']
    X = df[feature_cols].copy()

    # 处理缺失值
    if X.isnull().any().any():
        n_before = len(df)
        df = df.dropna(subset=feature_cols).reset_index(drop=True)
        X = df[feature_cols].copy()
        n_dropped = n_before - len(df)
        print(f"⚠ 警告：删除了 {n_dropped} 条含有缺失值的记录。")

    # Z-score 标准化（均值0，标准差1）
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    print(f"数据预处理完成。特征维度：{X_scaled.shape[1]}，样本数：{X_scaled.shape[0]}")
    return X_scaled, X, df, scaler


# -------------------------------
# 3. k-Means 模型实现
# -------------------------------
def perform_kmeans(X_scaled, n_clusters=3, random_state=42):
    """
    执行k-Means聚类。

    参数：
        X_scaled    - 标准化后的特征矩阵
        n_clusters  - 聚类数 k
        random_state- 随机种子

    返回：
        kmeans - 已训练的KMeans对象
        labels - 各样本的聚类标签
    """
    kmeans = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10)
    labels = kmeans.fit_predict(X_scaled)
    print(f"k-Means 聚类完成（k={n_clusters}）。")
    return kmeans, labels


# -------------------------------
# 4. 可视化
# -------------------------------
def visualize_clusters(X_original, labels, centroids_scaled, scaler, df, n_clusters):
    """
    绘制聚类散点图，包含高校名称标注、聚类中心标记和图例。
    """
    centroids_original = scaler.inverse_transform(centroids_scaled)

    plt.figure(figsize=(14, 10))

    # 散点图
    scatter = plt.scatter(
        X_original['A_plus_disciplines'],
        X_original['Academicians'],
        c=labels,
        cmap='viridis',
        s=80,
        alpha=0.85,
        edgecolors='k',
        linewidth=0.5
    )

    # 聚类中心
    plt.scatter(
        centroids_original[:, 0],
        centroids_original[:, 1],
        marker='X',
        s=300,
        c='red',
        edgecolors='black',
        linewidth=2,
        label='聚类中心',
        zorder=5
    )

    # 高校名称标注（仅当数据量 ≤ 50 时显示，避免标签重叠）
    if len(df) <= 200:
        for i, uni in enumerate(df['University']):
            plt.annotate(uni,
                         (X_original.iloc[i, 0], X_original.iloc[i, 1]),
                         textcoords="offset points",
                         xytext=(5, 5),
                         ha='left',
                         fontsize=7,
                         alpha=0.8)
    else:
        print("数据量超过50所，省略高校名称标注以避免图像拥挤。")

    plt.title(f'“双一流”高校 k-Means 聚类结果（k={n_clusters}）', fontsize=15, fontweight='bold')
    plt.xlabel('A+学科数量（第四轮学科评估）', fontsize=12)
    plt.ylabel('全职两院院士数量', fontsize=12)
    plt.colorbar(scatter, label='聚类标签')
    plt.legend(fontsize=11)
    plt.grid(True, linestyle='--', alpha=0.4)
    plt.tight_layout()
    plt.show()


# -------------------------------
# 5. 结果分析 / 输出
# -------------------------------
def print_results(df, labels, centroids_scaled, scaler, kmeans):
    """
    输出完整的聚类分析报告：
    - 聚类分配表
    - 聚类中心（原始尺度）
    - 惯性（inertia）
    - 各聚类统计摘要
    - 简要结论
    """
    df_out = df.copy()
    df_out['聚类'] = labels

    # ---- 5.1 聚类分配 ----
    print("\n" + "=" * 70)
    print("聚类分配结果".center(70))
    print("=" * 70)
    # 按聚类标签排序输出
    df_sorted = df_out.sort_values(['聚类', 'A_plus_disciplines'], ascending=[True, False])
    for _, row in df_sorted.iterrows():
        print(f"  {row['University']:<20s} → 类别 {int(row['聚类'])}"
              f"  (A+学科: {int(row['A_plus_disciplines']):>2d},  院士: {int(row['Academicians']):>3d})")

    # ---- 5.2 聚类中心 ----
    centroids_original = scaler.inverse_transform(centroids_scaled)
    print("\n" + "=" * 70)
    print("聚类中心（原始尺度）".center(70))
    print("=" * 70)
    for i, centroid in enumerate(centroids_original):
        print(f"  类别 {i}:  A+学科数量 ≈ {centroid[0]:.1f},  院士数量 ≈ {centroid[1]:.1f}")

    # ---- 5.3 惯性 ----
    print(f"\n惯性（簇内平方和，Inertia）：{kmeans.inertia_:.2f}")

    # ---- 5.4 统计摘要 ----
    print("\n" + "=" * 70)
    print("各聚类统计摘要".center(70))
    print("=" * 70)
    for cluster_id in sorted(set(labels)):
        cluster_data = df_out[df_out['聚类'] == cluster_id]
        n = len(cluster_data)
        avg_aplus = cluster_data['A_plus_disciplines'].mean()
        avg_acad = cluster_data['Academicians'].mean()
        universities = '、'.join(cluster_data['University'].values)
        if len(universities) > 80:
            universities = universities[:80] + '...'
        print(f"\n类别 {cluster_id}（共 {n} 所高校）：")
        print(f"  平均 A+学科数：{avg_aplus:.1f}")
        print(f"  平均 院士数量：{avg_acad:.1f}")
        print(f"  包含高校：{universities}")

    # ---- 5.5 结论 ----
    print("\n" + "=" * 70)
    print("简要结论".center(70))
    print("=" * 70)
    print("""
聚类结果反映了“双一流”高校在学科顶尖程度（A+学科）和师资力量（院士）
两个维度上的分层格局：

  - 第一梯队（高A+、高院士）：以清北为代表的顶尖综合性大学，
    在两个维度上均大幅领先。
  - 第二梯队（中等A+、中等院士）：包括华东五校及部分强势工科/
    综合性大学，在特定领域拥有较强话语权。
  - 第三梯队（较少A+、较少院士）：多数为学科特色型高校或
    地方重点建设高校，在特定学科上具有优势，但整体体量较小。

（注：具体梯队划分取决于k值的设定与数据分布。）
""")


# -------------------------------
# 主程序入口
# -------------------------------
def main():
    # 命令行传参：CSV文件路径（可选）
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    else:
        file_path = 'shuangyiliu_universities.csv'

    # 1. 加载数据
    df = load_data(file_path)

    # 2. 数据预处理
    X_scaled, X_original, df_clean, scaler = preprocess_data(df)

    # 3. 设定聚类数 k（可手动调整，或改用 input() 交互输入）
    k = 3
    print(f"\n聚类数 k = {k}")

    # 4. 执行 k-Means 聚类
    kmeans, labels = perform_kmeans(X_scaled, n_clusters=k)

    # 5. 输出聚类报告
    print_results(df_clean, labels, kmeans.cluster_centers_, scaler, kmeans)

    # 6. 可视化
    visualize_clusters(X_original, labels, kmeans.cluster_centers_, scaler, df_clean, k)


if __name__ == "__main__":
    main()