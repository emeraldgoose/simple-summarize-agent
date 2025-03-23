import argparse

from dotenv import load_dotenv
from langgraph.graph import StateGraph

from agent.loader import load_prompt
from agent.utils.logger import Logger
from agent.base_agent import get_main_workflow

logger = Logger()

def get_workflow_diagram(graph: StateGraph):
    return graph.get_graph().draw_mermaid()

def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", type=str, required=True, help="URL of the page you want to summarize")
    parser.add_argument("--search", type=bool, default=False, help="Using TavilySearch")
    parser.add_argument("--max-revision", type=int, default=1, help="Number of desired revisions")
    return parser.parse_args()


def main(url: str, search: bool, max_revision: int):
    assert load_dotenv('secret.env'), "Failed load environment variables."
    
    prompts = load_prompt('agent/prompts/task_prompts.yaml')
    config = {"prompts": prompts, "search": search, "max_revision": max_revision}

    graph = get_main_workflow()
    logger.log(get_workflow_diagram(graph), "MAIN WORKFLOW DIAGRAM")

    final = graph.invoke({"url": url}, config=config)
    with open("final.md", 'w+') as f:
        f.write(final['final_doc'])

if __name__ == "__main__":
    args = parse_arguments()
    main(args.url, args.search, args.max_revision)