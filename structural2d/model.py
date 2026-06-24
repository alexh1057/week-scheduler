"""Data model for a 2D frame: nodes, members, supports, and loads.

Units are not enforced -- use a consistent set throughout (e.g. N, m, Pa).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

Direction = Literal["local", "global"]


@dataclass
class Node:
    id: str
    x: float
    y: float


@dataclass
class Support:
    node_id: str
    ux: bool = False
    uy: bool = False
    rz: bool = False

    @classmethod
    def fixed(cls, node_id: str) -> "Support":
        return cls(node_id, True, True, True)

    @classmethod
    def pinned(cls, node_id: str) -> "Support":
        return cls(node_id, True, True, False)

    @classmethod
    def roller(cls, node_id: str, direction: Literal["x", "y"] = "y") -> "Support":
        return cls(node_id, direction == "x", direction == "y", False)


@dataclass
class Member:
    id: str
    node_i: str
    node_j: str
    E: float
    A: float
    I: float
    hinge_i: bool = False
    hinge_j: bool = False


@dataclass
class NodalLoad:
    node_id: str
    fx: float = 0.0
    fy: float = 0.0
    m: float = 0.0


@dataclass
class MemberPointLoad:
    """A concentrated force/moment applied along a member.

    `position` is measured from node_i, in the same length units as
    the node coordinates. Fx/Fy are resolved in `frame` ("local": local
    member x/y axes, "global": global X/Y axes).
    """

    member_id: str
    position: float
    fx: float = 0.0
    fy: float = 0.0
    m: float = 0.0
    frame: Direction = "local"


@dataclass
class MemberUDL:
    """A uniformly distributed load over [start, end] of a member.

    wx/wy are force-per-length, resolved in `frame`. start/end default
    to the full member length when left as None.
    """

    member_id: str
    wx: float = 0.0
    wy: float = 0.0
    frame: Direction = "local"
    start: float | None = None
    end: float | None = None


@dataclass
class FrameModel:
    nodes: dict[str, Node] = field(default_factory=dict)
    members: dict[str, Member] = field(default_factory=dict)
    supports: dict[str, Support] = field(default_factory=dict)
    nodal_loads: list[NodalLoad] = field(default_factory=list)
    point_loads: list[MemberPointLoad] = field(default_factory=list)
    udls: list[MemberUDL] = field(default_factory=list)

    def add_node(self, id: str, x: float, y: float) -> Node:
        node = Node(id, x, y)
        self.nodes[id] = node
        return node

    def add_member(
        self,
        id: str,
        node_i: str,
        node_j: str,
        E: float,
        A: float,
        I: float,
        hinge_i: bool = False,
        hinge_j: bool = False,
    ) -> Member:
        member = Member(id, node_i, node_j, E, A, I, hinge_i, hinge_j)
        self.members[id] = member
        return member

    def add_support(self, support: Support) -> None:
        self.supports[support.node_id] = support

    def add_nodal_load(self, load: NodalLoad) -> None:
        self.nodal_loads.append(load)

    def add_point_load(self, load: MemberPointLoad) -> None:
        self.point_loads.append(load)

    def add_udl(self, load: MemberUDL) -> None:
        self.udls.append(load)

    def node_order(self) -> list[str]:
        return list(self.nodes.keys())

    def member_length(self, member_id: str) -> float:
        m = self.members[member_id]
        ni, nj = self.nodes[m.node_i], self.nodes[m.node_j]
        return math.hypot(nj.x - ni.x, nj.y - ni.y)

    def member_angle(self, member_id: str) -> float:
        m = self.members[member_id]
        ni, nj = self.nodes[m.node_i], self.nodes[m.node_j]
        return math.atan2(nj.y - ni.y, nj.x - ni.x)

    def member_point_loads(self, member_id: str) -> list[MemberPointLoad]:
        return [p for p in self.point_loads if p.member_id == member_id]

    def member_udls(self, member_id: str) -> list[MemberUDL]:
        return [u for u in self.udls if u.member_id == member_id]
