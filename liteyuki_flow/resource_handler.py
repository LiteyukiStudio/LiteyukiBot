"""
Module docs
"""
import requests  # type: ignore
import zipfile

from github import Github, InputGitTreeElement, GitTree
from github.Issue import Issue
from github.Repository import Repository
import json
import yaml

from liteyuki_flow.const import OPENED, EDITED, CLOSED, REOPENED, RESOURCE_JSON, edit_tip
from liteyuki_flow.markdown_parser import MarkdownParser
from liteyuki_flow.typ import err, nil

user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"

headers = {
        "User-Agent": user_agent
}


# opened: 创建新的资源包，预审核
# edited: 编辑资源包信息，需重新审核
# closed: 审核通过，修改json并提交
# reopened: 重新打开，无操作
def on_first_open(github: Github, issue: Issue, repo: Repository):
    cid = issue.create_comment("已收到资源包发布请求，我会马上开始预检. " + edit_tip).id
    parser = MarkdownParser(issue.body)
    parser.parse_front_matters()
    parser.front_matters["cid"] = str(cid)

    new_issue_body = parser.build_front_matters()
    issue.add_to_labels("Resource")
    issue.edit(body=new_issue_body)


# opened | edited
def pre_check(github: Github, issue: Issue, repo: Repository) -> err:
    parser = MarkdownParser(issue.body)
    parser.parse_front_matters()
    name = parser.front_matters.get("name")
    desc = parser.front_matters.get("desc")
    link = parser.front_matters.get("link")
    homepage = parser.front_matters.get("homepage")  # optional
    author = parser.front_matters.get("author")
    cid = int(parser.front_matters.get("cid"))  # optional auto
    if not all((name, desc, link, author)):
        issue.get_comment(cid).edit("name, desc, link, homepage 及 author 为必填字段.")
        return ValueError("name, desc, link, homepage 及 author 为必填字段.")

    # 下载并解析资源包
    r = requests.get(link, headers=headers)
    print(r.text)
    if r.status_code != 200:
        issue.get_comment(cid).edit("下载失败.")
        return ValueError("下载失败.")

    try:
        with open(f"tmp/{name}.zip", "wb") as f:
            f.write(r.content)
        # 解压
        with zipfile.ZipFile(f"tmp/{name}.zip", "r") as z:
            z.extractall(f"tmp/{name}")
        # 检测包内metadata.yml文件
        data = yaml.load(open(f"tmp/{name}/metadata.yml"), Loader=yaml.SafeLoader)
    except Exception:
        issue.get_comment(cid).edit("解析资源包失败，可能是格式问题或metadata.yml不存在.")
        return ValueError("解析资源包失败，可能是格式问题或metadata.yml不存在.")

    # 检测必要字段 name，description，version
    if not all((data.get("name"), data.get("description"), data.get("version"))):
        issue.get_comment(cid).edit("元数据中缺少必要字段 name, description 或 version.")
        return ValueError("元数据中缺少必要字段 name, description 或 version.")

    # 不检测重复资源包，因为资源包可能有多个版本
    # 检测通过，编辑原issue
    metadata_markdown = f"**名称**: {data.get('name')}\n**描述**: {data.get('description')}\n**版本**: {data.get('version')}\n"
    for k, v in data.items():
        if k not in ("name", "description", "version"):
            metadata_markdown += f"**{k}**: {v}\n"

    new_issue_body = f"---\nname: {name}\ndesc: {desc}\nlink: {link}\nhomepage: {homepage}\nauthor: {author}\n---\n"
    new_issue_body += f"# Resource: {name}\n"
    new_issue_body += f"## 发布信息\n{desc}\n"
    new_issue_body += f"**名称**: {name}\n"
    new_issue_body += f"**描述**: {desc}\n"
    new_issue_body += f"**作者**: {author}\n"
    new_issue_body += f"**主页**: {homepage}\n"
    new_issue_body += f"**下载**: {link}\n"
    # 遍历其他字段
    for k, v in data.items():
        if k not in ("name", "description", "version"):
            new_issue_body += f"**{k}**: {v}\n"

    issue.edit(body=new_issue_body)
    issue.add_to_labels("pre-checked")
    issue.get_comment(cid).edit("✅ 预检查通过\n## 元数据\n" + metadata_markdown)
    return nil


# closed
def add_resource(github: Github, issue: Issue, repo: Repository):
    parser = MarkdownParser(issue.body)
    parser.parse_front_matters()
    name = parser.front_matters.get("name")
    desc = parser.front_matters.get("desc")
    link = parser.front_matters.get("link")
    homepage = parser.front_matters.get("homepage")  # optional
    author = parser.front_matters.get("author")

    # 编辑仓库内的json文件
    resources = json.load(open(RESOURCE_JSON))
    resources.append({
            "name"    : name,
            "desc"    : desc,
            "link"    : link,
            "homepage": homepage,
            "author"  : author
    })
    ref = repo.get_git_ref("heads/main")
    tree = repo.create_git_tree(
        base_tree=repo.get_git_commit(ref.object.sha).tree,
        tree=[
                InputGitTreeElement(
                    path=RESOURCE_JSON,
                    mode="100644",
                    type="blob",
                    content=json.dumps(resources, indent=4, ensure_ascii=False)
                )
        ]
    )
    commit = repo.create_git_commit(
        message=f":package: 发布资源: {name}",
        tree=tree,
        parents=[repo.get_git_commit(ref.object.sha)]
    )
    ref.edit(commit.sha)


def handle_resource(github: Github, issue: Issue, repo: Repository, act_type: str):
    if act_type in (OPENED, EDITED):
        if act_type == OPENED:
            on_first_open(github, issue, repo)
        pre_check(github, issue, repo)
    elif act_type == CLOSED:
        add_resource(github, issue, repo)
    else:
        print("No operation found for the issue: ", act_type)
