#****************************************************************************
#* expr_parser.py
#*
#* Copyright 2023-2025 Matthew Ballance and Contributors
#*
#* Licensed under the Apache License, Version 2.0 (the "License"); you may 
#* not use this file except in compliance with the License.  
#* You may obtain a copy of the License at:
#*  
#*   http://www.apache.org/licenses/LICENSE-2.0
#*  
#* Unless required by applicable law or agreed to in writing, software 
#* distributed under the License is distributed on an "AS IS" BASIS, 
#* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  
#* See the License for the specific language governing permissions and 
#* limitations under the License.
#*
#* Created on:
#*     Author: 
#*
#****************************************************************************
import dataclasses as dc
import enum
import ply.lex as lex
import ply.yacc as yacc
from typing import ClassVar, List

@dc.dataclass
class Expr(object):
    def accept(self, v):
        raise NotImplementedError("Expr.accept for %s" % str(type(sepf)))

@dc.dataclass
class ExprId(Expr):
    id : str

    def accept(self, v):
        v.visitExprId(self)

@dc.dataclass
class ExprHId(Expr):
    id : List[str] = dc.field(default_factory=list)

    def accept(self, v):
        v.visitExprHId(self)

class ExprBinOp(enum.Enum):
    Pipe = enum.auto()
    Plus = enum.auto()
    Minus = enum.auto()
    Times = enum.auto()
    Divide = enum.auto()
    # Comparison operators
    Eq = enum.auto()       # ==
    Ne = enum.auto()       # !=
    Lt = enum.auto()       # <
    Le = enum.auto()       # <=
    Gt = enum.auto()       # >
    Ge = enum.auto()       # >=
    # Logical operators
    And = enum.auto()      # &&
    Or = enum.auto()       # ||

class ExprUnaryOp(enum.Enum):
    Not = enum.auto()      # !

@dc.dataclass
class ExprUnary(Expr):
    op : ExprUnaryOp
    expr : Expr

    def accept(self, v):
        v.visitExprUnary(self)

@dc.dataclass
class ExprBin(Expr):
    op : ExprBinOp
    lhs : Expr
    rhs : Expr

    def accept(self, v):
        v.visitExprBin(self)

@dc.dataclass
class ExprCall(Expr):
    id : str
    args : List[Expr]

    def accept(self, v):
        v.visitExprCall(self)

@dc.dataclass
class ExprString(Expr):
    value : str

    def accept(self, v):
        v.visitExprString(self)

@dc.dataclass
class ExprInt(Expr):
    value : int

    def accept(self, v):
        v.visitExprInt(self)

@dc.dataclass
class ExprBool(Expr):
    value : bool

    def accept(self, v):
        v.visitExprBool(self)

class ExprVisitor(object):
    def visitExprHId(self, e : ExprId):
        pass

    def visitExprId(self, e : ExprId):
        pass

    def visitExprBin(self, e : ExprBin):
        e.lhs.accept(self)
        e.rhs.accept(self)

    def visitExprUnary(self, e):
        e.expr.accept(self)

    def visitExprCall(self, e : ExprCall):
        for arg in e.args:
            arg.accept(self)

    def visitExprString(self, e : ExprString):
        pass

    def visitExprInt(self, e : ExprInt):
        pass

    def visitExprBool(self, e):
        pass

@dc.dataclass
class ExprVisitor2String(ExprVisitor):
    _ret : str = ""
    _idx : int = 0

    @staticmethod
    def toString(e : Expr):
        v = ExprVisitor2String()
        e.accept(v)
        return v._ret

    def visitExprId(self, e : ExprId):
        self._ret += e.id
    
    def visitExprBin(self, e):
        e.lhs.accept(self)
        self._ret += " "
        self._ret += "op%d" % self._idx
        self._idx += 1
        self._ret += " "
        e.rhs.accept(self)

    def visitExprCall(self, e):
        self._ret += e.id
        self._ret += "("
        for i, arg in enumerate(e.args):
            if i > 0:
                self._ret += ", "
            arg.accept(self)
        self._ret += ")"
    
    def visitExprString(self, e):
        self._ret += e.value

    def visitExprInt(self, e):
        self._ret += str(e.value)


class ExprParser(object):

    _inst : ClassVar['ExprParser'] = None

    def __init__(self):

        # Build the lexer
        self.lexer = lex.lex(module=self)
        self.parser = yacc.yacc(module=self)

    @classmethod
    def inst(cls):
        if cls._inst is None:
            cls._inst = ExprParser()
        return cls._inst

    tokens = (
        'ID', 'DOT', 'NUMBER','COMMA',
        'PLUS','MINUS','TIMES','DIVIDE',
        'LPAREN','RPAREN','PIPE','STRING1','STRING2',
        'EQ','NE','LT','LE','GT','GE',  # Comparison operators
        'AND','OR','NOT'  # Logical operators
        )
    
    # Tokens - Define multi-character operators FIRST as functions with regex in docstring
    
    def t_AND(self, t):
        r'&&'
        return t
    
    def t_OR(self, t):
        r'\|\|'
        return t
    
    def t_EQ(self, t):
        r'=='
        return t
    
    def t_NE(self, t):
        r'!='
        return t
    
    def t_LE(self, t):
        r'<='
        return t
    
    def t_GE(self, t):
        r'>='
        return t
    
    def t_NUMBER(self, t):
        r'\d+'
        try:
            t.value = ExprInt(int(t.value)) 
        except ValueError:
            print("Integer value too large %d", t.value)
            t.value = ExprInt(0)
        return t
    
    def t_STRING1(self, t):
        r'"([^"\\]*(\\.[^"\\]*)*)"'
        t.value = t.value[1:-1].replace(r'\"', '"').replace(r'\\', '\\')
        return t

    def t_STRING2(self, t):
        r'\'([^\'\\]*(\\.[^\'\\]*)*)\''
        t.value = t.value[1:-1].replace(r'\'', '"').replace(r'\\', '\\')
        return t
    
    # Single character tokens
    t_COMMA   = r',' 
    t_PLUS    = r'\+'
    t_MINUS   = r'-'
    t_TIMES   = r'\*'
    t_DIVIDE  = r'/'
    t_LPAREN  = r'\('
    t_RPAREN  = r'\)'
    t_ID      = r'[a-zA-Z_][a-zA-Z0-9_]*(:-.+)?'
    t_DOT     = r'\.'
    t_LT      = r'<'
    t_GT      = r'>'
    t_NOT     = r'!'
    t_PIPE    = r'\|'
    
    # Ignored characters
    t_ignore = " \t"
    
    def t_newline(self, t):
        r'\n+'
        t.lexer.lineno += t.value.count("\n")
        
    def t_error(self, t):
        print("Illegal character '%s'" % t.value[0])
        t.lexer.skip(1)
        
    precedence = (
        ('left', 'OR'),
        ('left', 'AND'),
        ('right', 'NOT'),
        ('left', 'EQ', 'NE'),
        ('left', 'LT', 'LE', 'GT', 'GE'),
        ('left', 'PLUS', 'MINUS', 'PIPE'),
        ('left', 'TIMES', 'DIVIDE'),
        )
    
    def p_call(self, t):
        """expression : ID LPAREN RPAREN 
                      | ID LPAREN args RPAREN"""
        t[0] = ExprCall(t[1], t[3] if len(t) == 5 else [])

    def p_args(self, t):
        """args : expression 
                | args COMMA expression"""
        if len(t) == 2:
            t[0] = [t[1]]
        else:
            t[0] = t[1]
            t[0].append(t[3])
    
    def p_expression_binop(self, t):
        '''expression : expression PLUS expression
                      | expression MINUS expression
                      | expression TIMES expression
                      | expression PIPE expression
                      | expression DIVIDE expression
                      | expression EQ expression
                      | expression NE expression
                      | expression LT expression
                      | expression LE expression
                      | expression GT expression
                      | expression GE expression
                      | expression AND expression
                      | expression OR expression'''
        op_m = {
            '+' : ExprBinOp.Plus,
            '-' : ExprBinOp.Minus,
            '*' : ExprBinOp.Times,
            '|' : ExprBinOp.Pipe,
            '/' : ExprBinOp.Divide,
            '==' : ExprBinOp.Eq,
            '!=' : ExprBinOp.Ne,
            '<' : ExprBinOp.Lt,
            '<=' : ExprBinOp.Le,
            '>' : ExprBinOp.Gt,
            '>=' : ExprBinOp.Ge,
            '&&' : ExprBinOp.And,
            '||' : ExprBinOp.Or,
        }
        t[0] = ExprBin(op_m[t[2]], t[1], t[3])
    
    def p_expression_unary(self, t):
        '''expression : NOT expression'''
        t[0] = ExprUnary(ExprUnaryOp.Not, t[2])
    
    def p_expression_group(self, t):
        'expression : LPAREN expression RPAREN'
        t[0] = t[2]
    
    def p_expression_number(self, t):
        'expression : NUMBER'
        t[0] = t[1]
    
    def p_expression_name(self, t):
        'expression : ID'
        # Handle boolean literals
        if t[1] == 'true':
            t[0] = ExprBool(True)
        elif t[1] == 'false':
            t[0] = ExprBool(False)
        else:
            t[0] = ExprId(t[1])

    def p_expression_hid(self, t):
        'expression : hier_id'
        t[0] = t[1]

    def p_hier_id(self, t):
        '''hier_id : ID DOT hier_id 
                   | ID'''
        if len(t) == 2:
            t[0] = ExprHId()
            t[0].id.append(t[1])
        else:
            t[3].id.insert(0, t[1])
            t[0] = t[3]

    def p_expression_string1(self, t):
        'expression : STRING1'
        t[0] = ExprString(t[1])

    def p_expression_string2(self, t):
        'expression : STRING2'
        t[0] = ExprString(t[1])
    
    def p_error(self, t):
        print("Syntax error at '%s'" % t.value)

    def parse(self, input):
        return self.parser.parse(input, lexer=self.lexer)
    
