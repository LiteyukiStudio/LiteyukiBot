"""
Module docs
"""
import os
from github import Github
from argparse import ArgumentParser

from liteyuki_flow.const import PLUGIN_PREFIX, RESOURCE_PREFIX
from liteyuki_flow.typ import err, nil  # type: ignore

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--handle", action="store_true")  # 处理issue

    parser.add_argument("-p", "--parse", action="store_true")  # 解析markdown文件
    parser.add_argument("-i", "--input", type=str, help="Path to the markdown file.")
    args = parser.parse_args()

    if args.handle:
        print("Starting the issue handler module...")
        ISSUE_NUMBER = os.getenv("ISSUE_NUMBER")
        REPOSITORY = os.getenv("REPOSITORY")
        ACT_TYPE = os.getenv("ACT_TYPE")  # opened, edited, closed, reopened
        if ISSUE_NUMBER is None or REPOSITORY is None or ACT_TYPE is None:
            raise ValueError("Issue number, repository and action type are required.")

        g = Github(os.getenv("GITHUB_TOKEN"))
        repo = g.get_repo(REPOSITORY)
        issue = g.get_repo(REPOSITORY).get_issue(int(ISSUE_NUMBER))

        # 审资源
        if issue.title.strip().startswith(RESOURCE_PREFIX):
            from liteyuki_flow.resource_handler import handle_resource  # type: ignore
            handle_resource(github=g, issue=issue, repo=repo, act_type=ACT_TYPE)

        # 审插件
        elif issue.title.strip().startswith(PLUGIN_PREFIX):
            from liteyuki_flow.plugin_handler import handle_plugin  # type: ignore
            pass

        else:
            print("No handler found for the issue.")

    elif args.parse:
        print("Starting the markdown parser module...")
        from liteyuki_flow.markdown_parser import MarkdownParser  # type: ignore

        if args.input is None:
            raise ValueError("Input file is required.")
        with open(args.input, "r", encoding="utf-8") as f:
            content = f.read()

        md_parser = MarkdownParser(content)  # type: ignore
        err = md_parser.parse_front_matters()  # type: ignore
        if err != nil:
            print(f"Err: {err}")
        for k, v in md_parser.front_matters.content.items():
            print(f"{k}: {v}")
    else:
        print("No module specified.")
