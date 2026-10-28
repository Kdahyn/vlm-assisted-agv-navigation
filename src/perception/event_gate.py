"""연속 검출·미검출 횟수로 감지 신호의 활성 상태를 관리한다."""
class Gate:
    def __init__(self, hits=3, misses=3):
        if hits < 1 or misses < 1:
            raise ValueError("hits/misses must be >= 1")
        self.required_hits, self.required_misses = hits, misses
        self.hits = self.misses = 0
        self.active = False

    def update(self, present: bool) -> bool:
        """현재 감지 여부와 연속 횟수를 반영한 신호를 반환한다."""
        if present:
            self.hits += 1
            self.misses = 0
            self.active = self.active or self.hits >= self.required_hits
        else:
            self.hits = 0
            self.misses += 1
            if self.misses >= self.required_misses:
                self.active = False
        return self.active and present

    def reset(self):
        self.hits = self.misses = 0
        self.active = False


if __name__ == "__main__":
    gate = Gate()
    assert [gate.update(x) for x in [True, True, True]] == [False, False, True]
    assert gate.update(False) is False
    assert gate.update(False) is False
    assert gate.update(False) is False
    print("Gate debounce demo: OK")
