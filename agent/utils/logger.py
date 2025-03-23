from typing import Optional
from rich.rule import Rule
from rich.console import Console, Group
from rich.syntax import Syntax

class Logger:
    def __init__(self):
        self.console = Console()
    
    def log(self, content: str, title: Optional[str] = None):
        content = Syntax(content, lexer="markdown", theme="github-dark", word_wrap=True)
        if title:
            content = Group(Rule(f"[bold]{title}", align="center"), content)
        self.console.print(content)