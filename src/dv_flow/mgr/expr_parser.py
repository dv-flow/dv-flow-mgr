import dataclasses as dc
import enum

class TokenKind(enum.Enum):
    ID = enum.auto()

@dc.dataclass
class Expr(object):
    kind : TokenKind = TokenKind.ID

class ExprId(Expr):
    id : str

    def __post_init__(self):
        self.kind = TokenKind.ID

class ExprPipe(Expr):
    lhs : Expr
    rhs : Expr

    def __post_init__(self):
        self.kind = TokenKind.ID



class ExprParser(object):

    def __init__(self, input):
        self.input = input

    def __iter__(self):
        return self
    
    def __next__(self):

        self.expr = expr
        self.tokens = []
        self.pos = 0
