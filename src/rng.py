"""确定性随机数发生器。

为什么不用标准库的 ``random``？
因为本仓库的实验结果需要**完全可复现**——同一个随机种子必须得到逐位相同的
车辆序列与指标数值，否则队友之间、以及赛前预研与赛时环境之间无法对齐结论。
这里用一个显式的线性同余发生器（LCG）加 Box-Muller 正态变换，
不依赖任何实现细节，在任何 Python 版本上结果都一致。
"""

import math

_MODULUS = 2147483648      # 2 ** 31
_MULTIPLIER = 1103515245
_INCREMENT = 12345


class SimpleRandom:
    """线性同余伪随机数发生器，附带标准正态采样。"""

    def __init__(self, seed):
        self.state = int(seed) % _MODULUS

    def random(self):
        """返回 [0, 1) 区间内的均匀随机数。"""
        self.state = (self.state * _MULTIPLIER + _INCREMENT) % _MODULUS
        return self.state / float(_MODULUS)

    def gauss(self, mu=0.0, sigma=1.0):
        """Box-Muller 变换采样标准正态分布。"""
        u = 0.0
        while u == 0.0:
            u = self.random()
        v = 0.0
        while v == 0.0:
            v = self.random()
        z = math.sqrt(-2.0 * math.log(u)) * math.cos(2.0 * math.pi * v)
        return mu + sigma * z

    def uniform(self, low, high):
        return low + (high - low) * self.random()
