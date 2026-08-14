"""
因子开发基础模块

提供因子开发的基类和常用工具函数
"""

import numpy as np
import pandas as pd
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import warnings

warnings.filterwarnings('ignore')


class FactorBase(ABC):
    """因子基类"""
    
    def __init__(self, name: str = None, **kwargs):
        """
        初始化因子
        
        Args:
            name: 因子名称，如果为 None 则使用类名
            **kwargs: 因子参数
        """
        self.name = name or self.__class__.__name__
        self.params = kwargs
        self.description = ""
    
    @abstractmethod
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        """
        计算因子值
        
        Args:
            data: 包含 OHLCV 等数据的 DataFrame
                必须包含的列：['open', 'high', 'low', 'close', 'volume']
                索引：MultiIndex [(datetime, instrument)]
        
        Returns:
            因子值 Series，索引为 (datetime, instrument)
        """
        pass
    
    def __call__(self, data: pd.DataFrame) -> pd.Series:
        """调用方法，计算因子"""
        return self.calculate(data)
    
    def get_info(self) -> Dict[str, Any]:
        """获取因子信息"""
        return {
            'name': self.name,
            'description': self.description,
            'params': self.params,
            'class': self.__class__.__name__
        }


# ============================================
# 常用因子实现
# ============================================

class PriceReturnFactor(FactorBase):
    """
    收益率因子
    
    计算不同周期的价格收益率
    """
    
    def __init__(self, window: int = 5, name: str = None):
        """
        Args:
            window: 收益率计算周期
        """
        super().__init__(name=name or f"PR_{window}")
        self.window = window
        self.description = f"{window}日价格收益率"
    
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data['close']
        pr = close.pct_change(periods=self.window)
        return pr


class MomentumFactor(FactorBase):
    """
    动量因子
    
    计算过去 N 日的累积收益率
    """
    
    def __init__(self, window: int = 20, name: str = None):
        """
        Args:
            window: 动量计算周期
        """
        super().__init__(name=name or f"MOM_{window}")
        self.window = window
        self.description = f"{window}日动量因子"
    
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        close = data['close']
        mom = close / close.shift(self.window) - 1
        return mom


class VolatilityFactor(FactorBase):
    """
    波动率因子
    
    计算收益率的波动率
    """
    
    def __init__(self, window: int = 20, name: str = None):
        """
        Args:
            window: 波动率计算周期
        """
        super().__init__(name=name or f"VOL_{window}")
        self.window = window
        self.description = f"{window}日波动率"
    
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        returns = data['close'].pct_change()
        vol = returns.rolling(window=self.window).std()
        return vol


class VolumeFactor(FactorBase):
    """
    成交量因子
    
    计算成交量的移动平均
    """
    
    def __init__(self, window: int = 20, name: str = None):
        """
        Args:
            window: 成交量均线周期
        """
        super().__init__(name=name or f"VMA_{window}")
        self.window = window
        self.description = f"{window}日成交量均线"
    
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        volume = data['volume']
        vma = volume.rolling(window=self.window).mean()
        return volume / vma - 1  # 成交量相对均线的偏离


class HighLowFactor(FactorBase):
    """
    高低区间因子
    
    计算当前价格在近期高低点之间的位置
    """
    
    def __init__(self, window: int = 20, name: str = None):
        """
        Args:
            window: 高低点计算周期
        """
        super().__init__(name=name or f"HL_{window}")
        self.window = window
        self.description = f"{window}日高低区间位置"
    
    def calculate(self, data: pd.DataFrame) -> pd.Series:
        high = data['high']
        low = data['low']
        close = data['close']
        
        hh = high.rolling(window=self.window).max()
        ll = low.rolling(window=self.window).min()
        
        hl_ratio = (close - ll) / (hh - ll + 1e-8)
        return hl_ratio


# ============================================
# 因子组合工具
# ============================================

class FactorManager:
    """因子管理器"""
    
    def __init__(self):
        self.factors: Dict[str, FactorBase] = {}
    
    def add_factor(self, factor: FactorBase):
        """添加因子"""
        self.factors[factor.name] = factor
    
    def calculate_all(self, data: pd.DataFrame) -> pd.DataFrame:
        """计算所有因子"""
        results = {}
        for name, factor in self.factors.items():
            try:
                results[name] = factor.calculate(data)
            except Exception as e:
                print(f"计算因子 {name} 时出错：{e}")
        
        return pd.DataFrame(results)
    
    def get_factor_names(self) -> List[str]:
        """获取所有因子名称"""
        return list(self.factors.keys())


# ============================================
# 示例用法
# ============================================

if __name__ == "__main__":
    # 创建测试数据
    dates = pd.date_range('2023-01-01', '2023-12-31', freq='B')
    instruments = ['SHSE.600000', 'SHSE.600001', 'SHSE.600002']
    
    index = pd.MultiIndex.from_product([dates, instruments], names=['datetime', 'instrument'])
    
    np.random.seed(42)
    data = pd.DataFrame({
        'open': np.random.randn(len(index)).cumsum() + 10,
        'high': np.random.randn(len(index)).cumsum() + 11,
        'low': np.random.randn(len(index)).cumsum() + 9,
        'close': np.random.randn(len(index)).cumsum() + 10,
        'volume': np.random.randn(len(index)).cumsum() + 1000
    }, index=index)
    
    # 创建因子管理器
    manager = FactorManager()
    
    # 添加因子
    manager.add_factor(PriceReturnFactor(window=5))
    manager.add_factor(MomentumFactor(window=20))
    manager.add_factor(VolatilityFactor(window=20))
    manager.add_factor(VolumeFactor(window=20))
    manager.add_factor(HighLowFactor(window=20))
    
    # 计算所有因子
    factor_data = manager.calculate_all(data)
    
    print("因子名称:", manager.get_factor_names())
    print("\n因子数据:")
    print(factor_data.head(10))
    print("\n因子统计:")
    print(factor_data.describe())
