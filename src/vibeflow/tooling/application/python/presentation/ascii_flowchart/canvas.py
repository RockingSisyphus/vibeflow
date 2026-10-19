from __future__ import annotations


class Canvas:
    def __init__(self, width: int, height: int) -> None:
        self.width = max(width, 1)
        self.height = max(height, 1)
        self.grid = [[" " for _ in range(self.width)] for _ in range(self.height)]
        self.occupied = [[False for _ in range(self.width)] for _ in range(self.height)]

    def set(self, x: int, y: int, char: str) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height) or self.occupied[y][x]:
            return
        existing = self.grid[y][x]
        self.grid[y][x] = _merge_line(existing, char)

    def force_set(self, x: int, y: int, char: str) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.grid[y][x] = char

    def get(self, x: int, y: int) -> str:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[y][x]
        return " "

    def draw_text(self, x: int, y: int, text: str) -> None:
        for offset, char in enumerate(text):
            self.force_set(x + offset, y, char)

    def hline(self, x1: int, x2: int, y: int) -> None:
        self._line(x1, x2, y, fixed_axis="y", char="─")

    def vline(self, x: int, y1: int, y2: int) -> None:
        self._line(y1, y2, x, fixed_axis="x", char="│")

    def _line(self, start: int, end: int, fixed: int, *, fixed_axis: str, char: str) -> None:
        for value in range(min(start, end), max(start, end) + 1):
            x, y = (fixed, value) if fixed_axis == "x" else (value, fixed)
            self.set(x, y, char)

    def mark_occupied(self, x: int, y: int, width: int, height: int) -> None:
        for yy in range(y, y + height):
            for xx in range(x, x + width):
                if 0 <= xx < self.width and 0 <= yy < self.height:
                    self.occupied[yy][xx] = True

    def can_place_text(self, x: int, y: int, text: str) -> bool:
        if y < 0 or y >= self.height or x < 0 or x + len(text) >= self.width:
            return False
        return all(self.get(x + offset, y) == " " and not self.occupied[y][x + offset] for offset in range(len(text)))

    def to_string(self) -> str:
        return "\n".join("".join(row).rstrip() for row in self.grid).rstrip()


def _merge_line(existing: str, incoming: str) -> str:
    if existing == " ":
        return incoming
    if existing == incoming:
        return existing
    if {existing, incoming} == {"─", "│"}:
        return "┼"
    if existing in "┼├┤┬┴" or incoming in "┼├┤┬┴":
        return "┼"
    return incoming if existing in "─│" else existing
