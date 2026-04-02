from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from ..core.graph_model import DirectedGraph


@dataclass(frozen=True)
class ForumPost:
    post_id: str
    step: int
    author_id: str
    board: str
    tone: float
    target_id: str
    content: str


class ForumState:
    """
    Tieba-like simplified forum:
    - multiple boards
    - rolling posts
    - viewer-specific feed from graph neighbors + global hot posts
    """

    def __init__(self, max_posts: int = 1200) -> None:
        self.max_posts = max_posts
        self.posts: List[ForumPost] = []
        self.board_heat: Dict[str, float] = {}
        self.reputation: Dict[str, float] = {}
        self.target_mentions: Dict[str, int] = {}

    def publish(
        self,
        step: int,
        author_id: str,
        board: str,
        tone: float,
        target_id: str,
        content: str,
    ) -> ForumPost:
        tone = max(-1.0, min(1.0, tone))
        post = ForumPost(
            post_id=f"P{len(self.posts)}",
            step=step,
            author_id=author_id,
            board=board,
            tone=tone,
            target_id=target_id,
            content=content.strip(),
        )
        self.posts.append(post)
        if len(self.posts) > self.max_posts:
            self.posts = self.posts[-self.max_posts :]

        self.board_heat[board] = self.board_heat.get(board, 0.0) + abs(tone)
        if target_id:
            self.target_mentions[target_id] = self.target_mentions.get(target_id, 0) + 1
            # negative tone hurts target reputation; positive helps
            self.reputation[target_id] = self.reputation.get(target_id, 0.0) + tone
        self.reputation.setdefault(author_id, 0.0)
        return post

    def view_feed(
        self,
        viewer_id: str,
        graph: DirectedGraph,
        lookback_posts: int = 80,
        max_items: int = 8,
    ) -> List[ForumPost]:
        recent = self.posts[-lookback_posts:]
        if not recent:
            return []

        neighbors = {e.dst for e in graph.neighbors(viewer_id)}
        scored: List[tuple[float, ForumPost]] = []
        for post in recent:
            score = 0.1
            if post.author_id in neighbors:
                score += 1.2
            if post.target_id == viewer_id:
                score += 0.8
            score += 0.03 * self.board_heat.get(post.board, 0.0)
            score += 0.01 * (post.step - recent[0].step)
            scored.append((score, post))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in scored[:max_items]]

    def personal_sentiment(self, viewer_id: str, graph: DirectedGraph) -> float:
        feed = self.view_feed(viewer_id, graph)
        if not feed:
            return 0.0
        total = 0.0
        weight_sum = 0.0
        for p in feed:
            w = 1.0
            if p.target_id == viewer_id:
                w = 1.5
            total += p.tone * w
            weight_sum += w
        return total / weight_sum if weight_sum else 0.0

    def global_sentiment(self, lookback_posts: int = 100) -> float:
        recent = self.posts[-lookback_posts:]
        if not recent:
            return 0.0
        return sum(p.tone for p in recent) / len(recent)

    def hottest_board(self) -> str:
        if not self.board_heat:
            return "mining"
        return max(self.board_heat.items(), key=lambda kv: kv[1])[0]

    def most_criticized_target(self) -> str:
        if not self.target_mentions:
            return ""
        return max(self.target_mentions.items(), key=lambda kv: kv[1])[0]

    def brief_feed_text(self, viewer_id: str, graph: DirectedGraph, max_items: int = 5) -> str:
        feed = self.view_feed(viewer_id, graph, max_items=max_items)
        if not feed:
            return "no recent posts"
        lines: List[str] = []
        for p in feed:
            short_content = p.content[:48]
            lines.append(
                f"{p.post_id}|{p.board}|author={p.author_id}|target={p.target_id or 'none'}|"
                f"tone={p.tone:+.2f}|{short_content}"
            )
        return " || ".join(lines)

    def reputation_of(self, miner_id: str) -> float:
        return self.reputation.get(miner_id, 0.0)

    def board_heat_of(self, board: str) -> float:
        return self.board_heat.get(board, 0.0)

