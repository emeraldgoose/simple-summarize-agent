from typing import TypedDict, List
from pydantic import BaseModel, Field

from langchain_core.prompts import ChatPromptTemplate
from langchain_community.document_loaders import AsyncHtmlLoader
from langchain_community.document_transformers import MarkdownifyTransformer
from langchain_community.tools import TavilySearchResults
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI

from agent.utils.logger import Logger
from agent.loader import Prompt

logger = Logger()

class State(TypedDict):
    url: str
    planning_steps: List[str]
    title: str
    document: str
    figures: List[str]
    tables: List[str]
    drafts: List[str]
    final_doc: str


class ReflectionState(TypedDict):
    draft: str
    reflection: List[str]
    search_queries: List[str]
    revised_draft: str
    revision_number: int


class Reflection(BaseModel):
    missing: str = Field(
        description="Critique of what is missing"
        )
    advisable: str = Field(
        description="Critique of what is helpful for better writing"
        )
    superfluous: str = Field(
        description="Critique of what is superfluous"
        )

class Research(BaseModel):
    """Provide reflection and then follow up with search queries to improve the writing."""
    reflection: Reflection = Field(
        description="Your reflection on the initial writing for summary."
        )
    search_queries: List[str] = Field(
        description="1-3 search queries for researching improvements to address the critique of your current writing."
        )


def get_chat():
    chat = ChatGoogleGenerativeAI(model='gemini-2.0-flash-001')
    return chat


def get_document_node(state: State):
    url = state.get('url')
    loader = AsyncHtmlLoader(url)
    docs = loader.load()

    md = MarkdownifyTransformer()
    converted_docs = md.transform_documents(docs)
    
    title = converted_docs[0].metadata['title']
    document = converted_docs[0].page_content

    logger.log("", "Load HTML and Convert to Markdown")
    logger.log(document, title)
    
    return State(title=title, document=document)


def plan_node(state: State, config):
    document = state.get('document')
    prompts: Prompt = config["configurable"].get("prompts")
    
    planner_prompt = ChatPromptTemplate([('human', prompts.main.plan)])
    chat = get_chat()

    planner = planner_prompt | chat
    response = planner.invoke({"document": document})
    plan = response.content.strip().replace('\n\n','\n')
    planning_steps = plan.split('\n')
    
    logger.log(plan, "Split and Plan")

    return State(planning_steps=planning_steps)


def extract_materials(state: State, config):
    document = state.get('document')
    prompts: Prompt = config["configurable"].get("prompts")

    materials_prompt = ChatPromptTemplate([('human', prompts.main.extract_materials)])
    chat = get_chat()
    
    extracted_materials = materials_prompt | chat
    response = extracted_materials.invoke({"document": document})
    materials = response.content

    figure_materials = materials[materials.find('<figures>')+9:materials.find('</figures>')].split('\n\n')
    table_materials = materials[materials.find('<tables>')+8:materials.find('</tables>')].split('\n\n')

    figures, tables = [], []
    for figure in figure_materials:
        figures.append(figure.strip())

    for table in table_materials:
        tables.append(table.strip())

    logger.log(f"Extract figures: {len(figures)}\n\nExtract tables: {len(tables)}", "Extract Materials")
    
    return State(figures=figures, tables=tables)


def execute_node(state: State, config):
    document = state.get('document')
    planning_steps = state.get('planning_steps')
    figures = state.get('figures')
    tables = state.get('tables')
    prompts: Prompt = config["configurable"].get("prompts")

    write_prompt = ChatPromptTemplate([('human', prompts.main.write)])
    text = ""
    drafts = []
    for step in planning_steps:
        chat = get_chat()
        write_chain = write_prompt | chat

        result = write_chain.invoke({
            "document": document,
            "plan": planning_steps,
            "text": text,
            "STEP": step,
            "figures": figures,
            "tables": tables
        })
        output = result.content

        draft = output[output.find('<result>')+8:len(output)-9]

        drafts.append(draft)
        text += draft + '\n\n'

    logger.log(text, "Write Draft")
    
    return State(drafts=drafts)


def revise_answers(state: State, config):
    drafts = state.get("drafts")

    # Not using multiprocessing
    reflection_process = get_reflect_workflow()
    
    final_doc = ""
    for draft in drafts:
        output = reflection_process.invoke({"draft":draft}, config)
        final_doc += output.get('revised_draft') + '\n\n'

    logger.log(final_doc, "Revised Draft")
    
    return State(final_doc=final_doc)


def reflect_node(state: ReflectionState, config):
    draft = state.get('draft')
    search = config['configurable'].get('on_search')

    reflection = []
    search_queries = []
    for _ in range(2):
        chat = get_chat()
        structured_llm = chat.with_structured_output(Research, include_raw=True)

        info = structured_llm.invoke(draft)
        if not info['parsed'] == None:
            parsed_info = info['parsed']
            reflection = [parsed_info.reflection.missing, parsed_info.reflection.advisable]
            if search:
                search_queries = parsed_info.search_queries
            break

    logger.log(f"Reflection.missing: {reflection[0]}\n\nReflection.advisable: {reflection[1]}", "Reflect and Search")

    revision_number = state.get('revision_number') if state.get('revision_number') is not None else 1
    return ReflectionState(revision_number=revision_number, search_queries=search_queries, reflection=reflection)


def revise_draft(state: ReflectionState, config):
    on_search = config['configurable'].get('search')
    draft = state.get('draft')
    search_queries = state.get('search_queries')
    reflection = state.get('reflection')
    prompts: Prompt = config["configurable"].get("prompts")

    content = []
    if on_search:
        search = TavilySearchResults(max_results=1)
        for q in search_queries:
            response = search.invoke(q)
            for r in response:
                if 'content' in r:
                    content.append(r.get('content'))

    chat = get_chat()
    revise_prompt = ChatPromptTemplate([('human',prompts.reflect.revise)])
    reflect = revise_prompt | chat
    result = reflect.invoke({
        "draft": draft,
        "reflection": reflection,
        "content": content,
    })
    output = result.content
    revision_draft = output[output.find('<result>')+8:len(output)-9]
    revision_number = state.get("revision_number",1)

    logger.log(revision_draft, f"Revise draft: Ver.{revision_number}")
    
    return ReflectionState(revised_draft=revision_draft, revision_number=revision_number+1)


def should_continue(state: ReflectionState, config):
    max_revision = config['configurable'].get("max_revision")
    
    if state.get('revision_number') > max_revision:
        return "end"
    return "continue"


def get_reflect_workflow():
    workflow = StateGraph(ReflectionState)

    workflow.add_node("reflect_node", reflect_node)
    workflow.add_node("revise_draft", revise_draft)

    workflow.set_entry_point("reflect_node")
    workflow.add_conditional_edges(
        "revise_draft",
        should_continue,
        {"end": END, "continue": "reflect_node"}
    )

    workflow.add_edge("reflect_node", "revise_draft")
    return workflow.compile()


def get_main_workflow():
    workflow = StateGraph(State)

    workflow.add_node("get_document_node", get_document_node)
    workflow.add_node("plan_node",plan_node)
    workflow.add_node("extract_materials", extract_materials)
    workflow.add_node("execute_node", execute_node)
    workflow.add_node("revise_answers",revise_answers)

    workflow.set_entry_point("get_document_node")

    workflow.add_edge("get_document_node","plan_node")
    workflow.add_edge("get_document_node","extract_materials")
    workflow.add_edge("plan_node","execute_node")
    workflow.add_edge("extract_materials","execute_node")
    workflow.add_edge("execute_node", "revise_answers")
    workflow.add_edge("revise_answers",END)

    graph = workflow.compile()
    return graph

