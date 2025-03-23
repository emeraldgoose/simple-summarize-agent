import re

from langchain_core.exceptions import OutputParserException
from langchain_core.output_parsers import BaseOutputParser

class MarkdownOutputParser(BaseOutputParser):
    def parse(self, output: str) -> str:
        cleaned_text = output.strip()
        if len(cleaned_text) > 0:
            pattern = r"^\s*```(?:\w+)?\n([\s\S]*?)\n```\s*$"
            match = re.match(pattern, cleaned_text)
            if match:
                return match.group(1)
        else:
            raise OutputParserException("Output is empty")
    
    @property
    def _type(self) -> str:
        return "markdown_output_parser"
