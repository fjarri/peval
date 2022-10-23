import sys
import ast
import typing

ConstsDictT = typing.Dict[str, typing.Any]
PassOutputT = typing.Tuple[ast.AST, ConstsDictT]

NodeTypeT = typing.Type[ast.AST]
NodeTypeIsInstanceCriteriaT = typing.Union[typing.Tuple[NodeTypeT], NodeTypeT]

NameNodeT = typing.Union[ast.arg, ast.Name]

if sys.version_info[:2] >= (3, 8):
    ConstantNodeT = ast.Constant
else:
    ConstantNodeT = typing.Union[ast.NameConstant, ast.Str, ast.Bytes, ast.Num]

ConstantOrNameNodeT = typing.Union[ConstantNodeT, ast.Name]

ConstantT = typing.Union[int, float, complex, str, bytes, bool]
ConsantOrASTNodeT = typing.Union[ConstantT, ast.AST]
