"""횡단 지속시간 D ~ Uniform(1, 7)초를 가정한 재탐색 임계시간 민감도 계산."""


def reroute_probability(threshold, low=1, high=7):
    if high <= low:
        raise ValueError('Expected high > low')
    return min(1.0, max(0.0, (high - threshold) / (high - low)))


if __name__ == '__main__':
    for t in range(11):
        print(f'T={t:2d}s  theoretical unnecessary reroute probability={100*reroute_probability(t):5.1f}%')
    assert round(reroute_probability(5) * 100, 1) == 33.3
