import yaml
from typing import List
from pydantic import BaseModel

class Main(BaseModel):
    plan: List[str]
    extract_materials: List[str]
    write: List[str]

class Reflect(BaseModel):
    revise: List[str]

class Prompt(BaseModel):
    main: Main
    reflect: Reflect

def load_prompt(file: str) -> Prompt:
    with open(file, 'r') as f:
        prompts = yaml.load(f, Loader=yaml.FullLoader)

    return Prompt.model_validate(prompts)