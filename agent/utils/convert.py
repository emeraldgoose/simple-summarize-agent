import re

NUMBERED_LIST_PATTERN = r'^( *)(\d+)\. '
UNORDERED_LIST_PATTERN = r'^( *)(\-|\*) '
HEADING_PATTERN = r'^(#+)'
QUOTE_PATTERN = r'> ([\s\S]+)'
HR_PATTERN = r'^---+$'
TABLE_PATTERN = r'(\|(.*)\|)'
IMAGE_PATTERN = r'!\[(.*?)\]\((.*?)\)'
CODE_BLOCK_PATTERN = re.compile(r'```(\w+)?\n([\s\S]*?)\n```',re.DOTALL)
LATEX_BLOCK_PATTERN = re.compile(r'\$\$(.*?)\$\$', re.DOTALL)
IMAGE_XML_BLOCK_PATTERN = image_xml_pattern = re.compile(r'<figure>\n([\s\S]*?)\n</figure>',re.DOTALL)
SUPPORTED_IMG_EXT = ('bmp', 'gif', 'heic', 'jpeg', 'png', 'svg', 'tif', 'tiff')

latex_blocks = {}
code_blocks = {}
image_xml_blocks = {}

def replace_code_blocks(match):
    index = len(code_blocks)
    language, content = match.group(1), match.group(2)
    code_blocks[index] = ((language or 'plain text').strip(), content.strip())
    return f'CODEBLOCK_{index}'

def replace_latex_blocks(match):
    index = len(latex_blocks)
    content = match.group(1)
    latex_blocks[index] = content.strip()
    return f'LATEXBLOCK_{index}'

def replace_image_xml_blocks(match):
    index = len(image_xml_blocks)
    content = match.group(1)
    src = re.findall(r'<img src="([\s\S]*?)">',content)[0]
    figcaption = re.findall(r'<figcaption>([\s\S]*?)</figcaption>',content)[0]
    src = "" if not src else src[0]
    figcaption = "" if not figcaption else figcaption[0]
    image_xml_blocks[index] = (src, figcaption)
    return f'IMAGEXMLBLOCK_{index}'

def text_with_style(text):
    STYLE_MAP = {
        "**": "bold",
        "__": "bold",
        "*": "italic",
        "_": "italic",
        "~~": "strikethrough",
        "`": "code",
    }

    tokens = re.split(r"(\*\*|__|\*|_|~~|`)", text)
    active_styles = set()
    spans = []

    for token in tokens:
        if not token:
            continue
        
        if token in STYLE_MAP:
            if token in active_styles:
                active_styles.remove(token)
            else:
                active_styles.add(token)
        else:
            spans.append({
                "text": {"content": token},
                "annotations": {STYLE_MAP[style]: True for style in active_styles}
            })
    
    return spans

def make_block(type, text):
    annotations = text_with_style(text)

    block = {
        "object": "block",
        "type": type,
        type: {
            "rich_text": annotations
        }
    }
    return block

def make_image_block(url):
    block = {
        "object": "block",
        "type": "image",
        "image": {
            "external": {
                "url": url
            }
        }
    }
    return block

def make_table_row_block(row):
    block = {
        "object": "block",
        "type": "table_row",
        "table_row": {
            "cells": [text_with_style(data) for data in row]
        }
    }
    return block

def make_table_block(row):
    block = {
        "object": "block",
        "type": "table",
        "table": {
            "has_column_header": True,
            "has_row_header": False,
            "table_width": len(row),
            "children": [make_table_row_block(row)]
        }
    }
    return block

def make_code_block(language, code):
    block = {
        "object": "block",
        "type": "code",
        "code": {
            "language": language,
            "rich_text": [{"type": "text", "text": {"content": code}}]
        }
    }
    return block

def make_latex_bloock(latex):
    block = {
        "type": "equation",
        "equation": {
            "expression": latex
        }
    }
    return block

def make_embed_block(url):
    block = {
        "type": "embed",
        "embed": {
            "url": url
        }
    }
    return block

class MarkdownToNotionBlocks:
    def replace_latex_and_code_block(self, text):
        text = CODE_BLOCK_PATTERN.sub(replace_code_blocks, text)
        text = LATEX_BLOCK_PATTERN.sub(replace_latex_blocks, text)
        text = IMAGE_XML_BLOCK_PATTERN.sub(replace_image_xml_blocks, text)
        return text
    
    def convert(self, text):
        text = self.replace_latex_and_code_block(text)

        blocks = []
        list_stack = []
        for line in text.split('\n'):
            if not line:
                continue
            
            line = line.strip()
            heading_match = re.match(HEADING_PATTERN, line)
            unordered_list_match = re.match(UNORDERED_LIST_PATTERN, line)
            numbered_list_match = re.match(NUMBERED_LIST_PATTERN, line)
            image_match = re.match(IMAGE_PATTERN, line)
            table_match = re.match(TABLE_PATTERN, line)
            quote_match = re.match(QUOTE_PATTERN, line)
            horizon_rule_match = re.match(HR_PATTERN, line)
            
            if heading_match:
                line = re.sub(HEADING_PATTERN, '', line.strip()).strip()
                block = make_block(type=f'heading_{heading_match.group(1).count("#")}', text=line)
                blocks.append(block)

            elif unordered_list_match:
                indent = len(unordered_list_match.group(1))
                if indent == 0:
                    list_stack = []
                
                line = re.sub(UNORDERED_LIST_PATTERN, '', line)
                block = make_block('bulleted_list_item', text=line)

                while list_stack and list_stack[-1][1] >= indent:
                    list_stack.pop()

                if list_stack:
                    parent_element = list_stack[-1][0]
                    if 'children' not in parent_element[parent_element['type']]:
                        parent_element[parent_element['type']]['children'] = [block]
                    else:
                        parent_element[parent_element['type']]['children'].append(block)
                else:
                    blocks.append(block)
                    
                list_stack.append((block, indent))

            elif numbered_list_match:
                indent = len(numbered_list_match.group(1))
                if indent == 0:
                    list_stack = []
                
                line = re.sub(NUMBERED_LIST_PATTERN, '', line)
                block = make_block('numbered_list_item', text=line)

                while list_stack and list_stack[-1][1] >= indent:
                    list_stack.pop()

                if list_stack:
                    parent_element = list_stack[-1][0]
                    if 'children' not in parent_element[parent_element['type']]:
                        parent_element[parent_element['type']]['children'] = [block]
                    else:
                        parent_element[parent_element['type']]['children'].append(block)
                else:
                    blocks.append(block)
                
                list_stack.append((block, indent))

            elif image_match:
                _, url = image_match.groups()
                ext = url.split('.')[-1]
                if ext in SUPPORTED_IMG_EXT:
                    block = make_image_block(url)
                else:
                    block = make_embed_block(url)
                blocks.append(block)

            elif line.startswith("IMAGEXMLBLOCK"):
                idx = int(line.split('_')[-1])
                src, caption = image_xml_blocks[idx]
                block = make_image_block(src)
                blocks.append(block)
                block = make_block('paragraph',f'_{caption}_')
                blocks.append(block)

            elif table_match:
                table_delimeter = re.match(r'(\|[-| ]+\|)',line.strip())
                if table_delimeter:
                    continue
                
                row = re.match(r'(\|(.*)\|)',line.strip()).group(2).split('|')
                row = list(map(lambda s: s.strip(), row))
                if blocks and blocks[-1]['type'] == 'table':
                    block = blocks.pop()
                    block['table']['children'].append(make_table_row_block(row))
                else:
                    block = make_table_block(row)
                blocks.append(block)

            elif quote_match:
                line = quote_match.group(1)
                block = make_block(type='quote', text=line.strip())
                blocks.append(block)

            elif line.startswith("CODEBLOCK"):
                idx = int(line.split('_')[-1])
                language, code = code_blocks[idx]
                block = make_code_block(language, code)
                blocks.append(block)

            elif line.startswith("LATEXBLOCK"):
                idx = int(line.split('_')[-1])
                latex = latex_blocks[idx]
                block = make_latex_bloock(latex)
                blocks.append(block)
            
            elif horizon_rule_match:
                block = {'divider': {}, 'type': 'divider'}
                blocks.append(block)

            else:
                block = make_block(type='paragraph', text=line.strip())
                blocks.append(block)
        
        return blocks
